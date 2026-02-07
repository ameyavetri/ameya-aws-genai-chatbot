# MCP Connectors Knowledge Base

This document is the **persistent reference** for the MCP-based Data Source Connectors feature in this repository. Use it when answering questions about connectors: point to the relevant module/file and terms below.

**Source-of-truth alignment:** `CURSOR_IMPLEMENTATION_INSTRUCTION_SET.md`, `MCP_CONNECTORS_ARCHITECTURE.md`, `lib/shared/types.ts`, `aws-genai-llm-chatbot/capability.yaml`.

---

## 1. Glossary of Key Terms

| Term | Definition | Where it lives |
|------|------------|----------------|
| **connectors.enabled** | Top-level feature flag: when `true`, CDK creates the connector DynamoDB table and Connector Gateway (ECS + ALB). When `false`, no connector resources are created. | `lib/shared/types.ts` (SystemConfig.connectors.enabled), `cli/magic-config.ts`, `bin/default-config.json`, `lib/aws-genai-llm-chatbot-stack.ts` (conditional `if (props.config.connectors?.enabled)`) |
| **connector registry table** | DynamoDB table storing connector configuration per workspace. Key schema: PK `connector_id`, SK `workspace_id`; GSI `by_workspace`: PK `workspace_id`, SK `connector_type`. Table name: `{prefix}-connectors`. | `lib/connectors/connector-dynamodb-tables/index.ts`, `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` |
| **connector gateway** | Internal ALB + ECS Fargate services that host MCP servers (e.g. Azure SQL). Path-based routing (e.g. `/azure-sql/*`). Created only when `connectors.enabled` is true. | `lib/connectors/connector-gateway/index.ts`, `lib/aws-genai-llm-chatbot-stack.ts` |
| **MCP client** | HTTP client that calls MCP server tools (`POST /tools/{tool_name}`). If no endpoint is set, returns a stub response (no network call). | `lib/shared/layers/python-sdk/python/genai_core/connectors/mcp_client.py` |
| **orchestrator** | Coordinates: load connector from registry → RBAC/workspace check → intent classification → safety validation → MCP client call → normalize to QueryResult/context pack. | `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py` |
| **allowed_resources** | Per-connector allowlist for SQL safety: `schemas`, `tables`, `views`, and `rate_limits.max_rows_per_query`. Stored in the connector item in DynamoDB. Empty allowlist = no restriction (allow all). | Connector item in registry; validated in `lib/shared/layers/python-sdk/python/genai_core/connectors/safety.py`, `lib/connectors/azure-sql-mcp-server/safety.py` |
| **secret ARN** | AWS Secrets Manager ARN where connector credentials (e.g. Azure SQL connection string) are stored. Only ECS task roles (MCP servers) get `GetSecretValue`; api-handler gets only `DescribeSecret`/`GetResourcePolicy`. | Connector config in registry; CDK grants in `lib/aws-genai-llm-chatbot-stack.ts` (api-handler) and `lib/connectors/connector-gateway/index.ts` (task role) |
| **application_id scoping** | Connectors can be restricted to specific applications via `application_ids` on the connector item. Chat flow uses `get_connectors_for_application(workspace_id, application_id)` when `application_id` is present; otherwise workspace-level connectors (no `application_ids`). | `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` (`get_connectors_for_application`), `lib/model-interfaces/langchain/functions/request-handler/index.py` (resolve_context_for_prompt) |

---

## 2. Dependency Map (Control & Data Flow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PLANNED (not yet in schema/routes):                                        │
│  GraphQL schema (Query/Mutation) → AppSync → api-handler                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  api-handler Lambda                                                          │
│  • routes/connectors.py (PLANNED – not yet present)                           │
│    → listConnectors, createConnector, getConnector, updateConnector,         │
│      deleteConnector, testConnector, runConnectorQuery                        │
│  • index.py: no connectors router included yet                              │
│  File: lib/chatbot-api/functions/api-handler/index.py                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  genai_core.connectors (Python layer)                                        │
│  • registry: CRUD + get_connectors_for_application                           │
│    → lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py  │
│  • orchestrator: execute_query, test_connector                                │
│    → lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py│
│  • intent: classify_intent, detect_connector_intent                           │
│    → lib/shared/layers/python-sdk/python/genai_core/connectors/intent.py     │
│  • safety: validate_query, validate_sql                                      │
│    → lib/shared/layers/python-sdk/python/genai_core/connectors/safety.py     │
│  • mcp_client: MCPClient.call_tool, list_tools                               │
│    → lib/shared/layers/python-sdk/python/genai_core/connectors/mcp_client.py │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Connector Gateway (when connectors.enabled)                                 │
│  • ALB listener (port 80) → path-based rules → ECS Fargate services           │
│  • Per-connector: /azure-sql/*, /sharepoint/*, /dropbox/*                   │
│  File: lib/connectors/connector-gateway/index.ts                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Chat flow (context injection) – implemented:**

```
LangChain request-handler
  → resolve_context_for_prompt()
     • Guard: os.getenv("CONNECTORS_TABLE_NAME") and workspace_id
     • registry.get_connectors_for_application() or list_connectors()
     • intent.detect_connector_intent(prompt)
     • orchestrator.execute_query(...)
     • Fail-safe: try/except → log warning, connector_items = []
  → Order of blocks: internal (RAG) → web → connector
File: lib/model-interfaces/langchain/functions/request-handler/index.py
```

---

## 3. config.json Keys and Expected Defaults

Connector-related keys live under **`connectors`** (optional). If `connectors` is missing, treat as disabled.

| Key | Type | Default | Notes |
|-----|------|---------|--------|
| `connectors` | object | (absent or below) | Optional; missing ⇒ feature off. |
| `connectors.enabled` | boolean | **false** | Master switch for connector infra and runtime. |
| `connectors.vpcId` | string | **""** | VPC ID for connector gateway; empty ⇒ stack uses shared VPC. |
| `connectors.azureSql.enabled` | boolean | **false** | Deploy Azure SQL MCP service when true. |
| `connectors.sharepoint.enabled` | boolean | **false** | Deploy SharePoint MCP service when true. |
| `connectors.dropbox.enabled` | boolean | **false** | Deploy Dropbox MCP service when true. |

**Source:** `bin/default-config.json`, `cli/magic-config.ts` (SeedFarmer: `CONNECTORS_*` → `connectors.*`), `lib/shared/types.ts` (SystemConfig).

**Runtime (Lambda):** Only `CONNECTORS_TABLE_NAME` is set by CDK when `connectors.enabled` is true. Connector endpoint URLs come from each connector record in the registry (`endpoint.url`), not from a global `CONNECTOR_GATEWAY_URL` in this codebase.

---

## 4. Critical Invariants

These must hold for safe, correct behavior. When answering connector questions, check against these.

| Invariant | Where enforced / how |
|-----------|----------------------|
| **Fail-safe chat** | Connector context is wrapped in try/except in `resolve_context_for_prompt`; on any exception, log warning and set `connector_items = []`. Chat response continues without connector block. File: `lib/model-interfaces/langchain/functions/request-handler/index.py`. |
| **Feature off when not enabled** | No connector block if `CONNECTORS_TABLE_NAME` is unset or `workspace_id` is missing. Same file. CDK creates no connector table/gateway when `config.connectors?.enabled` is not true. |
| **Secrets never logged** | Secret values live only in Secrets Manager. Api-handler has only `DescribeSecret`/`GetResourcePolicy`; ECS task roles have `GetSecretValue` for MCP servers. No secret values in connector records (only ARNs). Ensure logging never dumps full connector config with secret ARN values in sensitive paths. |
| **SELECT-only (SQL)** | `genai_core.connectors.safety.validate_sql`: blocklist of dangerous keywords (DROP, DELETE, UPDATE, INSERT, etc.); only `SELECT` or `WITH ... SELECT` allowed. File: `lib/shared/layers/python-sdk/python/genai_core/connectors/safety.py`. Same rules in `lib/connectors/azure-sql-mcp-server/safety.py`. |
| **Allowlist enforced** | For SQL, FROM/JOIN refs must be in `allowed_resources.schemas` / `tables` / `views` when those lists are non-empty. Empty allowlist = no restriction. Same safety modules. |
| **LIMIT/TOP and row cap** | SQL must contain LIMIT or TOP; numeric limit must be ≤ `allowed_resources.rate_limits.max_rows_per_query` (default 1000). Same safety modules. |
| **RBAC boundaries** | Orchestrator: `connector.workspace_id` must match request `workspace_id`; if `application_id` is provided, it must be in `connector.application_ids`. File: `lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py`. GraphQL/resolvers (when implemented) must pass workspace/application from auth context. |

---

## 5. Quick Reference: Where Is…?

| Question | Answer (file or location) |
|----------|----------------------------|
| Where is the connector feature flag read at runtime? | Env `CONNECTORS_TABLE_NAME` presence in `lib/model-interfaces/langchain/functions/request-handler/index.py`; config at deploy time in `lib/aws-genai-llm-chatbot-stack.ts`. |
| Where is connector CRUD implemented? | `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py`. GraphQL/HTTP routes for CRUD are not yet implemented (no `routes/connectors.py`). |
| Where is SQL safety validated? | SDK: `lib/shared/layers/python-sdk/python/genai_core/connectors/safety.py`. Server: `lib/connectors/azure-sql-mcp-server/safety.py`. |
| Where does chat get connector context? | `resolve_context_for_prompt()` in `lib/model-interfaces/langchain/functions/request-handler/index.py`. |
| Where is the connector table schema defined? | PK/SK/GSI in `lib/connectors/connector-dynamodb-tables/index.ts`. |
| Where does SeedFarmer config map to connectors? | `cli/magic-config.ts`: `CONNECTORS_*` env vars → `connectors.*` in SystemConfig / config.json. |

Use this knowledge base for all connector-related answers and point to the module/file for the logic.
