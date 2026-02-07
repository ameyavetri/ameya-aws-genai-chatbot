# Connectors developer guide (MCP data sources)

This document is for developers who need to understand the connector architecture, extend it with new connector types, or troubleshoot connector behavior. For deployment and admin tasks, see [Deploying and configuring connectors](../guide/connector-deploy-and-config.md) and [Configuration](../guide/config.md).

---

## 1. Architecture

### Components and flow

- **UI** → Users (admin/workspace_manager) manage connectors via **Admin → Connectors**. The UI calls the **GraphQL API** (AppSync) for connector CRUD and **testConnector**.
- **GraphQL (api-handler Lambda)** → Resolvers for `listConnectors`, `getConnector`, `createConnector`, `updateConnector`, `deleteConnector`, `testConnector` live in `lib/chatbot-api/functions/api-handler/routes/connectors.py`. They use the **Connector Registry** (DynamoDB) and **Secrets Manager** (for credentials). Only the secret ARN is stored in the registry; raw credentials are never stored in DynamoDB. Responses mask `credentialsSecretArn`.
- **Request-handler Lambda (LangChain)** → During chat, the request-handler builds context for the prompt. It calls **resolve_context_for_prompt** (in `lib/model-interfaces/langchain/functions/request-handler/index.py`), which:
  - Reads **CONNECTORS_TABLE_NAME** from the environment (if not set, connector path is skipped).
  - Uses **intent detection** to decide if the user prompt needs connector data.
  - Calls the **Connector Registry** to list/get connectors for the workspace (and optional application).
  - Calls the **Orchestrator** (`genai_core.connectors.orchestrator`) to **execute_query** for the selected connector.
- **Orchestrator** → Loads the connector record from the registry, then uses the **MCP client** to call the connector’s MCP server (e.g. tools for search, health). The MCP server runs behind the **Connector Gateway** (ALB + ECS tasks: Azure SQL, Dropbox, SharePoint).
- **Connector Gateway** → ALB routes by path (e.g. `/azure-sql`, `/dropbox`) to the corresponding ECS service. Each MCP server reads credentials from **Secrets Manager** via `CREDENTIALS_SECRET_ARN` in its environment.

**Summary flow:**

- **Create/list/update/delete connectors:** UI → AppSync → api-handler → registry (DynamoDB) + Secrets Manager.
- **Chat using connector:** User message → sendQuery → request-handler → resolve_context_for_prompt → registry → orchestrator → MCP client → Connector Gateway (ALB) → MCP server (ECS) → response normalized and merged into prompt context; citations/sources are added to response metadata.

---

## 2. How to add a new connector type

1. **Add the MCP server and task to the Connector Gateway**  
   Implement (or reuse) an MCP server that exposes tools (e.g. search, health). Add a new ECS service and register it with the ALB under a path (e.g. `/my-connector`). Ensure the task role has `secretsmanager:GetSecretValue` for the secret(s) it needs. The container should read `CREDENTIALS_SECRET_ARN` from the environment.

2. **Add config for the new type**  
   In `bin/config.ts` and `bin/default-config.json`, add a flag such as `connectors.myConnector.enabled`. In the CDK stack, when this flag is true, create the ECS task and add a listener rule for the new path.

3. **Extend GraphQL and registry**  
   The current schema uses a generic `type` string (e.g. `azure_sql`, `dropbox`, `sharepoint`). You can add a new type value (e.g. `my_connector`) without changing the schema. If you need type-specific input fields, extend `CreateConnectorInput` / `UpdateConnectorInput` and the API route validation. The **registry** (DynamoDB) stores `connector_type` and optional `allowed_resources`; no schema change is required unless you add new top-level fields.

4. **Implement MCP tools**  
   The orchestrator calls the MCP server (e.g. a “query” or “search” tool). Implement the tools in your MCP server so they return a structure the orchestrator can normalize (e.g. list of items with `content`, `source`, `url`). Document the **secret shape** (JSON keys) for your connector in the admin guide.

5. **Document**  
   Update the [admin guide](../guide/connector-deploy-and-config.md) (how to create and test the new connector) and this developer guide (secret shape, any new env vars or IAM).

---

## 3. API reference

All connector operations are **GraphQL** (AppSync). Only **admin** and **workspace_manager** Cognito groups can call these; others receive **403 Unauthorized**.

| Operation            | Field / Mutation        | Description |
|----------------------|-------------------------|-------------|
| List connectors      | `listConnectors(workspaceId: String!, connectorType: String)` | Returns connectors for the workspace; optional filter by type. |
| Get connector        | `getConnector(connectorId: String!, workspaceId: String!)`    | Returns one connector by composite key. Returns null if not found (e.g. wrong workspace). |
| Create connector     | `createConnector(input: CreateConnectorInput!)`               | Creates a connector. Provide either `credentials` (JSON string; app creates secret) or `credentialsSecretArn`. |
| Update connector     | `updateConnector(input: UpdateConnectorInput!)`             | Updates name, type, endpoint, applicationIds, allowedResources, status, or credentials. |
| Delete connector     | `deleteConnector(connectorId: String!, workspaceId: String!)` | Soft-deletes the connector and deletes the app-created secret if applicable. |
| Test connector       | `testConnector(input: TestConnectorInput!)`                  | Calls the MCP server health/tool and returns `ConnectorHealth { status, details, timestamp }`. |

### Inputs (summary)

- **CreateConnectorInput:** `workspaceId`, `name`, `type`, `endpoint` (optional), `credentialsSecretArn` (optional), `credentials` (optional JSON string), `applicationIds`, `allowedResources`.
- **UpdateConnectorInput:** `connectorId`, `workspaceId`, plus optional `name`, `type`, `endpoint`, `credentialsSecretArn`, `credentials`, `applicationIds`, `allowedResources`, `status`.
- **TestConnectorInput:** `connectorId`, `workspaceId`.

### Outputs

- **Connector:** `id`, `workspaceId`, `name`, `type`, `status`, `endpoint`, `credentialsSecretArn` (masked in API), `applicationIds`, `allowedResources`, `createdAt`, `updatedAt`.
- **ConnectorHealth:** `status` (e.g. healthy, unhealthy), `details`, `timestamp`.

### Error codes

- **403 Unauthorized** — Caller is not in `admin` or `workspace_manager`. Or (if implemented) the requested `workspaceId` is not in the caller’s allowed workspaces.
- **404 / Connector not found** — `getConnector` with a valid ID but wrong `workspaceId`, or connector was deleted. The API may return `null` for getConnector instead of an error.
- **400 / Validation** — Invalid input (e.g. missing required field, invalid ARN, or both `credentials` and `credentialsSecretArn` provided).

---

## 4. Database schema (connector registry)

- **Table name:** `<prefix>-connectors` (e.g. `genai-chatbot-connectors`). Set by CDK when connectors are enabled; the Lambdas receive it as **CONNECTORS_TABLE_NAME**.
- **Primary key:** Composite.
  - **Partition key (PK):** `connector_id` (String).
  - **Sort key (SK):** `workspace_id` (String).
- **GSI:** `by_workspace` — partition key `workspace_id`, sort key `connector_type`. Used to list connectors by workspace (and optionally filter by type).

### Attributes (registry item)

| Attribute               | Type   | Description |
|-------------------------|--------|-------------|
| connector_id            | String | Unique ID (e.g. generated or `conn-<uuid>`). |
| workspace_id            | String | Workspace this connector belongs to. |
| connector_type          | String | e.g. `azure_sql`, `dropbox`, `sharepoint`. |
| name                    | String | Display name. |
| status                  | String | e.g. `active`, `inactive`. |
| endpoint                | Map    | `{ "type": "mcp_server", "url": "http://<alb>/azure-sql" }`. |
| credentials_secret_arn  | String | ARN of the secret in Secrets Manager (not exposed in API response). |
| application_ids         | List   | Optional; if set, only these application IDs can use this connector. |
| allowed_resources       | Map    | Optional; e.g. `schemas`, `tables`, `views`, `rate_limits` for SQL connectors. |
| created_at              | String | ISO timestamp. |
| updated_at              | String | ISO timestamp. |

---

## 5. Troubleshooting

### CONNECTORS_TABLE_NAME not set

- **Symptom:** Connectors do not appear in chat context; connector API may return “Connectors are not enabled.”
- **Cause:** The api-handler or request-handler Lambda does not have the environment variable **CONNECTORS_TABLE_NAME**.
- **Fix:** Enable connectors in config (`connectors.enabled: true`) and redeploy. Verify in the AWS Console: Lambda → api-handler and request-handler → Configuration → Environment variables → **CONNECTORS_TABLE_NAME** = `<prefix>-connectors`.

### Connector not found

- **Symptom:** `getConnector` returns null or 404; or chat does not use the connector.
- **Causes:** Wrong `workspace_id` (composite key), connector deleted, or table not set.
- **Fix:** Ensure you pass the correct `workspaceId` for the connector. In chat, ensure the user’s selected workspace matches the connector’s `workspace_id`. Check DynamoDB for the item (PK = `connector_id`, SK = `workspace_id`).

### Health check failed (testConnector unhealthy)

- **Symptom:** “Test connection” shows **unhealthy** or times out.
- **Causes:** MCP server unreachable (wrong endpoint URL, ECS task down, ALB target unhealthy), or MCP server error (e.g. invalid credentials, missing env).
- **Fix:**  
  - Verify **endpoint URL** (e.g. `http://<connector-alb-dns>/azure-sql`). Get ALB DNS from EC2 → Load Balancers or ECS → service → Load balancing.  
  - Check **ECS** service and tasks: are tasks running? Check **CloudWatch Logs** for the connector’s log group.  
  - Ensure the ECS task has **CREDENTIALS_SECRET_ARN** and the task role has **GetSecretValue** on that secret.

### Chat response has no connector context or citations

- **Symptom:** User asks a question that should use the connector, but the reply has no “Sources” or “References” and no connector-sourced content.
- **Causes:** Intent detection did not trigger connector; no active connector for the workspace/application; request-handler missing table access or env; MCP call failed (see health check).
- **Fix:** Confirm **resolve_context_for_prompt** runs with `CONNECTORS_TABLE_NAME` set and that the connector’s workspace (and optional application_ids) match. Check **request-handler** CloudWatch logs for connector intent and orchestrator calls. Verify **testConnector** is healthy for that connector.

### Where to look in CloudWatch

- **api-handler:** Log group for the api-handler Lambda; connector resolvers log `operation`, `workspace_id`, `connector_id`, `status`, and `duration_ms` (Part 10).
- **request-handler:** Log group for the LangChain request-handler; look for `connector context used in prompt` and orchestrator calls.
- **Connector ECS services:** One log group per connector type (e.g. Azure SQL, Dropbox); MCP server logs and errors.

---

## 6. Monitoring & observability (Part 10)

### CloudWatch metrics

Connector usage is published to the **GenAIChatbot/Connectors** namespace:

| Metric | Unit | Dimensions | When emitted |
|--------|------|------------|--------------|
| **ConnectorQuerySuccess** | Count | connector_type, workspace_id | After a successful `execute_query` in the orchestrator. |
| **ConnectorQueryFailure** | Count | connector_type, workspace_id, error_type | When `execute_query` raises (e.g. MCP timeout, validation). |
| **ConnectorResponseTime** | Milliseconds | connector_type, workspace_id | After each successful `execute_query`; value = duration in ms. |
| **ConnectorContextUsed** | Count | workspace_id | When the request-handler uses connector context in the prompt (chat flow). |

Lambdas that publish these metrics need **cloudwatch:PutMetricData** on the namespace (or the default Lambda execution role may already allow it). To build a dashboard: use **CloudWatch → Dashboards** and add widgets for ConnectorQuerySuccess, ConnectorQueryFailure, average ConnectorResponseTime, and optionally group by connector_type.

### Structured logging

- **API routes (connectors.py):** Each resolver logs at start (`operation`, `workspace_id`, `connector_id` where applicable) and on completion (`status`, `duration_ms`).
- **Orchestrator:** Logs at start of `execute_query` and `test_connector`; on success logs item count (execute_query) or result; on exception logs warning with `error_type` and `error_message`.
- **Request-handler:** When connector context is used, logs `workspace_id`, `connector_id`, `connector_type`, `operation=resolve_context_for_prompt`, `intent_matched=True`.

Log format is structured JSON (Lambda Powertools Logger). Key fields: `workspace_id`, `connector_id`, `connector_type`, `operation`, `status`, `error_message` (if failed), `duration_ms`.

---

For security and RBAC details, see [CONNECTOR_SECURITY_ARCHITECTURE_REVIEW.md](CONNECTOR_SECURITY_ARCHITECTURE_REVIEW.md). For the implementation plan, see [MCP_CONNECTOR_IMPLEMENTATION_PLAN.md](../MCP_CONNECTOR_IMPLEMENTATION_PLAN.md).
