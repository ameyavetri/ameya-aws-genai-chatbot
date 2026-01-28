# Cursor Implementation Instruction Set: MCP-Based Data Source Connectors

This document is the **step-by-step implementation plan** for adding MCP-based data source connectors to the AWS GenAI LLM Chatbot. **Do not implement code in this step**—use this solely as the instruction set for the next implementation phase.

**Source-of-truth:** `IMPLEMENTATION_SUMMARY.md`, `MCP_CONNECTORS_ARCHITECTURE.md`

**Constraints:** Additive-only; no breaking changes to chat, RAG, web search, auth, RBAC, schema, or data import. Fail-safe: connector failures must not break chat responses.

---

## PHASE 0 — Preflight & Baseline Safety

### Goal
Establish a clean baseline and ensure all existing tests pass before any connector changes.

### Exact Commands to Run (in order)
1. **`npm run build`** — Amplify codegen + TypeScript compile  
   - Working directory: repo root  
   - Success: no compile errors; `dist/` and generated code updated  

2. **`npm run test`** — Jest unit tests (TypeScript/CDK)  
   - Success: all tests in `tests/` pass  

3. **`npm run pytest`** — Python unit tests  
   - Runs: `pytest tests/`  
   - Success: all tests in `tests/` pass  

4. **`npm run integtest`** — Integration tests  
   - Runs: `pytest integtests/`  
   - Success: all tests in `integtests/` pass (or skip if env/setup not available)  

### Files/Folders to Inspect (no edits)
- **`package.json`** — Confirm scripts: `build`, `test`, `pytest`, `integtest`  
- **`tests/`** — Jest and pytest locations  
- **`integtests/`** — Integration test layout  

### Verification Outputs / Sanity Checks
- `npm run build` exits 0; no "TS2304" or "Cannot find module"  
- `npm run test` exits 0; no failing Jest tests  
- `npm run pytest` exits 0; no failing pytest tests  
- `npm run integtest` exits 0 or is explicitly skipped with documented reason  

### Required Precondition
**Any currently failing test must be fixed before proceeding.** Document the failing test names and fix them in a separate change. Do not start Phase 1 until all four command runs succeed (or integtest is formally excluded with approval).

### Risk Level
**None** — inspection and run-only.

### Rollback
N/A.

---

## PHASE 1 — Configuration & Feature Flag Plumbing (SeedFarmer → config.json → CDK)

### Goal
Add connector-related feature flags and config so that **defaults are off (false)** and no runtime or CDK behavior changes until explicitly enabled.

### Exact Files/Folders to Create/Modify

| Path | Action |
|------|--------|
| `aws-genai-llm-chatbot/capability.yaml` | MODIFY |
| `cli/magic-config.ts` | MODIFY |
| `lib/shared/types.ts` | MODIFY |

### Minimal-Diff Guidance

#### 1. `aws-genai-llm-chatbot/capability.yaml`
- In `input:`, append new entries (preserve existing order and structure):
  - **CONNECTORS_ENABLE** — type: Boolean, defaultValue: **false**, description: Enable data source connectors via MCP, isRequired: false  
  - **CONNECTORS_AZURE_SQL_ENABLE** — type: Boolean, defaultValue: **false**, label/description for Azure SQL connector, isRequired: false  
  - **CONNECTORS_SHAREPOINT_ENABLE** — type: Boolean, defaultValue: **false**, isRequired: false  
  - **CONNECTORS_DROPBOX_ENABLE** — type: Boolean, defaultValue: **false**, isRequired: false  
  - **CONNECTORS_VPC_ID** — type: String, defaultValue: `""`, description: VPC ID for connector gateway (required when connectors enabled), isRequired: false  
- Follow the exact YAML style of existing inputs (e.g. BEDROCK_ENABLE, RAG_ENABLE).

#### 2. `cli/magic-config.ts`
- Locate where the final `SystemConfig` object is built (e.g. `defaultConfig` or equivalent).
- Add a **connectors** section only when building the config object:
  - Read from prompts/options or from existing config when loading from `./bin/config.json`:
    - `CONNECTORS_ENABLE` → `connectors.enabled` (default **false**)
    - `CONNECTORS_AZURE_SQL_ENABLE` → `connectors.azureSql.enabled` (default **false**)
    - `CONNECTORS_SHAREPOINT_ENABLE` → `connectors.sharepoint.enabled` (default **false**)
    - `CONNECTORS_DROPBOX_ENABLE` → `connectors.dropbox.enabled` (default **false**)
    - `CONNECTORS_VPC_ID` → `connectors.vpcId` (default `undefined` or `""`)
- When reading from existing `config.json`, map `config.connectors` into the in-memory options so "create config" flow can prefill these.
- Ensure that if `connectors` is missing from an existing config.json, the app does not assume it is enabled; treat missing as disabled.

#### 3. `lib/shared/types.ts`
- In the `SystemConfig` interface, add an **optional** property:
  - `connectors?: { enabled?: boolean; vpcId?: string; azureSql?: { enabled?: boolean }; sharepoint?: { enabled?: boolean }; dropbox?: { enabled?: boolean }; }`
- No existing property types or names may change.

### Keeping Defaults Off
- In capability.yaml: every new connector-related input uses **defaultValue: false** (or empty string for VPC).
- In magic-config: when constructing config from scratch, set `connectors.enabled = false` and each per-connector `enabled = false` unless the user explicitly opts in.
- In types.ts: `connectors` is optional; CDK and app code must use `config.connectors?.enabled ?? false` and similarly for nested flags.

### Commands to Run
- `npm run build`  
- `npm run test`  
- `npm run pytest`  

### Expected Verification
- Build succeeds.
- Existing tests pass.
- With default/generated config, `config.connectors?.enabled` is false when connectors are not explicitly enabled.

### Risk Level
**Low** — additive config and types only.

### Rollback
Revert the three file edits; no persistent state or resources are created in this phase.

---

## PHASE 2 — Infrastructure: Connector Registry Table + Gateway (CDK)

### Goal
Add CDK constructs for the connector DynamoDB table and the connector gateway (ECS Fargate + ALB), **only when** `config.connectors?.enabled === true`. When the flag is false, nothing new is created and existing stacks are unchanged.

### Exact Files/Folders to Create/Modify

| Path | Action |
|------|--------|
| `lib/connectors/connector-dynamodb-tables/index.ts` | CREATE (new construct) |
| `lib/connectors/connector-gateway/index.ts` | CREATE (new construct) |
| `lib/aws-genai-llm-chatbot-stack.ts` | MODIFY |

### Minimal-Diff Guidance

#### 1. `lib/connectors/connector-dynamodb-tables/index.ts` (new)
- New CDK construct **ConnectorDynamoDBTables**.
- Outputs:
  - A DynamoDB table named `{prefix}-connectors` (use config.prefix).
  - Key schema: **PK** `connector_id` (String), **SK** `workspace_id` (String).
  - GSI **by_workspace**: **PK** `workspace_id`, **SK** `connector_type`.
  - Props: accept `kmsKey`, `retainOnDelete`, `deletionProtection` (or equivalent from main stack), consistent with existing table constructs in the repo.
- No other tables or GSIs; do not change existing RAG/workspace/session tables.

#### 2. `lib/connectors/connector-gateway/index.ts` (new)
- New CDK construct **ConnectorGateway**.
- Responsibilities:
  - Define or accept VPC (from config or existing stack VPC).
  - ECS Fargate cluster (or use shared cluster if one exists).
  - Internal Application Load Balancer.
  - One ECS service per **enabled** connector type (e.g. Azure SQL when `config.connectors?.azureSql?.enabled`).
  - Target groups per connector type; path or host-based routing to the correct service.
- Props: e.g. `vpc`, `azureSqlEnabled`, `sharepointEnabled`, `dropboxEnabled`, `secretsManager` (for task role to access secret ARNs only).
- Ensure ECS task roles can read from Secrets Manager only the secrets that will hold connector credentials (by ARN); do not pass secret values in environment variables.
- Security groups: allow inbound only from ALB and from Lambda (or VPC endpoint) that will call the gateway; no public internet ingress.

#### 3. `lib/aws-genai-llm-chatbot-stack.ts`
- Import the new constructs.
- After existing constructs that do not depend on connectors, add a **conditional** block:
  - `if (props.config.connectors?.enabled) { ... }`
  - Inside:
    - Instantiate **ConnectorDynamoDBTables** with appropriate props (prefix, KMS, retain, deletion protection).
    - Instantiate **ConnectorGateway** with VPC and per-connector flags from config.
    - Set **api-handler Lambda** environment variable: `CONNECTORS_TABLE_NAME` = connector table name.
    - Grant api-handler Lambda: `connectorTables.connectorsTable.grantReadWriteData(apiHandler)` (or equivalent access to the new table).
    - Grant api-handler Lambda permission to **read secret ARNs** only (e.g. `secretsmanager:DescribeSecret`, `secretsmanager:GetResourcePolicy` if needed for validation; actual `GetSecretValue` can be restricted to connector-orchestration code paths or to a dedicated connector execution role later).
- **Important:** api-handler must get **read/write** to the connectors table and **read ARNs/metadata** for secrets as needed; document that secret **values** are only fetched by code that runs with a role allowed to call `GetSecretValue` (e.g. MCP server task role or a dedicated connector Lambda).

### IAM Summary for api-handler Lambda
- **Connectors table:** `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`, `BatchGetItem` on the new table resource.
- **Secrets:** Prefer storing only ARNs in DynamoDB; if api-handler needs to pass ARNs to other components, it does not need `GetSecretValue`. If the design requires api-handler to resolve ARNs to resource names only, keep permission minimal (e.g. `DescribeSecret`). Actual credential retrieval must happen in ECS task role or connector execution path, not in api-handler unless specified.

### Commands to Run
- `npm run build`  
- `npm run test`  

### Expected Verification
- `cdk diff` or `cdk synth` with **connectors.enabled = false** shows **no** new connector table or gateway resources.
- With **connectors.enabled = true** (and required VPC etc.), synth shows new DynamoDB table, ECS cluster/service(s), ALB, and updated Lambda env/grants.

### Risk Level
**Medium** — new infra; conditional wiring keeps risk bounded.

### Rollback
Set `connectors.enabled` to false and redeploy; optionally remove the new construct instantiations and delete the connector table/gateway stack resources via CDK destroy or console.

---

## PHASE 3 — API Layer: GraphQL Schema + Resolvers (Additive Only)

### Goal
Expose connector CRUD, test, and query operations via GraphQL and route them to a new connector route module. All changes are **additive**: no existing types, queries, or mutations are renamed or removed.

### Exact Files/Folders to Create/Modify

| Path | Action |
|------|--------|
| `lib/chatbot-api/schema/schema.graphql` | MODIFY (append only) |
| `lib/chatbot-api/functions/api-handler/routes/connectors.py` | CREATE |
| `lib/chatbot-api/functions/api-handler/index.py` | MODIFY |

### Minimal-Diff Guidance

#### 1. `lib/chatbot-api/schema/schema.graphql`
- **Append** new types and operations at the end of the file (or in a dedicated section). Do not edit existing type definitions or field names.
- Add:
  - Types: `Connector`, `ConnectorResources`, `ConnectorHealth`, `ConnectorQueryResult`, `ConnectorResultItem`, `ConnectorMetadata`.
  - Inputs: `CreateConnectorInput`, `ConnectorEndpointInput`, `ConnectorResourcesInput`, `TestConnectorInput`, `RunConnectorQueryInput`.
  - **extend type Query** with: `listConnectors(workspaceId: String!): [Connector!]!`, `getConnector(connectorId: String!): Connector`, `testConnector(input: TestConnectorInput!): ConnectorHealth!`, `runConnectorQuery(input: RunConnectorQueryInput!): ConnectorQueryResult!`.
  - **extend type Mutation** with: `createConnector(input: CreateConnectorInput!): Connector!`, `updateConnector(connectorId: String!, input: CreateConnectorInput!): Connector!`, `deleteConnector(connectorId: String!): Boolean!`.
- Use existing directive pattern (e.g. `@aws_cognito_user_pools`) and, if used elsewhere, group-based access (e.g. `cognito_groups: ["admin", "workspace_manager"]`) for create/test/update/delete; allow authenticated users for `runConnectorQuery` where applicable, with authorization enforced in the resolver (application/workspace scoping).

#### 2. `lib/chatbot-api/functions/api-handler/routes/connectors.py` (new)
- New route module consistent with `routes/workspaces.py`, `routes/applications.py`, etc.
- Use existing patterns: `Router()`, `Logger`, `Tracer`, `UserPermissions(router)`, Pydantic request models, `genai_core.types.CommonError` for errors.
- Resolvers to implement (names matching schema):
  - `listConnectors(workspaceId)` → call registry list, return list of connector DTOs.
  - `getConnector(connectorId)` → call registry get, return one connector or null.
  - `createConnector(input)` → validate input, call registry create, return created connector.
  - `updateConnector(connectorId, input)` → validate, call registry update, return updated connector.
  - `deleteConnector(connectorId)` → call registry delete, return Boolean.
  - `testConnector(input)` → call orchestrator (or MCP client) health/test, return ConnectorHealth.
  - `runConnectorQuery(input)` → call orchestrator execute_query, return ConnectorQueryResult (items, metadata, citations).
- RBAC: use `approved_roles([permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE])` for create/update/delete/test; for `runConnectorQuery`, allow a user role and enforce inside the resolver that the request’s workspace/application is allowed to use the connector.
- Validators: use `ID_FIELD_VALIDATION`, `SAFE_PROMPT_STR_REGEX` (or equivalent) from `common.constant` for IDs and free-text inputs; restrict `type` to e.g. `azure_sql | sharepoint | dropbox` in Pydantic.

#### 3. `lib/chatbot-api/functions/api-handler/index.py`
- Add: `from routes.connectors import router as connectors_router` and `app.include_router(connectors_router)`.
- Do not change order or behavior of other routers unless required for dependency injection (e.g. passing table names via app state if your pattern uses it).

### Do Not Break Existing Schema — Checklist
- [ ] No existing `type` or `input` name is renamed or removed.
- [ ] No existing `Query` or `Mutation` field is removed or changed in argument types.
- [ ] All new fields are added via `extend type Query` / `extend type Mutation` or new types.
- [ ] Schema remains parseable and passes any existing schema lint/validate steps.

### Commands to Run
- `npm run build`  
- `npm run test`  
- `npm run pytest` (including any schema or API-handler tests).

### Expected Verification
- Build succeeds; GraphQL schema loads without errors.
- Existing GraphQL and route tests still pass.
- New connector resolvers are registered and resolvable by field name.

### Risk Level
**Low** — additive schema and new route file; existing routes untouched.

### Rollback
Remove the connector schema block, delete `routes/connectors.py`, and revert `index.py` router inclusion.

---

## PHASE 4 — Core SDK: genai_core Connectors Orchestration (No MCP Servers Yet)

### Goal
Implement the Python orchestration layer under `genai_core.connectors` so that registry, MCP client, intent, safety, and orchestrator exist and can be called by the API and (later) by the chat flow. No real MCP servers are called yet; MCP client can stub or mock.

### Exact Files/Folders to Create

| Path | Responsibility |
|------|----------------|
| `lib/shared/layers/python-sdk/python/genai_core/connectors/__init__.py` | Re-export public API: `registry`, `orchestrator`, `base`, `safety`, `intent`, `mcp_client`. |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/base.py` | **BaseConnector** ABC; dataclasses **SchemaMetadata**, **QueryResult**; optional **incremental_sync** stub. |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` | **ConnectorRegistry(table_name)**; methods: `create_connector`, `get_connector`, `list_connectors`, `update_connector`, `delete_connector`, `get_connectors_for_application`. |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/mcp_client.py` | **MCPClient(endpoint)**; `call_tool(tool_name, arguments)` returning a normalized dict; optional `list_tools()`. Can use a stub that returns structure without a real network call until Phase 6. |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py` | **execute_query(workspace_id, connector_id, user_prompt, intent=None, params=None, application_id=None)**; **test_connector(connector_id)**; internal: get connector from registry, RBAC check by application_id, intent classification if needed, safety validation, call MCP client, normalize to context pack. |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/intent.py` | **classify_intent(user_prompt, connector_type, schema)** returning `{intent, params}`; **detect_connector_intent(prompt)** returning `{needs_connector, connector_id, ...}` for use in chat flow. Can start with rule-based or keyword logic. |
| `lib/shared/layers/python-sdk/python/genai_core/connectors/safety.py` | **validate_query(connector_type, intent, params, allowed_resources)**; for `azure_sql`: **validate_sql(sql_template, params, allowed_resources)** enforcing: block keywords (DROP, DELETE, UPDATE, INSERT, EXEC, xp_cmdshell, sp_, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, BACKUP, RESTORE), read-only (SELECT only), allowlist for schemas/tables/views, LIMIT/TOP required, row cap and timeout in allowed_resources or defaults (e.g. 1000, 30s). |

### Minimal APIs (Signatures)

- **registry.ConnectorRegistry(table_name).create_connector(workspace_id, connector_config) -> str** (connector_id)  
- **registry.get_connector(connector_id) -> dict**  
- **registry.list_connectors(workspace_id, connector_type=None) -> list**  
- **registry.get_connectors_for_application(workspace_id, application_id) -> list**  
- **orchestrator.execute_query(...) -> {items, metadata, citations}**  
- **orchestrator.test_connector(connector_id) -> {status, details, timestamp}**  
- **safety.validate_sql(sql_template, params, allowed_resources)** raises on violation  
- **intent.detect_connector_intent(prompt) -> {needs_connector, connector_id?, intent?, params?}**  
- **intent.classify_intent(user_prompt, connector_type, schema) -> {intent, params}**

### Safety Rules (Centralized in safety.py)
- Block list of SQL keywords (as in MCP_CONNECTORS_ARCHITECTURE.md).
- Only SELECT allowed.
- Schemas/tables/views must be in allowed_resources.
- LIMIT/TOP required; max rows and timeout from connector config or defaults (1000, 30s).
- Parameterization: all user inputs must be passed as parameters, not concatenated into SQL.

### Commands to Run
- `npm run build` (if any TS references layer)  
- `npm run pytest` (target `tests/shared/layers/python-sdk/genai_core/` or equivalent for connector tests once added in Phase 7).

### Expected Verification
- Import `genai_core.connectors` and submodules without errors.
- Unit tests (Phase 7) will validate registry CRUD, safety validation, and intent helpers; until then, minimal smoke test or manual import is sufficient.

### Risk Level
**Low** — new package under genai_core; no changes to existing genai_core modules.

### Rollback
Remove the `genai_core/connectors` directory and any imports from it in api-handler and request-handler.

---

## PHASE 5 — Chat Flow Hook: Context Injection (Fail-Safe)

### Goal
Use the existing `resolve_context_for_prompt()` function to optionally inject connector-sourced context. Behavior must remain fail-safe: any exception in connector path must be caught and must **not** break the chat response; existing RAG and web paths must not regress.

### Exact File and Function to Modify

| Path | Change |
|------|--------|
| `lib/model-interfaces/langchain/functions/request-handler/index.py` | MODIFY `resolve_context_for_prompt` (and optionally its single call site to pass `application_id` if available). |

### Current Signature (keep backward compatible)
```text
def resolve_context_for_prompt(prompt: str, source_mode: str, workspace_id: str, user_id: str) -> str:
```
- Add an **optional** parameter: `application_id: Optional[str] = None` so existing callers need not change.

### Call Site
- In the same file, the call is around lines 271–276 (in the “QA mode or general” branch). Update the call to pass `application_id=data.get("applicationId")` if that key exists in the message payload; otherwise pass `None`.

### Minimal Additive Logic Inside `resolve_context_for_prompt`
1. **Guard:** If connectors are disabled at runtime (e.g. no env var `CONNECTORS_TABLE_NAME` or explicit feature flag), skip the connector block entirely.
2. **Guard:** If `workspace_id` or `application_id` is missing, skip connector context.
3. **Try/except:** Wrap all connector logic in `try/except`; on any exception, log a warning and set `connector_items = []`.
4. **Steps inside try:**
   - Call `genai_core.connectors.registry.get_connectors_for_application(workspace_id, application_id)` (if application_id is None, you may use a registry method that returns workspace-level connectors only—implement that contract in Phase 4).
   - If the list is empty, skip.
   - Call `genai_core.connectors.intent.detect_connector_intent(prompt)`. If `not needs_connector`, skip.
   - Choose which connector(s) to use (e.g. by intent or first allowed); ensure the chosen connector is in the allowed list.
   - Call `genai_core.connectors.orchestrator.execute_query(...)` with workspace_id, connector_id, user_prompt, application_id, etc.
   - Map result to the same shape as existing context items: `{ "title": ..., "snippet": ..., "url": ... }` (use “External Data Source” or similar for title; snippet = content; url = source/citation if available).
5. **Format:** Reuse `_format_context_block("External Data Source Results", connector_items)` and append that block to `parts` only if non-empty.
6. **Order:** Append connector block after internal and web blocks; do not change how internal or web blocks are built.

### No-Regression Checklist for RAG and Web
- [ ] When `CONNECTORS_TABLE_NAME` is unset or connectors disabled, connector block is never run and the function behaves as today.
- [ ] When `workspace_id` is None or missing, no connector calls are made.
- [ ] Any exception in connector code (registry, intent, orchestrator, network) is caught and results in empty connector context, not in a raised exception.
- [ ] Internal RAG logic and web search logic are unchanged; no edits to those branches.
- [ ] The returned string still has the same overall structure (blocks separated by `\n\n`), with at most one additional block for connectors.

### Commands to Run
- `npm run build`  
- `npm run pytest` (including `tests/model-interfaces/langchain/...` if present).

### Expected Verification
- With connectors disabled or table name unset, chat flow continues to work as before.
- With connectors enabled and a deliberate connector failure (e.g. bad connector_id), chat still returns a response and only the connector block is empty.

### Risk Level
**Medium** — touches the critical context path; mitigations are guarding and try/except.

### Rollback
Revert changes to `resolve_context_for_prompt` and the call site; remove optional `application_id` and any imports of `genai_core.connectors` from the request-handler.

---

## PHASE 6 — MCP Server: Azure SQL Connector (First Working Connector)

### Goal
Deliver a minimal but working Azure SQL MCP server running in ECS, with schema discovery, a small tool set (health, discover_schema, query_*), and safety enforced at the server.

### Exact Files/Folders to Create

| Path | Purpose |
|------|---------|
| `lib/connectors/azure-sql-mcp-server/` | Root for the first MCP server |
| `lib/connectors/azure-sql-mcp-server/Dockerfile` | Multi-stage build; base image, pip install, run main.py |
| `lib/connectors/azure-sql-mcp-server/requirements.txt` | Dependencies: MCP SDK (or stdio/HTTP impl), pyodbc, boto3, etc. |
| `lib/connectors/azure-sql-mcp-server/main.py` | MCP server entry: load config from env, start server, register tools (health, discover_schema, query_*). |
| `lib/connectors/azure-sql-mcp-server/connector.py` | Azure SQL implementation: connection pooling, `discover_schema()`, `query(intent, params)` with safety checks. |
| `lib/connectors/azure-sql-mcp-server/schema_discovery.py` | Query INFORMATION_SCHEMA for allowed schemas/tables/views; return structure usable by tools. |
| `lib/connectors/azure-sql-mcp-server/safety.py` | Server-side SQL validation: same rules as genai_core.connectors.safety (keyword block, read-only, allowlist, LIMIT/TOP, timeout, row cap). |

### Environment / ECS Configuration
- **Endpoint config:** Passed via task definition env: e.g. `CONNECTOR_TYPE=azure_sql`, `ALLOWED_RESOURCES` (JSON string).
- **allowed_resources:** JSON with `schemas`, `tables`, `views`; server must restrict all queries to these.
- **Secret ARN:** Task role must have `secretsmanager:GetSecretValue` on that ARN. Server reads connection string (or equivalent) from Secrets Manager at startup or per-request; do not put credentials in env vars.

### MCP Server Fetching Secrets
- ECS task role is granted permission on the secret ARN provided in the connector registration.
- In `main.py` or `connector.py`: use boto3 `secretsmanager.get_secret_value(SecretId=secret_arn)` to retrieve the value; cache in memory if desired, but never log or expose it.
- Secret ARN comes from task env (e.g. `CREDENTIALS_SECRET_ARN`) set by the CDK when creating the task definition for a given connector instance (or from a generic “Azure SQL secret” resource if single shared secret per deployment).

### Minimal Tool Set
- **health** — No args; returns `{ "status": "healthy" | "unhealthy", "details": ... }` (e.g. DB ping).
- **discover_schema** — Returns schema metadata (tables, columns, types) for allowed objects only.
- **query_{table}** (or **query** with `intent` + `params`) — Executes one parameterized, allowlisted, read-only query; returns items, metadata, citations.

### Dynamic Query Generation Strategy (Constrained)
- Prefer **template-based** queries keyed by intent (e.g. “query_customers” → fixed SELECT template with parameterized filters).
- If “dynamic” generation is used (e.g. LLM-generated SQL), it **must** be validated by the same safety layer (keyword block, allowlist, read-only, LIMIT/TOP) before execution.
- All user or external inputs must be passed as parameters, not string-interpolated into SQL.

### Connector Gateway Wiring (CDK)
- In `lib/connectors/connector-gateway/index.ts`, ensure the Azure SQL ECS service is created when `azureSqlEnabled` is true; set env vars and secret ARN reference in the task definition; target group and listener rules route requests for “/azure-sql” or similar to this service.

### Commands to Run
- Build Docker image for azure-sql-mcp-server and run it locally (optional); run E2E via integtests in Phase 7.

### Expected Verification
- ECS task starts; health check returns 200/healthy.
- `discover_schema` returns only allowed schemas/tables/views.
- A valid `query_*` returns rows; a query touching a blocked keyword or disallowed table fails with a clear error.

### Risk Level
**Medium** — new service and credential handling.

### Rollback
Disable Azure SQL in config and remove or scale to zero the Azure SQL ECS service; remove the Docker image from use.

---

## PHASE 7 — Tests (Unit + Integration) + CI Safety

### Goal
Add unit and integration tests for connectors; ensure all **existing** tests continue to pass so that failures block merge.

### Exact Files/Folders to Create/Modify

| Path | Purpose |
|------|---------|
| `tests/shared/layers/python-sdk/genai_core/connectors/` (or equivalent under `tests/`) | New dir for connector unit tests |
| `tests/.../test_registry.py` | Registry CRUD against real or local DynamoDB (or mocked) |
| `tests/.../test_mcp_client.py` | MCP client with mocked HTTP/stdio; assert request shape and response parsing |
| `tests/.../test_safety.py` | Safety: dangerous keywords rejected, allowlist enforced, read-only enforced, LIMIT/TOP required |
| `tests/.../test_intent.py` | Intent: `detect_connector_intent` and `classify_intent` return expected shapes |
| `integtests/connectors/` (new) | New dir for connector integration tests |
| `integtests/connectors/test_connector_integration.py` | Create connector via GraphQL → test health → run query → assert response format |
| `integtests/connectors/test_connector_in_chat_flow.py` (optional in same phase) | Send chat message that triggers connector; assert context/citations in response |

### Unit Test Scope
- **Registry:** create, get, list by workspace/type, get_connectors_for_application, update, delete.
- **MCP client:** mocked response; assert `call_tool` builds correct payload and maps response to `{ items, metadata, citations }`.
- **Safety:** For each of DROP, DELETE, UPDATE, INSERT, EXEC, etc., assert validation raises; assert SELECT-only and allowlist checks; assert LIMIT/TOP required.
- **Intent:** Sample prompts and expected intent/params; optional connector_id when applicable.

### Integration Test Scope
- Use existing integtest patterns (e.g. `integtests/clients/appsync_client.py`, env-based config).
- **test_connector_integration.py:** Create connector (GraphQL mutation) → testConnector (GraphQL query) → runConnectorQuery (GraphQL query); assert structure of ConnectorHealth and ConnectorQueryResult.
- **test_connector_in_chat_flow.py:** Create connector, then send a chat message that should trigger connector context; assert response contains expected content or citations (or assert no failure when connector is unavailable).

### CI Safety
- In the same CI run as the rest of the repo: run `npm run build`, `npm run test`, `npm run pytest`, `npm run integtest`.
- Require that **all** existing suites still pass; new connector tests may be skipped if their dependencies (e.g. DynamoDB, MCP server) are not available in CI, but skip must be explicit and not hide regressions.

### Commands to Run
- `npm run build`  
- `npm run test`  
- `npm run pytest`  
- `npm run integtest`  

### Expected Verification
- All existing tests pass.
- New connector unit tests pass when run in an environment that has (or mocks) DynamoDB and dependencies.
- New connector integration tests pass when run in an environment with deployed API and connector table (or optional skip with reason).

### Risk Level
**Low** — tests are additive.

### Rollback
Remove or skip the new tests without reverting application code if tests are flaky; fix tests and re-enable.

---

## PHASE 8 — Deployment & Verification Runbook

### Goal
Document exact deployment steps with SeedFarmer and CDK, config inputs, validation of outputs, and manual smoke tests plus observability checks.

### Deployment Steps (Summary)

1. **Preflight**
   - Run Phase 0 commands; fix any failing tests.

2. **Config**
   - In SeedFarmer (or equivalent): set `CONNECTORS_ENABLE=true`, `CONNECTORS_AZURE_SQL_ENABLE=true`, and `CONNECTORS_VPC_ID` if required.
   - Run `npm run config` (or equivalent) to regenerate `./bin/config.json` with `connectors.enabled: true` and `connectors.azureSql.enabled: true`.

3. **Deploy**
   - Execute SeedFarmer deploy (or `npx cdk deploy` with config that includes connectors).
   - Confirm outputs: connector table name, connector gateway URL (e.g. internal ALB DNS), and any new export used by the app.

4. **Validate outputs**
   - Connector table exists and has expected key schema and GSI.
   - ECS services for Azure SQL are running and healthy.
   - Lambda env has `CONNECTORS_TABLE_NAME` when connectors are enabled.

5. **Manual smoke tests**
   - Create a connector via GraphQL (createConnector) with a valid secret ARN and allowed_resources.
   - Call testConnector; expect status “healthy” when backend is reachable.
   - Call runConnectorQuery with a safe prompt; expect items and citations.
   - Send a chat message that should use connector context; confirm response and citations.

6. **Observability**
   - Logs: ensure connector-related log lines (e.g. “Connector context retrieval failed”, “execute_query”) are written to the same log groups as the api-handler and request-handler (CloudWatch).
   - Metrics: if you add custom metrics for connector calls/failures, confirm they appear and that failures are counted separately from successful chat completions.
   - Requirement: Connector failures must be visible (logs/metrics) but must **not** cause chat to return 5xx or empty response; chat should degrade gracefully.

### Rollback
- Set `CONNECTORS_ENABLE=false` (and per-connector flags to false); redeploy. Optionally tear down connector-specific resources via CDK destroy.

---

## Folder-by-Folder Summary (New Folders)

| Folder | Purpose |
|--------|---------|
| **lib/connectors/** | CDK and runtime assets for connectors: registry table construct, gateway construct, and per-connector MCP servers. |
| **lib/connectors/connector-dynamodb-tables/** | CDK construct for the `{prefix}-connectors` DynamoDB table and GSI. |
| **lib/connectors/connector-gateway/** | CDK construct for ECS cluster, ALB, and Fargate services per connector type. |
| **lib/connectors/azure-sql-mcp-server/** | First MCP server: Dockerfile, main.py, connector.py, schema_discovery.py, safety.py. |
| **lib/shared/layers/python-sdk/python/genai_core/connectors/** | Orchestration SDK: base, registry, mcp_client, orchestrator, intent, safety, __init__.py. |
| **lib/chatbot-api/functions/api-handler/routes/connectors.py** | New route module only; no new top-level folder. |
| **tests/.../genai_core/connectors/** | Unit tests for registry, mcp_client, safety, intent. |
| **integtests/connectors/** | Integration tests: create → test → query and chat-flow with connector context. |

---

## Future Connectors Plan (SharePoint, Dropbox)

- **Architecture unchanged:** Same registry table, same GraphQL types/mutations, same orchestrator and `resolve_context_for_prompt` hook. New connectors are new ECS services (or new tasks) behind the same gateway and new entries in the registry by `connector_type`.
- **SharePoint:** New folder `lib/connectors/sharepoint-mcp-server/` with Dockerfile, main.py, connector implementation using Microsoft Graph (or similar). Auth: OAuth2; store refresh token in Secrets Manager; implement token refresh in the server. Tools: search_documents, get_item, list_folder, get_schema. Allowlists: `sites`, `folders` from `allowed_resources`.
- **Dropbox:** New folder `lib/connectors/dropbox-mcp-server/` with Dockerfile, main.py, connector using Dropbox API. Auth: OAuth2; store access token in Secrets Manager. Tools: search_files, get_file, list_folder, get_schema. Allowlists: `folders` from `allowed_resources`.
- **CDK:** In `connector-gateway`, add conditional creation of SharePoint and Dropbox ECS services when `config.connectors?.sharepoint?.enabled` or `config.connectors?.dropbox?.enabled` is true; re-use same ALB with additional listener rules/paths.
- **No schema or API contract changes** for these; only new connector_type values and new MCP server implementations.

---

## Security Checklist

- [ ] **Secrets Manager:** All connector credentials stored only in Secrets Manager; DynamoDB and config store only secret **ARNs**.
- [ ] **RBAC:** Create/update/delete/test restricted to Admin and WorkspaceManager; runConnectorQuery restricted to users with access to the application/workspace that owns the connector.
- [ ] **Allowlists:** Azure SQL allows only configured schemas/tables/views; SharePoint/Dropbox only configured sites/folders; enforced in both orchestrator and MCP server.
- [ ] **Audit logs:** Connector queries (and optionally sensitive operations) logged in a form that supports audit; avoid logging secret values or full PII in plain text.
- [ ] **Prompt injection / SQL injection:** User and LLM-generated input never concatenated into SQL; parameterization enforced; server-side validation mirrors genai_core.connectors.safety.
- [ ] **Least privilege:** ECS task roles and Lambda roles have minimal permissions; Lambda can read/write connector table and pass ARNs; only the component that needs credentials (e.g. MCP server task) has GetSecretValue on the specific secret ARNs.

---

## Implementation Checklist (High-Level)

- [ ] Phase 0: Preflight passed; all baseline tests green.
- [ ] Phase 1: capability.yaml, magic-config.ts, types.ts updated; defaults off.
- [ ] Phase 2: ConnectorDynamoDBTables and ConnectorGateway created and wired conditionally; api-handler granted table + minimal secrets access.
- [ ] Phase 3: Schema extended; routes/connectors.py added; index.py includes connectors router.
- [ ] Phase 4: genai_core.connectors implemented (base, registry, mcp_client, orchestrator, intent, safety).
- [ ] Phase 5: resolve_context_for_prompt updated with fail-safe connector block; application_id passed where available.
- [ ] Phase 6: Azure SQL MCP server implemented and deployable via connector-gateway.
- [ ] Phase 7: Unit and integration tests added; all existing tests still pass.
- [ ] Phase 8: Deployment runbook executed; smoke tests and observability verified.

---

## Definition of Done

- All phases 0–8 are completed in order (or in an order that respects dependencies as described).
- No existing flow is broken: chat, RAG, web search, auth, RBAC, schema, and data import behave as before when connectors are disabled.
- With connectors enabled: an admin can create and test an Azure SQL connector, and a user can run a connector query and see connector-derived context in chat when the prompt triggers it.
- Failures in connector code path do not cause chat to fail; they result in empty connector context and visible logs/metrics.
- Security checklist items are satisfied; credentials live only in Secrets Manager with ARNs elsewhere.
- All baseline and new tests pass in CI; integration tests are run (or explicitly skipped with reason) in the same pipeline.

---

*End of Cursor Implementation Instruction Set. Use this document only as the plan for implementation; do not apply code changes in this step.*
