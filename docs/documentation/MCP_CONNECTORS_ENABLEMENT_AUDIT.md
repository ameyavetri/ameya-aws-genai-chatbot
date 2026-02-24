# MCP Connectors Enablement Wiring Audit

This document audits how connector enablement flows from **config / capability** → **deploy-time (CDK)** → **runtime (Lambda / genai_core)**. It also flags key-name mismatches and documents CONNECTORS_VPC_ID usage.

---

## 1. Exact config.json Keys for Connector Enablement

### Global (connectors on/off)

| config.json key | Type | Purpose |
|-----------------|------|--------|
| `connectors` | object | Optional. If missing, treat connectors as disabled. |
| `connectors.enabled` | boolean | **Master switch.** When `true`, CDK creates connector DynamoDB table and Connector Gateway; Lambda gets `CONNECTORS_TABLE_NAME`. When `false`, none of that happens. |

### Per-connector (which MCP services to deploy)

| config.json key | Type | Purpose |
|-----------------|------|--------|
| `connectors.azureSql.enabled` | boolean | When `true` (and `connectors.enabled`), CDK deploys Azure SQL MCP ECS service and path `/azure-sql/*`. |
| `connectors.sharepoint.enabled` | boolean | When `true`, CDK deploys SharePoint MCP ECS service and path `/sharepoint/*`. |
| `connectors.dropbox.enabled` | boolean | When `true`, CDK deploys Dropbox MCP ECS service and path `/dropbox/*`. |

### VPC (optional)

| config.json key | Type | Purpose |
|-----------------|------|--------|
| `connectors.vpcId` | string | **Intended:** VPC ID for connector gateway. **Actual:** Not used by CDK in this codebase (see §4). |

**Source chain:** `capability.yaml` inputs → SeedFarmer / env vars → `cli/magic-config.ts` → `config.json` → `lib/shared/types.ts` (SystemConfig).

---

## 2. Where Keys Are Consumed

### Deploy-time (CDK)

| Key | Consumed by | File: location |
|-----|-------------|----------------|
| `connectors.enabled` | Conditional creation of ConnectorDynamoDBTables + ConnectorGateway; setting `CONNECTORS_TABLE_NAME` on api-handler Lambda | `lib/aws-genai-llm-chatbot-stack.ts`: `if (props.config.connectors?.enabled)` (line ~238) |
| `connectors.azureSql.enabled` | Passed to ConnectorGateway as `azureSqlEnabled` | `lib/aws-genai-llm-chatbot-stack.ts`: `azureSqlEnabled: props.config.connectors?.azureSql?.enabled` (~261) |
| `connectors.sharepoint.enabled` | Passed to ConnectorGateway as `sharepointEnabled` | Same block: `sharepointEnabled: props.config.connectors?.sharepoint?.enabled` |
| `connectors.dropbox.enabled` | Passed to ConnectorGateway as `dropboxEnabled` | Same block: `dropboxEnabled: props.config.connectors?.dropbox?.enabled` |
| `connectors.vpcId` | **Not consumed.** Stack always uses `shared.vpc`. | `lib/aws-genai-llm-chatbot-stack.ts`: `const connectorVpc = shared.vpc` (~256) |

No other CDK code reads `config.connectors`.

### Runtime

| What | Consumed by | File: location |
|------|-------------|----------------|
| **Env var** `CONNECTORS_TABLE_NAME` | Set by CDK when `connectors.enabled` is true. Used as the only “connectors enabled” signal at runtime. | Set: `lib/aws-genai-llm-chatbot-stack.ts` (~272–274). Read: `lib/model-interfaces/langchain/functions/request-handler/index.py` (~92), `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py` (~157) |
| **config.json** `connectors.*` | **Not read at runtime.** Lambda does not receive config.json; connector enablement at runtime is inferred from presence of `CONNECTORS_TABLE_NAME`. | N/A |

So: **deploy-time** uses `config.json` (and thus capability.yaml → magic-config); **runtime** uses only the env var `CONNECTORS_TABLE_NAME`.

---

## 3. Key-Name Consistency Check (capability.yaml ↔ magic-config ↔ SystemConfig ↔ code)

| capability.yaml (input) | magic-config read/write | SystemConfig / config.json | CDK / code read | Status |
|--------------------------|-------------------------|----------------------------|-----------------|--------|
| `CONNECTORS_ENABLE` | → `options.connectorsEnable`; → `defaultConfig.connectors.enabled` | `connectors.enabled` | `props.config.connectors?.enabled` | OK |
| `CONNECTORS_VPC_ID` | → `options.connectorsVpcId`; → `defaultConfig.connectors.vpcId` | `connectors.vpcId` | Never read (reserved); capability.yaml updated to say optional/reserved | OK (documented) |
| `CONNECTORS_AZURE_SQL_ENABLE` | → `options.connectorsAzureSqlEnable`; → `defaultConfig.connectors.azureSql.enabled` | `connectors.azureSql.enabled` | `props.config.connectors?.azureSql?.enabled` | OK |
| `CONNECTORS_SHAREPOINT_ENABLE` | → `options.connectorsSharepointEnable`; → `defaultConfig.connectors.sharepoint.enabled` | `connectors.sharepoint.enabled` | `props.config.connectors?.sharepoint?.enabled` | OK |
| `CONNECTORS_DROPBOX_ENABLE` | → `options.connectorsDropboxEnable`; → `defaultConfig.connectors.dropbox.enabled` | `connectors.dropbox.enabled` | `props.config.connectors?.dropbox?.enabled` | OK |

**Resolved:** `connectors.vpcId` / `CONNECTORS_VPC_ID` is written by magic-config and defined in SystemConfig and capability.yaml, but **no CDK or runtime code reads it** (stack always uses `shared.vpc`). Chosen fix: keep current behavior; capability.yaml description was updated to state it is optional/reserved and not used today.

---

## 4. CONNECTORS_VPC_ID: Required? Where Used?

- **Required?** **No.** The CDK never reads `config.connectors.vpcId`. The connector gateway always uses the same VPC as the rest of the stack (`shared.vpc`).
- **Where used?**
  - **capability.yaml:** `CONNECTORS_VPC_ID` is defined (String, defaultValue `""`), description: “VPC ID for connector gateway (required when connectors enabled)”.
  - **magic-config.ts:** Maps `CONNECTORS_VPC_ID` → `config.connectors.vpcId` (SeedFarmer and interactive; interactive uses `options.connectorsVpcId ?? ""`).
  - **lib/shared/types.ts:** `connectors.vpcId` is defined.
  - **lib/aws-genai-llm-chatbot-stack.ts:** Only uses `shared.vpc`; **no reference to `props.config.connectors?.vpcId`**.

So CONNECTORS_VPC_ID is **not required** and is **not used** at deploy or runtime. capability.yaml has been updated to describe it as optional/reserved and not used today.

---

## 5. Example config.json Snippets

### Connectors disabled (default)

```json
{
  "connectors": {
    "enabled": false,
    "vpcId": "",
    "azureSql": { "enabled": false },
    "sharepoint": { "enabled": false },
    "dropbox": { "enabled": false }
  }
}
```

Or omit `connectors` entirely; code uses `config.connectors?.enabled ?? false` and equivalent for nested flags.

### Connectors enabled with Azure SQL and Dropbox

```json
{
  "connectors": {
    "enabled": true,
    "vpcId": "",
    "azureSql": { "enabled": true },
    "sharepoint": { "enabled": false },
    "dropbox": { "enabled": true }
  }
}
```

With this, CDK will:

- Create the connector DynamoDB table and Connector Gateway.
- Deploy Azure SQL and Dropbox ECS services (and path rules `/azure-sql/*`, `/dropbox/*`).
- Set `CONNECTORS_TABLE_NAME` on the api-handler Lambda.

Runtime behavior: request-handler and genai_core use `CONNECTORS_TABLE_NAME`; they do not read `config.json` directly.

---

## 6. Summary

| Question | Answer |
|----------|--------|
| **Exact config keys for global enablement?** | `connectors.enabled` (boolean). |
| **Exact config keys per connector (Azure SQL, Dropbox)?** | `connectors.azureSql.enabled`, `connectors.dropbox.enabled` (and `connectors.sharepoint.enabled` for SharePoint). |
| **Where consumed at deploy-time?** | `lib/aws-genai-llm-chatbot-stack.ts`: `config.connectors?.enabled`, `config.connectors?.azureSql?.enabled`, `config.connectors?.sharepoint?.enabled`, `config.connectors?.dropbox?.enabled`. |
| **Where consumed at runtime?** | Only env var `CONNECTORS_TABLE_NAME` (set by CDK when `connectors.enabled` is true). Read in request-handler and genai_core.connectors.registry. |
| **CONNECTORS_VPC_ID required?** | No. Not used by CDK or runtime. |
| **Key name mismatches?** | None. `connectors.vpcId` / `CONNECTORS_VPC_ID` is defined and written but not read by CDK; capability.yaml now describes it as optional/reserved and not used today. |
