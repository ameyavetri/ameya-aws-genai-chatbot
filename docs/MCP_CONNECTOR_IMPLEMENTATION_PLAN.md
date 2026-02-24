# MCP Connector Implementation Plan

## Executive Summary

This plan covers end-to-end implementation of MCP Data Source Connectors in the AWS GenAI LLM Chatbot: fixing critical infrastructure (registry key schema, request-handler wiring), adding backend API and GraphQL, frontend Connectors UI, chat flow integration with citations/source attribution, integration tests, security/RBAC, Secrets Manager, deployment and migration, documentation, and observability.

**Estimated effort:** ~15–25 person-days depending on parallelization and test depth.

**Key risks:**
- Registry `get_connector` / `update_connector` / `delete_connector` use only `connector_id` while the DynamoDB table has composite primary key `(connector_id, workspace_id)`; this causes incorrect or failing behavior and must be fixed first.
- Request-handler Lambda currently does **not** receive `CONNECTORS_TABLE_NAME` or table access; connector context in chat will not run until this is wired in CDK.
- Playground path does not validate `workspaceId` against the user; a user can supply another workspace’s ID and access its connectors (see CONNECTOR_SECURITY_ARCHITECTURE_REVIEW.md).

**Dependencies:** Part 1 (infrastructure fixes) blocks Part 2 (API), Part 5 (chat flow), and Part 6 (integration tests). Part 2 + Part 3 (GraphQL) can proceed in parallel after Part 1. Part 7 (RBAC/Secrets) should be done with Part 2.

---

## Part 1: Fix Critical Infrastructure Issues

### Step 1.1: Fix Registry get_connector()

**Recommended approach: Option B — use composite key and require workspace_id where available.**

**Rationale:** The connectors table is defined in `lib/connectors/connector-dynamodb-tables/index.ts` with **partition key `connector_id`** and **sort key `workspace_id`**. DynamoDB `get_item` requires both keys. The current `get_connector(connector_id)` uses only `connector_id`, so the call is invalid for this schema and would fail at runtime. Option A (change table to PK-only) would break the GSI `by_workspace` design. Option C (query by connector_id) is possible but less efficient and still needs a single-item contract; Option B keeps the schema and makes the API explicit.

**Changes required:**

1. **`lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py`**
   - Change `get_connector(self, connector_id: str)` to `get_connector(self, connector_id: str, workspace_id: Optional[str] = None) -> Dict[str, Any]`.
   - If `workspace_id` is provided: call `self._table.get_item(Key={"connector_id": connector_id, "workspace_id": workspace_id})`.
   - If `workspace_id` is None: use `query` with `KeyConditionExpression = Key("connector_id").eq(connector_id)`, return the first item (and document that connector_id is globally unique per table, or that “first” is arbitrary if not). Prefer requiring `workspace_id` at all call sites and document that as the canonical API.
   - Update the module-level helper `get_connector(connector_id, workspace_id=None)` to pass through both arguments.

2. **Call sites of get_connector:**
   - **`lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py`**: In `execute_query` and `test_connector`, the orchestrator already has `workspace_id` (in `execute_query`) but not in `test_connector`. Change to:
     - `execute_query`: call `get_connector(connector_id, workspace_id)` (add workspace_id parameter to the module-level call).
     - `test_connector`: change to `test_connector(connector_id: str, workspace_id: Optional[str] = None)`. If workspace_id is provided, call `get_connector(connector_id, workspace_id)`; otherwise use query-by-connector_id for backward compatibility (e.g. from API where workspace is not yet passed).
   - **Any future connector API route** that fetches by ID must pass `workspace_id` (from validated request context) when calling `get_connector`.

**Migration strategy:** No data migration. This is a code-only fix. Existing connector records already have both `connector_id` and `workspace_id` in the table.

**Impact:** Callers that today call `get_connector(connector_id)` without workspace_id must be updated to pass workspace_id where available (orchestrator); otherwise the registry can fall back to query. **Design decision:** Decide whether `test_connector` and any “get by ID” API should require `workspace_id` (recommended for consistency and security).

---

### Step 1.2: Fix update_connector and delete_connector for composite key

**File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py`

- **update_connector(connector_id, updates):** Today uses `Key={"connector_id": connector_id}` in `update_item`. Change to accept `workspace_id: Optional[str] = None`; when provided use `Key={"connector_id": connector_id, "workspace_id": workspace_id}`. When not provided, either query by connector_id to get the item and use its workspace_id for the update, or require workspace_id (recommended).
- **delete_connector(connector_id):** Same: add `workspace_id` parameter and use composite key for the update_item that sets status=inactive (or for a future hard delete).

**Call sites:** No current call sites in the repo for update/delete except future API routes; those routes must pass workspace_id from the validated request (e.g. from path or body and validated against user’s allowed workspaces).

---

### Step 1.3: Wire CONNECTORS_TABLE_NAME to Request Handler

**Problem:** In `lib/aws-genai-llm-chatbot-stack.ts`, when `props.config.connectors?.enabled` is true, only the **api-handler** Lambda gets `CONNECTORS_TABLE_NAME` and `connectorsTable.grantReadWriteData(apiHandler)`. The **request-handler** (LangChain Lambda) that runs the chat flow and calls `resolve_context_for_prompt` does **not** get this env or table access, so connector context is never used in chat.

**Changes required:**

1. **`lib/aws-genai-llm-chatbot-stack.ts`** (inside the same `if (props.config.connectors?.enabled)` block, after creating `connectorTables` and configuring api-handler):
   - After the block that configures the api-handler (around lines 268–292), add:
     - If `langchainInterface` is defined: grant the **request-handler** access to the connector table and set the env var:
       - `connectorTables.connectorsTable.grantReadData(langchainInterface.requestHandler)` (read-only is sufficient for context resolution; write is only needed for API-handler CRUD).
       - `langchainInterface.requestHandler.addEnvironment("CONNECTORS_TABLE_NAME", connectorTables.connectorsTable.tableName)`.
   - **Dependency:** `langchainInterface` is created earlier in the stack (around line 84), so it is in scope in the connectors block. No need to reorder construct creation.

2. **Optional (recommended):** Add **CONNECTOR_GATEWAY_URL** or per-connector endpoint resolution: Today connector records store `endpoint.url` per connector. If the request-handler or MCP client needs a base gateway URL (e.g. for dynamic path construction), it can be an env var set from the Connector Gateway ALB. Document in Part 9 if you add it.

**Impact:** After deploy, the LangChain request-handler will have `CONNECTORS_TABLE_NAME` set and read access to the connectors table, so `resolve_context_for_prompt` will no longer skip the connector block due to missing env.

---

## Part 2: Backend API Routes

**Location:** New route module and GraphQL resolvers backed by the same Lambda (api-handler).

### Step 2.1: Connector API route module

- **New file:** `lib/chatbot-api/functions/api-handler/routes/connectors.py`
  - Use the same pattern as `routes/applications.py` and `routes/workspaces.py`: `Router()`, `UserPermissions(router)`, `@router.resolver(field_name="...")`, and `@permissions.approved_roles(...)`.
  - Implement resolvers that delegate to `genai_core.connectors.registry` and `genai_core.connectors.orchestrator`:
    - **createConnector:** Parse input (workspaceId, name, type, endpoint, credentialsSecretArn, allowedResources, applicationIds, etc.). Validate workspace access (user must be admin or workspace_manager and allowed to use that workspace — see Part 7). Create secret in Secrets Manager (Part 7.2), then `registry.create_connector(workspace_id, connector_config)` with `connector_config` containing no raw credentials; store only `credentials_secret_arn` (or equivalent key) in the connector item. Return the created connector (mask secret ARN in response).
    - **listConnectors:** Input: workspaceId, optional connectorType. Resolve allowed workspaces for user; if requested workspaceId not in allowed list, return 403 or empty. Call `registry.list_connectors(workspace_id, connector_type)`. Return list; mask any credential fields.
    - **getConnector:** Input: connectorId, workspaceId (required for composite key and scope check). Validate workspace access; call `registry.get_connector(connector_id, workspace_id)`; return connector (mask credentials).
    - **updateConnector:** Input: connectorId, workspaceId, updates. Validate workspace access and that user is admin or workspace_manager. Optionally update secret in Secrets Manager if credentials changed. Call `registry.update_connector(connector_id, updates, workspace_id=workspace_id)`.
    - **deleteConnector:** Input: connectorId, workspaceId. Validate workspace access; delete or rotate secret (Part 7.2); call `registry.delete_connector(connector_id, workspace_id)`.
    - **testConnector:** Input: connectorId, workspaceId. Validate workspace access; call `orchestrator.test_connector(connector_id, workspace_id)` (orchestrator must call get_connector with workspace_id).
  - All connector mutations and testConnector: restrict to **admin or workspace_manager** (same as workspaces). List/get: allow same roles and ensure workspace scoping (only return connectors for workspaces the user is allowed to use). See Part 7.1 for exact role checks.

2. **`lib/chatbot-api/functions/api-handler/index.py`**
   - Import and include the connectors router: `from routes.connectors import router as connectors_router` and `app.include_router(connectors_router)`.
   - Guard inclusion (e.g. only include if connectors feature is enabled) if desired; otherwise always include and let schema/resolvers return appropriate errors when table is not configured.

**Input validation:** Use Pydantic or existing validation patterns (e.g. `SAFE_STR_REGEX`, `ARN_VALIDATION_OPTIONAL`) for connectorId, workspaceId, name, type, endpoint URL, secret ARN, allowedResources structure. Reject oversized or invalid input.

---

## Part 3: GraphQL Schema

**File:** `lib/chatbot-api/schema/schema.graphql`

### Add types and inputs

- **Connector type** (example; align with registry and API):
  - `type Connector @aws_cognito_user_pools { id: ID! workspaceId: ID! name: String! type: String! status: String endpoint: ConnectorEndpoint credentialsSecretArn: String # masked or null in response applicationIds: [String] allowedResources: AllowedResources createdAt: AWSDateTime updatedAt: AWSDateTime }`
- **ConnectorEndpoint:** `type ConnectorEndpoint { type: String url: String }`
- **AllowedResources:** structure matching `allowed_resources` (schemas, tables, views, rateLimits).
- **Inputs:** `CreateConnectorInput`, `UpdateConnectorInput`, `TestConnectorInput` (connectorId, workspaceId), etc.

### Add Query and Mutation

- **Query:** `listConnectors(workspaceId: ID!, connectorType: String): [Connector]!`, `getConnector(connectorId: ID!, workspaceId: ID!): Connector`, `testConnector(input: TestConnectorInput!): ConnectorHealth`.
- **Mutation:** `createConnector(input: CreateConnectorInput!): Connector!`, `updateConnector(input: UpdateConnectorInput!): Connector!`, `deleteConnector(connectorId: ID!, workspaceId: ID!): Boolean`.
- **ConnectorHealth:** `type ConnectorHealth { status: String! details: String timestamp: AWSDateTime }`.

### Directive for auth

- Use `@aws_cognito_user_pools(cognito_groups: ["admin", "workspace_manager"])` on connector mutations and on listConnectors, getConnector, testConnector (consistent with workspaces). If you later introduce “connector_user” for read-only, add that group and use it only for list/get in allowed workspaces.

### Resolver mapping

- In AppSync, map the new Query/Mutation fields to the same api-handler Lambda; the Powertools AppSync resolver will route by `fieldName` to the handlers in `routes/connectors.py` (e.g. `listConnectors` → resolver that returns list of connectors).

---

## Part 4: Frontend UI Components

### Step 4.1: Navigation and routing

- **File:** `lib/user-interface/react-app/src/components/navigation-panel.tsx`
  - Add a “Connectors” section (or link under Chatbot/Admin) visible when `appContext?.config.connectors_enabled` is true and user has admin or workspace_manager role. Pattern: same as RAG section (`if (appContext?.config.rag_enabled)`). Add item: `{ type: "link", text: "Connectors", href: "/connectors" }` (or under a “Data sources” section). Decide whether to place under “Chatbot” or “Admin” (recommend “Admin” or a dedicated “Data sources” section for consistency with workspace-level scope).

- **Router:** Ensure route `/connectors` exists (e.g. in `lib/user-interface/react-app/src/common/router/source-router.ts` or equivalent) and renders the Connectors page.

### Step 4.2: Connectors page and sub-views

- **New page:** `lib/user-interface/react-app/src/pages/connectors.tsx` (or under `pages/connectors/index.tsx` and a detail page).
  - **List view:** Table or list of connectors for the selected workspace (workspace selector at top, reusing existing workspace dropdown pattern). Columns: name, type, status, last checked, actions (Edit, Test, Delete). “Create connector” button.
  - **Create/Edit form:** Form for name, connector type (dropdown: Azure SQL, Dropbox, SharePoint), endpoint URL (optional if gateway is fixed per type), credentials (secret ARN selector or “create secret” flow), allowed resources (for Azure SQL: schemas, tables, views; for Dropbox/SharePoint optional). Application IDs multi-select for “enabled for applications.” Call GraphQL `createConnector` / `updateConnector` with validated input.
  - **Test connection:** Button that calls `testConnector` and shows status (healthy/unhealthy) and details.

### Step 4.3: API client and app context

- **New file:** `lib/user-interface/react-app/src/common/api-client/connectors-client.ts`
  - Methods: `listConnectors(workspaceId, connectorType?)`, `getConnector(connectorId, workspaceId)`, `createConnector(input)`, `updateConnector(input)`, `deleteConnector(connectorId, workspaceId)`, `testConnector(connectorId, workspaceId)`. Use the same GraphQL client pattern as `workspaces-client.ts` or `applications-client.ts`.

- **App context:** Ensure `connectors_enabled` (or similar) is available in `appContext.config` so the nav and connectors page can show/hide. This may come from a small config endpoint or from existing config that already includes feature flags; if not, add a minimal “features” or “config” field that includes `connectors_enabled` (e.g. from a health or config API that reads from deployment config or env).

### Step 4.4: Placeholders and UX

- Use Cloudscape components (SideNavigation, Table, Form, Button, Alert) consistent with the rest of the app. Use placeholder text for “Screenshots” in docs (Part 9.1). Error handling: display API errors (e.g. 403 Forbidden) with clear messages (“You don’t have access to this workspace” or “Only admins can create connectors”).

---

## Part 5: Chat Flow Integration

### Step 5.1: Citations and sources for connector results

**Goal:** (1) Add citations/sources for connector results. (2) Indicate which results came from which connector.

**Current behavior:** In `lib/model-interfaces/langchain/functions/request-handler/index.py`, `resolve_context_for_prompt` maps orchestrator result items to `connector_items` with `title`, `snippet`, `url` and formats them in a single block “External Data Source Results” via `_format_context_block`. The orchestrator already returns `items`, `metadata`, and `citations` (from `genai_core.connectors.base.QueryResult` and `_normalize_to_context_pack`). Metadata includes `connector_id`, `connector_type`, and `source`.

**Changes required:**

1. **Request-handler — context block formatting**
   - **File:** `lib/model-interfaces/langchain/functions/request-handler/index.py`
   - In the connector block construction (where `connector_items` is built from `result.get("items", [])`):
     - For each item, include **source attribution**: use `item.get("source")` or `item.get("connector_name")` and the connector’s display name or type from the selected_connector (e.g. `selected_connector.get("name")` or `selected_connector.get("connector_type")`). Add a visible “Source: &lt;connector name/type&gt;” (or “[1] … Source: Dropbox – My Folder”) in the formatted context so the model sees it.
     - Ensure each entry in the context block has a **citation label** the model can refer to (e.g. “[1]”, “[2]” already present; add “Source: &lt;connector_type/name&gt;” on the next line or in Notes).
   - Pass through **citations** from the orchestrator result: `result.get("citations", [])`. If the current flow only builds a single string context block, extend the flow so that connector citations are either:
     - (A) Inlined into the context block as numbered references (e.g. “[1] … URL: … Source: Dropbox”), or
     - (B) Returned separately and merged into the response metadata (see below).

2. **Orchestrator / normalizer**
   - **File:** `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py`
   - In `_normalize_to_context_pack`, ensure each `normalized_items` entry includes at least: `source` (connector type or name), `connector_id` (for reference), and if the MCP server returns per-item URLs or identifiers, preserve them as `source_url` or `url`. The existing `metadata` already has `connector_id`, `connector_type`, `source`. Enrich each item with `connector_name` or `connector_type` so the request-handler can format “Source: Azure SQL – dbo.customers” or “Source: Dropbox – Marketing”.

3. **Response metadata and history**
   - **File:** `lib/model-interfaces/langchain/functions/request-handler/adapters/base/base.py` (and any adapter that builds the final response)
   - When building `metadata` for the AI response (e.g. for admin users), include a **connector_sources** or **sources** structure if connector context was used: e.g. `connector_sources: [{ "connector_id": "...", "connector_type": "dropbox", "connector_name": "...", "citation_count": 3 }]` and/or the list of citations (title, url, source). This allows the UI to show “Sources” or “References” and “From: Dropbox (3), Azure SQL (2)”.
   - **Contract:** The request-handler’s `handle_run` receives the result of `resolve_context_for_prompt` only as a string today. To expose citations to the client, either:
     - Have `resolve_context_for_prompt` return a small structure `{ "context_block": str, "connector_citations": [...] }` and pass `connector_citations` through to the adapter so it can attach them to response metadata, or
     - Have the adapter read from a shared structure (e.g. a thread-local or context variable) set by `resolve_context_for_prompt` with the last run’s connector citations. Prefer the explicit return structure for clarity.

4. **UI (optional but recommended)**
   - In chat message component (e.g. `lib/user-interface/react-app/src/components/chatbot/chat-message.tsx` or metadata component), if `response.metadata.connector_sources` or `response.metadata.citations` exists, render a “Sources” or “References” section with links and “From: &lt;connector name&gt;” per source. Reuse existing RAG citation UX if present (e.g. `chat-message-metadata.tsx`).

**Summary table**

| What | Where |
|------|--------|
| Citations in context string | request-handler: add “Source: &lt;connector&gt;” and numbered refs in `_format_context_block` / connector_items |
| Per-item source | orchestrator: enrich items with connector_name/connector_type; request-handler: include in snippet or title |
| Citations in response metadata | request-handler: return or set connector_citations; adapter: add to metadata.connector_sources / citations |
| UI “Sources” | chat-message or chat-message-metadata: render metadata.connector_sources / citations |

### Step 5.2: Multiple connectors and mixed RAG + connector

- **Current:** `resolve_context_for_prompt` uses one selected_connector (first match or intent-suggested). To support **multiple connectors** in one query:
  - Extend the loop to iterate over all connectors that match intent (or a small set) and call `execute_query` for each; aggregate `items` and `citations` with a clear `connector_id`/`connector_type` on each item and in metadata. Then format one context block with multiple “Source: Connector A”, “Source: Connector B” sections or a single block with inline source labels.
- **RAG + connector:** Internal RAG and connector blocks are already concatenated in `resolve_context_for_prompt` (internal_block, web_block, connector_block). Ensure the titles are distinct (“Internal Knowledge Base Results”, “Internet Search Results”, “External Data Source Results”) and in metadata distinguish `source_type: "rag"` vs `source_type: "connector"` if you add a unified sources list.

---

## Part 6: Testing Strategy

### Step 6.1: Integration tests

**Files to update:**  
`integtests/connectors/test_connector_integration.py`, `integtests/connectors/test_connector_in_chat_flow.py`

**Test scenarios and assertions:**

1. **Create connector via API**
   - Call `createConnector` with valid input (workspaceId, name, type, endpoint, credentialsSecretArn or placeholder).  
   - Assert: response has `id`, `name`, `type`, `workspaceId`; no raw credentials in response.  
   - Store `connector_id` for later tests.

2. **List connectors for workspace**
   - Call `listConnectors(workspaceId)`.  
   - Assert: list is returned; created connector appears; optional filter by `connectorType`.

3. **Update connector**
   - Call `updateConnector` with same connectorId and workspaceId; change name or allowedResources.  
   - Assert: returned connector reflects update; getConnector returns updated data.

4. **Test connector health**
   - Call `testConnector(connectorId, workspaceId)`.  
   - Assert: response has `status` (“healthy” or “unhealthy”), `details`, `timestamp`.  
   - If MCP server is unavailable, accept “unhealthy” and optional skip in CI.

5. **Delete connector**
   - Call `deleteConnector(connectorId, workspaceId).  
   - Assert: success; listConnectors no longer returns this connector (or returns with status inactive if soft delete).

6. **Chat query with connector**
   - Create connector and application linked to workspace; send sendQuery with applicationId and a prompt that triggers connector intent (e.g. “Show me documents about X” or “Query customers”).  
   - Assert: response received; optional: response content or metadata includes connector-derived content or citations; metadata has connector_sources or citations when implemented.

7. **Chat without connectors (backward compatibility)**
   - Send sendQuery with a prompt that does not trigger connectors (or with workspace that has no connectors).  
   - Assert: normal response; no connector-related errors; behavior unchanged from pre-connector deployment.

**Mock strategy for MCP servers:**

- **Option A:** Use a small stub HTTP server (e.g. in pytest fixture) that implements a single MCP-like endpoint (e.g. POST /tools/health returning `{"raw_response": {"items": [], "citations": []}}`) and set connector endpoint URL to that stub in createConnector. Prefer this for integration tests that run against a real deployed API and table.
- **Option B:** Mock `genai_core.connectors.mcp_client.MCPClient.call_tool` in the request-handler/orchestrator path so that no network call is made; return a fixed `QueryResult`-shaped dict. Use for unit tests or when MCP is not deployed.
- **Recommendation:** Use Option A for `integtests/connectors` (real API + table, stub MCP); use Option B in unit tests for orchestrator/request-handler if added.

**Assertion patterns:**

- For CRUD: assert on presence and shape of fields (id, workspaceId, name, type, status); assert no `password`, `credentialsSecretArn` value in response (or masked).
- For chat: assert `session.history` has at least one message; optional `assert any("customer" in str(h.get("content", "")).lower() for h in session["history"])` or assert on metadata keys.
- For errors: assert 403 when user is not admin/workspace_manager on create/update/delete; assert 404 or “Connector not found” when getConnector with wrong workspace.

### Step 6.2: End-to-end manual test plan

1. Admin logs in.
2. Navigate to Connectors page (from nav).
3. Select a workspace; create Dropbox connector with name, type Dropbox, endpoint URL (gateway path), credentials (create secret in Secrets Manager, then select ARN or enter ARN).
4. Click “Test connection”; verify success (healthy).
5. Save connector (create or update).
6. As a user (or same admin), open Playground; select same workspace; send: “Show me documents about X”.
7. Verify response includes both RAG (if any) and Dropbox-sourced content where applicable.
8. Verify citations/sources: response or metadata shows “Source: Dropbox” or references with correct labels; links work if implemented.

---

## Part 7: Security & RBAC Implementation

### Step 7.1: Role-based access control

**Requirements:**  
Only admin or workspace_manager can create/update/delete connectors. All users in the workspace can use connectors in chat (via existing sendQuery path). Users in different workspaces cannot access each other’s connectors.

**Verification of admin/workspace_manager in connector API routes:**

- In `lib/chatbot-api/functions/api-handler/routes/connectors.py`, use the same pattern as `routes/applications.py` and `routes/workspaces.py`:
  - `permissions = UserPermissions(router)` (router from Powertools AppSync).
  - Decorate each resolver with `@permissions.approved_roles([permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE])` for create, update, delete, and testConnector. For listConnectors and getConnector, use the same roles and additionally validate that the requested `workspaceId` is in the set of workspaces the user is allowed to use (see below).
- **Reference:** `lib/shared/layers/python-sdk/python/genai_core/auth.py`: `ADMIN_ROLE = "admin"`, `WORKSPACES_MANAGER_ROLE = "workspace_manager"`. `approved_roles` returns `{"error": "Unauthorized"}` when the user’s role is not in the list; ensure AppSync/Lambda returns this as 403 Forbidden (or map in the handler to raise an exception that AppSync translates to 403).

**Where to add authorization checks:**

- In each connector resolver: after parsing input, call a shared helper e.g. `get_allowed_workspace_ids_for_user(user_id, user_roles)` (to be implemented per your user↔workspace model). If the request has `workspaceId`, require `workspace_id in allowed_workspace_ids`; else return 403. For createConnector, the workspace is in the input; for list/get/update/delete/test, workspace is in input or path. Until you have a per-user workspace membership table, you can allow all workspaces for admin/workspace_manager (matching current listWorkspaces behavior) but still enforce that listConnectors/getConnector only return data for the requested workspaceId (no cross-workspace listing by ID).
- **Playground workspace validation:** In `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py`, in the branch where there is no applicationId (playground), validate that `data.get("workspaceId")` is in the user’s allowed workspaces before forwarding the message. If not implemented yet, document as follow-up and add a TODO; see CONNECTOR_SECURITY_ARCHITECTURE_REVIEW.md recommendation 7.1.

**Error responses for unauthorized access:**

- Return a consistent structure that the client can interpret as 403: e.g. raise an exception that includes a message like “User is not authorized to use this workspace” or “Only admin or workspace_manager can create connectors”. Map `{"error": "Unauthorized"}` from `approved_roles` to an AppSync-friendly error (e.g. raise ValueError or CommonError with a clear message) so the client receives 403 and a message.

**How the existing role system works:**

- Cognito groups define roles (`admin`, `workspace_manager`, etc.). The api-handler receives `event["identity"]["claims"]["cognito:groups"]`. `UserPermissions(router).approved_roles([...])` checks that the user’s role is in the list. Workspace-level access is not yet enforced in the backend for listWorkspaces (all workspaces are returned); connector list/get should at least be scoped to the requested workspaceId and only for allowed roles.

### Step 7.2: Secrets Manager integration

**Requirements:**  
CreateConnector creates a secret in Secrets Manager; store only the secret ARN in the DynamoDB connector record; MCP servers read credentials at runtime; never expose credentials in API responses; mask secret ARN in responses if needed.

**Secret creation in create connector route:**

- In `routes/connectors.py` createConnector handler:
  - Accept `credentials` (object or JSON string) or `credentialsSecretArn`. If the client sends credentials (e.g. for first-time setup), call `boto3.client("secretsmanager").create_secret(Name=..., SecretString=json.dumps(credentials))`. Use a naming convention (see below); then set `credentials_secret_arn` in the connector config and do not store raw credentials in DynamoDB.
  - If the client sends an existing `credentialsSecretArn`, validate it exists (DescribeSecret or GetResourcePolicy) and that the caller is allowed to use it; then store that ARN in the connector item.

**Secret naming convention:**

- Example: `genai-connector-{connector_id}` or `{prefix}-connector-{workspace_id}-{connector_id}`. Ensure connector_id is set before creating the secret (e.g. generate UUID in API, then create secret with that ID in the name). Prefer a stable name so that update can find the same secret.

**Secret structure (JSON):**

- **Azure SQL:** `{"server": "...", "database": "...", "username": "...", "password": "..."}` or a single key `connectionString`.
- **Dropbox:** `{"access_token": "..."}` or `{"app_key": "...", "app_secret": "...", "refresh_token": "..."}` per Dropbox API.
- **SharePoint:** Similar key-value structure (site URL, client id/secret, etc.). Document in Part 9.

**Updating secrets when connector credentials change:**

- In updateConnector, if input includes a `credentials` payload, call `secretsmanager.put_secret_value(SecretId=existing_secret_arn, SecretString=...)`. If the connector was created with an existing ARN, do not overwrite that secret; document that “change credentials” may require a new secret and update of the connector’s `credentials_secret_arn`.

**Secret deletion when connector is deleted:**

- In deleteConnector, after soft-deleting the connector in DynamoDB, call `secretsmanager.delete_secret(SecretId=connector["credentials_secret_arn"], ForceDeleteWithoutRecovery=True)` (or schedule recovery window). Only delete if the connector record owned that secret (e.g. created by this app); if the ARN was user-provided, do not delete the secret, only remove the reference.

**MCP servers:**

- **Files:** `lib/connectors/azure-sql-mcp-server/connector.py`, `lib/connectors/dropbox-mcp-server/` (and SharePoint if present). Each ECS task should receive `CREDENTIALS_SECRET_ARN` (or similar) from the connector gateway/task definition. At runtime, the MCP server reads the secret via `boto3.client("secretsmanager").get_secret_value(SecretId=...)`. Ensure the ECS task role has `secretsmanager:GetSecretValue` on the relevant secret(s). Per-connector tasks may get the ARN from the registry at startup or from an env var injected per task.

---

## Part 8: Deployment & Migration

### Step 8.1: CloudFormation migration

**Scenario:** Existing deployments have `connectors.enabled=false` or no connectors config.

**Can the table be added without data loss?**  
Yes. The connector table is created only when `connectors.enabled` is true. Adding it later is a new resource; no existing table is modified. No migration of existing data is needed.

**Migration scripts:**  
None required for the table itself. If you later backfill connector records from an external store, that would be a one-off script (not in scope here).

**Enabling connectors on an existing deployment:**

1. Update `config.json`: set `connectors.enabled` to `true` and set per-type flags (e.g. `connectors.azureSql.enabled`, `connectors.dropbox.enabled`).
2. Run `npm run cdk deploy`. CDK will create ConnectorDynamoDBTables, Connector Gateway (if any type enabled), add `CONNECTORS_TABLE_NAME` and table access to api-handler and (after Part 1.3) to request-handler.
3. No downtime required; existing RAG, chat, workspaces, and applications are unchanged.

**New installations:**  
Same as above; ensure config has `connectors.enabled: true` and desired connector types before first deploy.

**Rollback:**  
Set `connectors.enabled` to `false` and redeploy. CDK will remove the connector table and gateway (if removal policy is DESTROY). **Warning:** Destroying the table deletes all connector records. Use RETAIN if you want to keep the table. Restore from backup if you need to recover data. After rollback, request-handler and api-handler will no longer have `CONNECTORS_TABLE_NAME`; connector code paths will be skipped (no table name env).

**Feature flag:**  
Runtime behavior is “connectors on if CONNECTORS_TABLE_NAME is set.” There is no separate runtime flag to “disable connectors after enabling” without redeploying with `connectors.enabled: false`. To support a runtime kill switch, you could add an SSM Parameter or DynamoDB flag read by the API and request-handler; that is not in the current design.

### Step 8.2: Configuration file updates

**File:** `bin/config.json` (or root `config.json`; see `bin/default-config.json` and `cli/magic-config.ts` for how config is loaded).

**Required additions (already present in default-config.json; document and validate):**

- `connectors.enabled` (boolean, default false): Master switch for connector table and gateway.
- `connectors.azureSql.enabled` (boolean, default false): Deploy Azure SQL MCP service.
- `connectors.sharepoint.enabled` (boolean, default false): Deploy SharePoint MCP service.
- `connectors.dropbox.enabled` (boolean, default false): Deploy Dropbox MCP service.
- `connectors.vpcId` (string, optional): Reserved for VPC for connector gateway; currently not used by CDK (see MCP_CONNECTORS_ENABLEMENT_AUDIT.md).

**Documentation:** In `docs/guide/config.md` (or connector-deploy-and-config.md), document each key, type, default, and effect (deploy-time vs runtime). Runtime behavior: only `CONNECTORS_TABLE_NAME` is read by Lambda; config.json is not passed to Lambda at runtime.

---

## Part 9: Documentation

### Step 9.1: User documentation (admin guide) outline

1. **How to enable connectors** — Set `connectors.enabled` and per-type flags in config; deploy; verify Connectors page appears.
2. **How to create a Dropbox connector** — Navigate to Connectors → Create; choose Dropbox; enter name, endpoint (or use default gateway path); create or select secret (token/refresh); save. [Screenshot placeholder.]
3. **How to create a SharePoint connector** — Same flow; document site URL, client id/secret or token in secret. [Screenshot placeholder.]
4. **How to create an Azure SQL connector** — Same flow; document server, database, username, password (or connection string) in secret; optional allowed schemas/tables. [Screenshot placeholder.]
5. **How to test connectors** — Use “Test connection” on the connector card/list; interpret healthy vs unhealthy.
6. **Troubleshooting connection issues** — Check secret exists and ECS task has GetSecretValue; check ALB and target health; check MCP server logs in CloudWatch.
7. **Security best practices** — Store credentials only in Secrets Manager; use least-privilege IAM for ECS; rotate secrets periodically; do not share workspace IDs across tenants.

### Step 9.2: Developer documentation outline

1. **Architecture diagram** — Components: UI → GraphQL (api-handler) → Connector Registry (DynamoDB); request-handler → resolve_context_for_prompt → registry + orchestrator → MCP client → Connector Gateway (ALB + ECS MCP servers). Flow for create/list vs chat flow.
2. **How to add a new connector type** — Add MCP server image and task in Connector Gateway; add type to config (e.g. `connectors.newType.enabled`); extend GraphQL input and registry schema; implement tools (e.g. search, health) in the new MCP server; document secret shape.
3. **API reference** — List endpoints (createConnector, listConnectors, getConnector, updateConnector, deleteConnector, testConnector); input/output schemas; error codes (403, 404).
4. **Database schema** — Table name, PK/SK (connector_id, workspace_id), GSI by_workspace; attribute list and meaning (connector_type, endpoint, credentials_secret_arn, allowed_resources, application_ids, status, timestamps).
5. **Troubleshooting** — Common errors (CONNECTORS_TABLE_NAME not set, Connector not found, Health check failed); where to look (CloudWatch logs for api-handler, request-handler, ECS tasks); how to verify table and env in Lambda.

---

## Part 10: Monitoring & Observability

### Step 10.1: CloudWatch metrics

**Metrics to track:**

- Connector usage count (per workspace or globally): number of chat runs that used at least one connector.
- Connector success/failure rate: success = execute_query returned without exception; failure = exception or unhealthy.
- Connector response time: time from start of execute_query to return (or per MCP call).
- Connector error types: dimension on error type (e.g. timeout, validation, MCP error).

**Where to add metric logging:**

- **Orchestrator:** `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py`: in `execute_query`, after the MCP call and normalization, publish a metric (e.g. `ConnectorQuerySuccess`, count 1, dimensions: connector_type, workspace_id). In the except path, publish `ConnectorQueryFailure` with dimension error_type.
- **Request-handler:** In `resolve_context_for_prompt`, when connector context is used, optionally increment a metric `ConnectorContextUsed` (count 1, dimensions: workspace_id). Use the same namespace as the rest of the app.

**Namespace and names:**

- Namespace: e.g. `GenAIChatbot/Connectors` or reuse existing app namespace.
- Metric names: `ConnectorQuerySuccess`, `ConnectorQueryFailure`, `ConnectorContextUsed`, `ConnectorResponseTime` (if you add timing).

**Dashboard:** Create a CloudWatch dashboard with widgets: count of ConnectorQuerySuccess and ConnectorQueryFailure over time; average ConnectorResponseTime; breakdown by connector_type.

### Step 10.2: Logging

**Requirements:** Log connector usage in chat flow; log connector API operations (create, update, delete); log connector health check results.

**Log format:** Structured JSON (already used via Lambda Powertools Logger). Include:

- `workspace_id`, `connector_id`, `connector_type`, `operation` (e.g. createConnector, listConnectors, execute_query, test_connector), `status` (success/failure), `user_id` (or omit for PII policy), `duration_ms` (optional).

**Where to add logging:**

- **API routes (connectors.py):** At start of each resolver log operation and workspace_id/connector_id; before return log status and duration.
- **Orchestrator:** Log at start of execute_query (connector_id, workspace_id); on success log item count; on exception log warning with error type.
- **Request-handler:** In resolve_context_for_prompt, when connector block is used, log info with workspace_id, connector_id, and whether intent matched.

**Key fields:** workspace_id, connector_id, connector_type, operation, status, error_message (if failed), duration_ms.

---

## Implementation Order & Dependencies

```
Part 1 (Fix registry + wire request-handler)
    ↓
Part 2 (Backend API routes) + Part 7.1 (RBAC) + Part 7.2 (Secrets)
    ↓
Part 3 (GraphQL schema + resolver mapping)
    ↓
Part 4 (Frontend: nav, page, client, context)
    ↓
Part 5 (Chat flow: citations + source attribution)
    ↓
Part 6 (Integration tests) — can start after Part 2/3
Part 8 (Deployment docs + config) — in parallel
Part 9 (Documentation) — after UI and API stable
Part 10 (Metrics + logging) — with Part 2 and Part 5
```

- **Part 1** must be done first so that registry calls succeed and chat can use connectors.
- **Part 2 and Part 3** can be done together (API + schema).
- **Part 7** should be implemented with Part 2 (auth and secrets in the same routes).
- **Part 5** can be refined after Part 1 is deployed (citations and metadata).
- **Part 6** depends on Part 2/3 and optionally Part 4 for full E2E.

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Registry composite key not fixed; get_item fails in production | Fix in Part 1.1 and 1.2; add unit tests for registry with a local DynamoDB or mock. |
| Request-handler never gets CONNECTORS_TABLE_NAME | Implement Part 1.3 and verify env in deployed Lambda after deploy. |
| Playground workspace spoofing (user B uses WK1 connectors) | Implement workspace validation in send-query resolver (Part 7.1) and document. |
| Secrets in API response | Never return GetSecretValue in API; store only ARN; mask ARN in list/get if required by policy. |
| Breaking existing deployments | Connectors are additive; when disabled, no new resources; request-handler without env skips connector block. |
| MCP server unreachable from Lambda | Ensure Lambda VPC (if used) can reach Connector Gateway ALB (security groups, subnets). |

---

## Estimated Effort

| Part | Effort (person-days) |
|------|----------------------|
| Part 1 (infrastructure fixes) | 1–2 |
| Part 2 (API routes) | 2–3 |
| Part 3 (GraphQL schema) | 0.5–1 |
| Part 4 (Frontend) | 2–3 |
| Part 5 (Chat flow + citations) | 1.5–2 |
| Part 6 (Integration tests) | 1.5–2 |
| Part 7 (RBAC + Secrets) | 2–3 |
| Part 8 (Deployment + config) | 0.5–1 |
| Part 9 (Documentation) | 1–2 |
| Part 10 (Observability) | 0.5–1 |
| **Total** | **~15–25** |

---

## Ambiguities and Design Decisions for Stakeholders

1. **Workspace membership:** Backend does not yet enforce “user U can only use workspace W.” listWorkspaces returns all workspaces for admin/workspace_manager. Confirm whether connector list/get and playground sendQuery should restrict to a future “user_workspaces” or “group_workspaces” model, or keep “all workspaces for admin/workspace_manager” for now.
2. **test_connector(workspace_id):** Should testConnector require workspace_id (recommended) or allow global lookup by connector_id?
3. **Connector visibility for “chatbot_user”:** Should non-admin users have listConnectors/getConnector for workspaces they belong to (read-only), or is connector management strictly admin/workspace_manager only?
4. **Citation format in UI:** Exact format of “Sources” (e.g. inline refs vs sidebar vs tooltip) and whether to show per-connector breakdown in the message metadata.
5. **Runtime feature flag:** Should there be an SSM/Parameter Store flag to disable connector usage at runtime without redeploying with connectors.enabled=false?

---

*This plan is implementation-only; no production code is written in this document. All file paths and method names are to be implemented per existing codebase patterns.*
