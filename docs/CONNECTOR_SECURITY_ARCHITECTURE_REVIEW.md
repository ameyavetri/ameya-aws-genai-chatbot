# Connector Security Architecture Review

**Scope:** AWS GenAI Chatbot with MCP connectors (Azure SQL + Dropbox).  
**Focus:** Authorization, workspace scope, access control flow, scenario validation, gaps, and recommendations.

---

## 1. Authorization & Scope

### 1.1 Are Azure SQL and Dropbox connectors scoped at the WORKSPACE level?

**Yes, by design.** Connectors are stored and listed per workspace.

- **Storage:** Connector records in DynamoDB include `workspace_id`. Table schema (CDK): PK `connector_id`, SK `workspace_id`; GSI `by_workspace` on `(workspace_id, connector_type)`.
  - **File:** `lib/connectors/connector-dynamodb-tables/index.ts` (lines 23–57).
- **Creation:** `create_connector(workspace_id, connector_config)` always binds the connector to a workspace.
  - **File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` (lines 30–50).
- **Listing:** `list_connectors(workspace_id, connector_type)` and `get_connectors_for_application(workspace_id, application_id)` both filter by `workspace_id`.
  - **File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` (lines 70–95, 136–148).

So connectors are **not** globally accessible by API design; they are workspace-scoped in the registry.

### 1.2 Globally accessible?

**No.** There is no API that lists “all connectors” across workspaces. All connector listing paths take `workspace_id` and query the `by_workspace` GSI. Access to a **specific** workspace’s connectors is still subject to whether the backend **validates** that the requesting user is allowed to use that `workspace_id` (see Section 4).

---

## 2. Access Control Flow

End-to-end path: **UI → GraphQL (sendQuery) → send-query resolver → SNS → request-handler (Lambda) → resolve_context_for_prompt → registry/orchestrator → MCP gateway.**

### 2.1 UI → GraphQL

- **Playground (no application):** Request payload includes `data.workspaceId` from the client (selected workspace).
  - **File:** `lib/user-interface/react-app/src/components/chatbot/chat-input-panel.tsx` (lines 555–577): `workspaceId: state.selectedWorkspace?.value`.
- **Application (end-user):** Request includes `applicationId` only; **no** `workspaceId` in payload. Workspace is resolved on the server from the application record.
  - **File:** same file (lines 541–554): when `props.applicationId` is set, `data` has no `workspaceId`.

### 2.2 GraphQL API → send-query Lambda resolver

- **With applicationId:** Resolver loads application, checks user is in application roles (or admin/workspace_manager), then builds the message with **server-side** `workspaceId` from `application_item.get("Workspace")` (e.g. `Workspace::<id>`). Client cannot override workspace.
  - **File:** `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py` (lines 81–134).
- **Without applicationId (playground):** Resolver only checks user is in `admin` or `workspace_manager`; then sets `message["data"] = request.get("data", {})`. So **entire `data` (including `workspaceId`) is client-supplied.**
  - **File:** same file (lines 136–147): `message = { ..., "data": request.get("data", {}), }`. No validation that the user is allowed to use the given `workspaceId`.

### 2.3 Request-handler (handle_run)

- Reads `workspace_id = data.get("workspaceId", None)` and `application_id = data.get("applicationId")`.
  - **File:** `lib/model-interfaces/langchain/functions/request-handler/index.py` (lines 256–257, 351–358).
- Calls `resolve_context_for_prompt(prompt, source_mode, workspace_id, user_id, application_id)` with that `workspace_id`. No check here that the user is allowed to use `workspace_id`.

### 2.4 resolve_context_for_prompt → registry

- If `application_id`: uses `get_connectors_for_application(workspace_id, application_id)` (workspace + application scoped).
- Else: uses `list_connectors(workspace_id=workspace_id)` and filters to active, workspace-level connectors.
  - **File:** `lib/model-interfaces/langchain/functions/request-handler/index.py` (lines 91–115).
- Connector list is always derived from the **single** `workspace_id` passed in. That `workspace_id` is trusted as the “current workspace” for the request; there is no separate step that validates “this user may use this workspace.”

### 2.5 Orchestrator

- `execute_query(workspace_id, connector_id, user_prompt, ...)` is called with the `connector_id` chosen from the list above.
- **File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py` (lines 14–80).
- **Workspace check:** After `get_connector(connector_id)`, it enforces:
  - `if connector.get("workspace_id") != workspace_id: raise CommonError("Connector does not belong to this workspace")` (lines 36–37).
- **Application check:** If `application_id` is present, it enforces:
  - `if application_id and application_id not in connector.get("application_ids", []): raise CommonError("Connector not enabled for this application")` (lines 39–40).

So **once** a connector is selected, the orchestrator ensures it belongs to the given workspace (and optionally application). It does **not** ensure that the **caller** is allowed to use that workspace; that would have to be enforced earlier (e.g. in the resolver or a shared auth layer).

### 2.6 Where workspace_id and application_id are validated

| Location | workspace_id | application_id |
|----------|--------------|----------------|
| **send-query resolver (with application)** | Set server-side from application record; not client-supplied. | User must be in application roles or admin/workspace_manager. |
| **send-query resolver (playground)** | **Not validated.** Taken from `request.get("data", {})`. | N/A. |
| **request-handler** | Not validated; passed through to context resolution. | Passed through. |
| **resolve_context_for_prompt** | Used to filter connectors; not validated against user. | Used for get_connectors_for_application. |
| **orchestrator.execute_query** | Validated against connector’s `workspace_id`. | Validated against connector’s `application_ids`. |

**Conclusion:** `workspace_id` is **validated only** in the orchestrator **relative to the connector**, not relative to the **user**. There is no step that asserts “this user is allowed to use workspace WK1.”

---

## 3. Scenario Validation

**Scenario:**

- Workspace **WK1** → RAG + SQL + Dropbox enabled (connectors registered).
- Workspace **WK2** → Only RAG (no connectors).
- **User A** → intended to use WK1.
- **User B** → intended to use WK2.

**Desired:** User A can use SQL/Dropbox via WK1; User B cannot use SQL/Dropbox and only uses RAG (e.g. WK2).

### 3.1 User A can access SQL/Dropbox via chat and API

- **With applicationId:** If the application is tied to WK1, resolver sets `workspaceId` from the application; context resolution lists WK1 connectors; orchestrator allows. **Code path is correct.**
- **Playground:** If User A sends a request with `data.workspaceId === WK1`, the same flow runs: list_connectors(WK1), connector context used, execute_query(WK1, connector_id, …). **Code path allows it.**

So User A can access WK1 connectors when the request carries WK1 as `workspaceId`.

### 3.2 User B CANNOT access SQL/Dropbox (required)

- **Intended use:** User B uses WK2; WK2 has no connectors, so no connector context should be used.
- **Actual behavior:** The backend does **not** check “this user may only use WK2.” So if User B (or any client) sends a request with `data.workspaceId === WK1`:
  1. send-query resolver (playground) forwards `data` as-is (including `workspaceId: WK1`).
  2. request-handler uses `workspace_id = WK1`.
  3. resolve_context_for_prompt calls `list_connectors(workspace_id=WK1)` and gets WK1’s connectors.
  4. Connector context is fetched and injected; orchestrator’s workspace check passes (connector belongs to WK1, request says WK1).

So **User B can access WK1’s SQL/Dropbox by sending `workspaceId: WK1` in the playground.** There is no “user ↔ workspace” authorization; only “connector ↔ workspace” and “connector ↔ application” are enforced.

### 3.3 User B only uses RAG

- If User B (or the UI) always sends `workspaceId: WK2`, then only WK2 is used; WK2 has no connectors, so only RAG (and other non-connector context) applies. So **behavior depends entirely on the client sending the correct workspaceId**; the server does not enforce “User B may only use WK2.”

**Scenario verdict:** The scenario is **not** enforced in code. A WK2 user can use WK1 connectors by supplying WK1 as `workspaceId` in the chat path when not using an application.

---

## 4. Security Gaps

### 4.1 Path where a WK2 user can query WK1 connectors

- **Path:** Playground (no applicationId) → sendQuery with `data: { ..., workspaceId: "<WK1_ID>" }`.
- **Files:**
  - `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py` (lines 136–147): forwards `request.get("data", {})` without validating `workspaceId` against the user.
  - `lib/model-interfaces/langchain/functions/request-handler/index.py` (lines 257, 352–358): uses `data.get("workspaceId")` and passes it to `resolve_context_for_prompt`.
- **Root cause:** No server-side rule that restricts which `workspace_id` a given user (or group) may use in the chat flow.

### 4.2 Connector registry queried without workspace filtering

- **List paths:** All list paths use `workspace_id`:
  - `list_connectors(workspace_id, connector_type)` — GSI `by_workspace`.
  - `get_connectors_for_application(workspace_id, application_id)` — calls `list_connectors(workspace_id)` then filters by application.
- **Get path:** `get_connector(connector_id)` fetches by **connector_id only**; no workspace in the key.
  - **File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` (lines 52–68): `get_item(Key={"connector_id": connector_id})`.
  - **Note:** Table is defined with **composite** PK+SK `(connector_id, workspace_id)` in CDK. If the table is deployed that way, `get_item` with only `connector_id` would be invalid (DynamoDB requires full primary key). So either the table is single-key in practice, or this call is buggy. The docstring (lines 55–57) says “query using the primary key and return the first match” but the code uses `get_item`, not `query`.
- So: **listing** is always workspace-filtered; **get_connector** is by ID only and is then checked in the orchestrator against `workspace_id`. The gap is not “registry without workspace filtering” for list; it is **no user↔workspace check** before using that workspace_id.

### 4.3 Connector ID reuse cross-workspace

- **Design:** Connector records are keyed by `(connector_id, workspace_id)` (per CDK). So the same logical `connector_id` could exist in different workspaces as different items (different SK). But `get_connector(connector_id)` only passes `connector_id`; if the table really has a sort key `workspace_id`, that API cannot work as written. If instead the table uses only `connector_id` as PK, then one connector_id could only point to one workspace (one item). Either way, the **orchestrator** enforces that the fetched connector’s `workspace_id` matches the request’s `workspace_id`, so cross-workspace reuse of a single connector record is not allowed at execution time.
- **Remaining risk:** If an API or future code path called `get_connector(connector_id)` and then used that connector **without** passing and checking `workspace_id`, that would be a cross-workspace leak. Today the only caller of `get_connector` in the chat path is the orchestrator, which does receive and check `workspace_id`.

### 4.4 RBAC missing or weak

- **Playground:** Only check is “user in admin or workspace_manager” (send-query resolver lines 137–138). No per-workspace or per-connector RBAC; any such user can send any `workspaceId` and get that workspace’s connectors.
- **Application path:** Application roles and workspace are enforced; workspace is server-set. RBAC is stronger.
- **API handler (workspaces):** `listWorkspaces` / `getWorkspace` require admin or workspace_manager; they return all workspaces (no user↔workspace filter). So there is no “User B only sees WK2” in the backend; it’s by UI selection only.
- **Connectors:** No GraphQL/resolvers found that expose connector CRUD or `test_connector` to the client; `test_connector(connector_id)` in the orchestrator has no workspace check and is not exposed in the schema. If it were later exposed, it would need to accept and validate workspace (and user) before use.

---

## 5. Code References (Enforcing Scope)

### 5.1 Workspace-scoped connector list

| File | Function / location | What it does |
|------|---------------------|--------------|
| `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` | `list_connectors(workspace_id, connector_type)` (70–95) | Query GSI `by_workspace` with `workspace_id`. |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` | `get_connectors_for_application(workspace_id, application_id)` (136–148) | Calls `list_connectors(workspace_id)`, then filters by `application_ids` and status. |
| `lib/model-interfaces/langchain/functions/request-handler/index.py` | `resolve_context_for_prompt` (58–175) | Uses either `get_connectors_for_application(workspace_id, application_id)` or `list_connectors(workspace_id=workspace_id)`; connector list is always workspace-based. |

### 5.2 Orchestrator workspace and application check

| File | Function / location | What it does |
|------|---------------------|--------------|
| `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py` | `execute_query` (14–80) | After `get_connector(connector_id)`: checks `connector.get("workspace_id") != workspace_id` → raise; if `application_id`, checks `application_id in connector.get("application_ids", [])`. |

### 5.3 Application path (server-side workspace)

| File | Function / location | What it does |
|------|---------------------|--------------|
| `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py` | `handler` (72–161) | When `request.get("applicationId")`: loads application, checks user in app roles or admin/workspace_manager, sets `workspaceId` from `application_item.get("Workspace")` (server-side). |

### 5.4 DynamoDB and IAM

| File | What it does |
|------|---------------------|
| `lib/connectors/connector-dynamodb-tables/index.ts` | Connectors table: PK `connector_id`, SK `workspace_id`; GSI `by_workspace` (`workspace_id`, `connector_type`). |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` | Uses `CONNECTORS_TABLE_NAME`; create/list/update/delete use workspace or connector_id; get_connector uses only connector_id. |

---

## 6. Verdict

**Partially isolated.**

- **Positive:** Connectors are stored and listed by workspace; orchestrator enforces connector↔workspace and connector↔application; application path uses server-side workspace and application RBAC.
- **Negative:** In the **playground** path, `workspace_id` is client-supplied and **never** validated against the user. Any admin/workspace_manager user can set `workspaceId` to another workspace and use that workspace’s connectors (e.g. WK2 user can use WK1’s SQL/Dropbox). There is no user↔workspace authorization in the codebase.

So: **connector isolation by workspace is implemented; user isolation to a subset of workspaces is not.**

---

## 7. Recommendations

### 7.1 (Critical) Validate workspace access in send-query resolver for playground

**Goal:** Ensure the user is allowed to use the requested workspace before forwarding `workspaceId` to the chat pipeline.

**Option A – Allowlist of workspace IDs per user/group (e.g. from Cognito or DB):**  
In the send-query resolver, when there is no `applicationId`, resolve the set of workspace IDs the user may use (e.g. from a “user_workspaces” or “group_workspaces” table, or from Cognito custom attributes). If `request["data"].get("workspaceId")` is not in that set, return 403 or overwrite with a default allowed workspace.

**Option B – Restrict to workspaces returned by listWorkspaces and enforce in backend:**  
Today `listWorkspaces` returns all workspaces. If you later restrict it per user (e.g. by group or membership table), then in the send-query resolver (playground path) you could call the same “allowed workspaces for this user” logic and require `request["data"]["workspaceId"]` to be in that set; otherwise reject or clear connector usage.

**File:** `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py`

**Example patch (Option B – placeholder for “allowed workspaces”):**

```python
# After line 136, before building message:
else:
    if not ("admin" in user_roles or "workspace_manager" in user_roles):
        raise RuntimeError("User is not authorized to access this application")

    data = request.get("data", {})
    workspace_id_from_client = data.get("workspaceId")

    # Validate workspace access: only allow workspaces the user is allowed to use.
    allowed_workspace_ids = get_allowed_workspace_ids_for_user(
        event["identity"]["sub"], user_roles
    )  # Implement: e.g. from DynamoDB or Cognito
    if workspace_id_from_client and allowed_workspace_ids is not None:
        if workspace_id_from_client not in allowed_workspace_ids:
            raise RuntimeError("User is not authorized to use this workspace")

    message = {
        "action": request["action"],
        ...
        "data": data,
    }
```

Implement `get_allowed_workspace_ids_for_user` (e.g. list workspaces for the user’s group or membership table). Until you have per-user/group workspace membership, you could temporarily **reject** requests that contain a `workspaceId` not in a configured list, or leave the function to “allow all” and add the check when membership exists.

### 7.2 (Important) Align registry get_connector with table key schema

**File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py`

If the table uses composite key `(connector_id, workspace_id)`:

- Change `get_connector(self, connector_id: str)` to `get_connector(self, connector_id: str, workspace_id: Optional[str] = None)` and use both in `get_item` when provided; or
- Use `query` with `KeyConditionExpression = Key("connector_id").eq(connector_id)` and return the first item (and document that connector_id is unique per workspace), and ensure callers pass `workspace_id` when available so you can optionally filter.

Orchestrator already has `workspace_id` when it calls `get_connector`; so the orchestrator could call `get_connector(connector_id, workspace_id)` and the registry could use both keys for a composite-key table.

### 7.3 (Hardening) Optional: Validate workspace in request-handler

Even if the resolver enforces workspace access, the request-handler can add a second check: resolve “allowed workspaces for this user” (e.g. from context or a small lookup) and ensure `data.get("workspaceId")` is in that set before calling `resolve_context_for_prompt`. This limits impact of bugs or alternate entry points.

**File:** `lib/model-interfaces/langchain/functions/request-handler/index.py`  
**Location:** Before calling `resolve_context_for_prompt` (around 352), add a guard that checks `workspace_id` against the same “allowed workspaces” concept used in the resolver (e.g. shared helper or env/lookup). If invalid, skip connector context (or return an error) and continue with RAG-only.

### 7.4 (If connector APIs are added) Protect test_connector and any connector-by-ID APIs

**File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py` — `test_connector(connector_id)` (84–114) has no workspace or user check. If you expose it via GraphQL/REST:

- Require `workspace_id` (and optionally `application_id`) in the request.
- Resolve “allowed workspaces” for the user; require `workspace_id` in that set.
- Call `get_connector(connector_id, workspace_id)` (once 7.2 is done) and optionally verify connector’s `workspace_id` matches before calling the MCP health check.

---

**Summary:** Connectors are workspace-scoped in storage and listing, and the orchestrator enforces connector↔workspace and connector↔application. The main gap is **no validation of client-supplied `workspaceId` against the user** in the playground path, allowing a WK2 user to use WK1 connectors. Implementing 7.1 (and optionally 7.2 and 7.3) will align the implementation with a “fully workspace-isolated” and user-aware model.
