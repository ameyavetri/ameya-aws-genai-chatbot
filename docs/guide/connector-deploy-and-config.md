# Deploying Updates and Configuring Connectors (Azure SQL + Dropbox)

This guide covers: (1) how to deploy this project (including connector updates) to AWS, (2) deployment and migration (Part 8), (3) after deploy, how to configure and use connectors (admin guide, Part 9.1), and (4) optional low-level registry configuration.

---

## Part 8: Deployment & migration

### Enabling connectors on an existing deployment

Existing deployments typically have `connectors.enabled: false` or no `connectors` section. You can enable connectors without data loss:

1. Update **config.json** (project root or `bin/config.json`): set `connectors.enabled` to `true` and the per-type flags you need (e.g. `connectors.azureSql.enabled`, `connectors.dropbox.enabled`, `connectors.sharepoint.enabled`).
2. Run **`npm run cdk deploy`**. CDK will create the connector DynamoDB table, Connector Gateway (ALB + ECS), and set `CONNECTORS_TABLE_NAME` and table access on the api-handler and request-handler Lambdas.
3. No downtime is required; existing RAG, chat, workspaces, and applications are unchanged.

**New installations:** Use the same config: set `connectors.enabled: true` and the desired connector types before the first deploy.

### Rollback

To disable connectors:

1. Set **`connectors.enabled`** to **`false`** in config.
2. Run **`npm run cdk deploy`**.

CDK will remove the connector table and Connector Gateway if their removal policy is **DESTROY**. **Warning:** Destroying the table deletes all connector records. If you use **Retain on delete** (e.g. `retainOnDelete: true` in config), the table will be retained; you can later restore or migrate data. To recover after a destroy, use DynamoDB backups if enabled.

After rollback, the request-handler and api-handler will no longer have `CONNECTORS_TABLE_NAME`; connector code paths are skipped (no table name in env).

### Feature flag (runtime)

Runtime behavior is **“connectors on if CONNECTORS_TABLE_NAME is set.”** There is no separate runtime flag to disable connectors without redeploying with `connectors.enabled: false`. To support a runtime kill switch, you could add an SSM Parameter or DynamoDB flag read by the API and request-handler; that is not in the current design.

### Migration

No data migration is required when enabling connectors. The connector table is created only when `connectors.enabled` is true. Adding it later is a new resource; no existing table is modified. If you later backfill connector records from an external store, that would be a one-off script (out of scope for this guide).

---

## Part 1: Deploying to AWS

### Prerequisites

- AWS account, IAM user with sufficient permissions (e.g. AdministratorAccess for a full deploy)
- Node.js 18 or 20, AWS CLI configured, [AWS CDK CLI](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html) installed
- [Docker](https://docs.docker.com/get-docker/) (and `buildx` on Linux) for building Lambda layers and connector images
- Python 3+ for local tests (optional)

See [Deploy](deploy.md) for detailed environment setup (local, GitHub Codespaces, etc.).

### 1. Config for connectors

Ensure `config.json` (in project root, or `bin/config.json` if you use the CLI) has connectors enabled and the types you want:

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

- **connectors.enabled** must be **true** so the stack creates the connector DynamoDB table and Connector Gateway (ALB + ECS).
- **connectors.azureSql.enabled** / **connectors.dropbox.enabled** control whether the Azure SQL and Dropbox MCP services are deployed.

### 2. Install and build

From the project root:

```bash
npm ci && npm run build
```

### 3. (Optional) Configure via CLI

To adjust LLMs, RAG, connectors, etc. interactively:

```bash
npm run config
```

This updates `config.json` (or `bin/config.json`). Answer the prompts; for connectors, enable the ones you need.

### 4. Bootstrap CDK (first time per account/region)

If you have never used CDK in this account and region:

```bash
npm run cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

Replace `<ACCOUNT_ID>` and `<REGION>` (e.g. `us-east-1`).

### 5. Deploy

```bash
npm run cdk deploy
```

Or with approval for security-related changes:

```bash
npx cdk deploy --require-approval broadening
```

Deploy can take 15–45+ minutes depending on what’s being created (VPC, RAG, connectors, etc.). Progress is visible in the [CloudFormation console](https://console.aws.amazon.com/cloudformation/home) for the stack (e.g. `chatbotGenAIChatBotStack`).

### 6. Note outputs

After a successful deploy, note:

- **User Interface** URL (CloudFront or custom domain)
- **Cognito User Pool** link to create users and assign admin/workspace_manager
- **Connector Gateway:** the internal ALB DNS name is not always in stack outputs; you may need it for connector registration (see Part 2). You can find it in the AWS Console: **EC2 → Load Balancers** (filter by the stack name or “Connector”), or **ECS → Clusters → &lt;prefix&gt;-ConnectorCluster** and inspect the service’s load balancer.

---

## Part 9.1: Admin guide – creating and testing connectors (UI)

After deployment with connectors enabled, only **admin** and **workspace_manager** roles can manage connectors. Use the chatbot UI or the GraphQL API.

### 1. How to enable connectors

Set **connectors.enabled** and the per-type flags in **config.json** (see [Configuration](config.md#connectors-mcp-data-source-connectors)), then run **`npm run cdk deploy`**. After deploy, the **Connectors** menu appears under **Admin** in the navigation (when the frontend is built with connectors enabled).

### 2. How to create a connector (UI)

1. Log in as an **admin** or **workspace_manager**.
2. Go to **Admin → Connectors**.
3. Select the **workspace** this connector will belong to.
4. Click **Create connector**.
5. Enter **name**, choose **type** (e.g. Azure SQL, Dropbox, SharePoint).
6. Enter **endpoint URL**: the Connector Gateway base path for that type (e.g. `http://<connector-alb-dns>/azure-sql`, `http://<connector-alb-dns>/dropbox`). See [Connector Gateway URL](#22-connector-gateway-url-endpoint-for-registry) below for how to get the ALB DNS.
7. **Credentials:** either paste a **JSON object** (the app will create a secret in Secrets Manager and store only the ARN), or provide an existing **credentials Secret ARN** from Secrets Manager.
8. (Optional) Restrict to specific **applications** or set **allowed resources** (e.g. for Azure SQL: schemas, tables).
9. Save. The connector appears in the list with status **active**.

### 3. How to create a Dropbox connector

- **Type:** Dropbox.
- **Secret shape (JSON):**
  - **Recommended (auto-refresh, long-lived):** `{ "app_key": "YOUR_APP_KEY", "app_secret": "YOUR_APP_SECRET", "refresh_token": "YOUR_REFRESH_TOKEN" }`. Create an app at [Dropbox Developers](https://www.dropbox.com/developers/apps), use OAuth2 with `token_access_type=offline` to obtain a refresh token. The connector auto-refreshes access tokens and never expires.
  - **Legacy (short-lived, ~4 hours):** `{ "access_token": "YOUR_ACCESS_TOKEN" }`. Generate from the App Console; will expire and require manual update.
- You can paste this JSON in the **Credentials** field when creating the connector (the app creates the secret), or create the secret in Secrets Manager first and enter its ARN.

### 4. How to create a SharePoint connector

- **Type:** SharePoint.
- **Secret shape:** site URL, client id/secret, or token as required by the SharePoint MCP server. Store as JSON in Secrets Manager and provide the secret ARN, or paste JSON in the Credentials field when creating the connector.

### 5. How to create an Azure SQL connector

- **Type:** Azure SQL.
- **Secret shape (JSON):**  
  `{ "server": "your-server.database.windows.net", "database": "YourDatabase", "username": "your-user", "password": "your-password" }`  
  or a single **connection string** value. You can paste JSON in the Credentials field or use an existing secret ARN.
- **Allowed resources (optional):** schemas (e.g. `dbo`), tables (e.g. `dbo.Customers`), views, and rate limits (e.g. `maxRowsPerQuery`) to restrict what the connector can query.

### 6. How to test connectors

On the Connectors page, use **Test connection** on a connector row. The result shows **healthy** or **unhealthy**, with details and timestamp. If the MCP server is unreachable (e.g. ALB/task down, wrong URL), you will see **unhealthy**. Fix the endpoint URL, ECS task, or credentials and test again.

### 7. Troubleshooting connection issues

- **Secret:** Ensure the secret exists in Secrets Manager and that the ECS task role has **GetSecretValue** on that secret. If the app created the secret (you pasted credentials), the task role is granted access to secrets with the app’s naming prefix.
- **ALB and target health:** In **EC2 → Load Balancers**, check the Connector Gateway ALB; in **Target groups**, verify targets are healthy. If ECS tasks are failing, check **ECS → Clusters → &lt;prefix&gt;-ConnectorCluster** and the service’s running tasks and logs.
- **MCP server logs:** In **CloudWatch Logs**, find the log group for the connector ECS service (e.g. Azure SQL or Dropbox). Errors (e.g. auth failure, invalid JSON in secret) appear there.
- **Chat not using connector:** Ensure the **request-handler** Lambda has **CONNECTORS_TABLE_NAME** set and read access to the connector table (see [Request-handler and connector table](#25-request-handler-lambda-and-connector-table)). Use a workspace that matches the connector’s workspace and ask a question that should trigger the connector (e.g. “Show me data from the database” or “Search my Dropbox”).

### 8. Security best practices

- Store credentials **only** in Secrets Manager; never put raw passwords in config or in the DynamoDB connector record (only the secret ARN is stored).
- Use least-privilege IAM for ECS tasks (only the secrets they need).
- Rotate secrets periodically; update the secret value in Secrets Manager and, if needed, use **Update connector** to point to a new secret ARN.
- Do not share workspace IDs across tenants; connectors are scoped by workspace.
- Only **admin** and **workspace_manager** can create, update, delete, or test connectors; regular users use connectors in chat only when the workspace and application allow it.

---

## Part 2: Configuring Azure SQL and Dropbox After Deploy (advanced)

You can also configure connectors via AWS Secrets Manager and (for advanced or scripted use) by writing items directly to the connector DynamoDB table. The **primary** way to create and manage connectors is the **Admin → Connectors** UI (or GraphQL API); this section is for automation or when the UI is not used.

For the chatbot to use Azure SQL and Dropbox, you need:

1. Store credentials in AWS Secrets Manager.
2. (Optional) Give the MCP ECS tasks access to those secrets via `CREDENTIALS_SECRET_ARN`.
3. Register each connector (via UI/GraphQL, or directly in the connector DynamoDB table as below).

The chat flow uses connector records from the registry; the MCP servers (Azure SQL / Dropbox) read credentials from their **environment** (e.g. `CREDENTIALS_SECRET_ARN`). So you configure both: **registry (endpoint + metadata)** and **ECS/Secrets (credentials)**.

### 2.1 Create secrets in AWS Secrets Manager

**Azure SQL**

Create a secret with the connection details. Either a JSON object or a connection string is supported.

- **JSON (recommended):**

  ```json
  {
    "server": "your-server.database.windows.net",
    "database": "YourDatabase",
    "username": "your-user",
    "password": "your-password"
  }
  ```

- Or a single **connection string** value (e.g. `Server=...;Database=...;UID=...;PWD=...;Driver={ODBC Driver 18 for SQL Server};Encrypt=yes;TrustServerCertificate=no`).

In AWS Console: **Secrets Manager → Store a new secret → Other type of secret** → key/value or plaintext, then name the secret (e.g. `chatbot/azure-sql-connector`). Note the **Secret ARN**.

**Dropbox**

Create a secret with your Dropbox credentials. Two formats supported:

**Recommended (refresh token, auto-refresh):**
```json
{
  "app_key": "YOUR_APP_KEY",
  "app_secret": "YOUR_APP_SECRET",
  "refresh_token": "YOUR_REFRESH_TOKEN"
}
```

**Legacy (access token, expires ~4 hours):**
```json
{
  "access_token": "YOUR_DROPBOX_ACCESS_TOKEN"
}
```

Obtain a refresh token via OAuth2 with `token_access_type=offline` in the authorize URL. Note the **Secret ARN**.

### 2.2 Connector Gateway URL (endpoint for registry)

The chatbot’s request-handler calls the MCP servers via the **Connector Gateway ALB**. The URL is internal (VPC), e.g.:

- `http://<connector-alb-dns-name>`

Path-based routes:

- Azure SQL: `http://<alb-dns>/azure-sql`
- Dropbox: `http://<alb-dns>/dropbox`

To get the ALB DNS name:

1. **AWS Console → EC2 → Load Balancers** → find the ALB associated with the Connector Gateway (name often includes the stack prefix and “Connector”).
2. Or **ECS → Clusters → &lt;prefix&gt;-ConnectorCluster** → open the service → **Configuration and tasks** → **Load balancing** → copy the load balancer DNS name.

The **request-handler Lambda** runs in the same VPC as the Connector Gateway, so it can use this internal URL.

### 2.3 (Optional) Pass credentials to MCP ECS tasks

The Azure SQL and Dropbox containers read `CREDENTIALS_SECRET_ARN` from their **environment**. The CDK today does not set this per connector; you can set it by updating the ECS task definition so the container gets the secret ARN.

**Option A – Update task definition in Console**

1. **ECS → Task Definitions** → select the task definition for the connector (e.g. `chatbot-azure-sqlTaskDefinition` or `chatbot-dropboxTaskDefinition`).
2. **Create new revision**.
3. Under the container → **Environment variables** → add:
   - **Key:** `CREDENTIALS_SECRET_ARN`
   - **Value:** the full Secret ARN from step 2.1.
4. Save. Update the ECS service to use the new task revision (e.g. **Update service → Force new deployment**).

**Option B – Same via AWS CLI**

Create a new task definition revision that adds `CREDENTIALS_SECRET_ARN` to the container’s `environment`, then update the service to use that revision.

After this, the Azure SQL / Dropbox containers will pull credentials from Secrets Manager at runtime. Ensure the **ECS task role** has `secretsmanager:GetSecretValue` for that secret (the connector-gateway CDK grants the task role access to Secrets Manager; if you use a custom secret, add a resource policy or IAM so the task role can read it).

### 2.4 Register connectors in the connector registry (optional, advanced)

The chat flow only uses connectors that exist in the **connector DynamoDB table**, with an **endpoint URL** pointing at the Connector Gateway. The normal way to create connectors is **Admin → Connectors** in the UI (or the GraphQL mutations **createConnector** / **updateConnector**). If you need to script or automate, you can instead insert items directly into the table (Console, CLI, or a small script) as below.

**Table name:** `<prefix>-connectors` (e.g. `chatbot-connectors`).

**Required attributes per connector item:**

- **connector_id** (string) – unique ID, e.g. `conn-azure-sql-prod` or `conn-dropbox-main`.
- **workspace_id** (string) – RAG workspace ID this connector is tied to (must match a workspace the user can select in chat).
- **connector_type** (string) – `azure-sql` or `dropbox`.
- **status** (string) – `active`.
- **endpoint** (map) – must contain **url** (string): the full base URL to the MCP service, e.g. `http://<connector-alb-dns>/azure-sql` or `http://<connector-alb-dns>/dropbox`.
- **created_at**, **updated_at** (strings, ISO timestamps) – optional but useful.

**Optional (recommended for Azure SQL):**

- **allowed_resources** (map) – for SQL safety: e.g. `{ "schemas": ["dbo"], "tables": ["dbo.Customers", "dbo.Orders"], "views": [], "rate_limits": { "max_rows_per_query": 1000 } }`. Leave empty `{}` for no restriction (less safe).
- **application_ids** (list of strings) – if set, only those application IDs can use this connector; leave unset for workspace-level (all apps using that workspace).

**Example – Azure SQL (AWS CLI)**

Replace `<TABLE_NAME>`, `<WORKSPACE_ID>`, `<CONNECTOR_ALB_DNS>` with your values.

```bash
aws dynamodb put-item \
  --table-name chatbot-connectors \
  --item '{
    "connector_id": {"S": "conn-azure-sql-01"},
    "workspace_id": {"S": "<WORKSPACE_ID>"},
    "connector_type": {"S": "azure-sql"},
    "status": {"S": "active"},
    "endpoint": {"M": {"url": {"S": "http://<CONNECTOR_ALB_DNS>/azure-sql"}}},
    "created_at": {"S": "2025-01-01T00:00:00Z"},
    "updated_at": {"S": "2025-01-01T00:00:00Z"}
  }'
```

**Example – Dropbox**

```bash
aws dynamodb put-item \
  --table-name chatbot-connectors \
  --item '{
    "connector_id": {"S": "conn-dropbox-01"},
    "workspace_id": {"S": "<WORKSPACE_ID>"},
    "connector_type": {"S": "dropbox"},
    "status": {"S": "active"},
    "endpoint": {"M": {"url": {"S": "http://<CONNECTOR_ALB_DNS>/dropbox"}}},
    "created_at": {"S": "2025-01-01T00:00:00Z"},
    "updated_at": {"S": "2025-01-01T00:00:00Z"}
  }'
```

**Getting a workspace_id:** Use an existing RAG workspace ID. In the UI: RAG → Workspaces; or call the GraphQL `listWorkspaces` and pick an `id`. That `id` is the `workspace_id` to use in the connector item.

### 2.5 Request-handler Lambda and connector table

The **LangChain request-handler** Lambda (which runs chat and calls `resolve_context_for_prompt`) must have:

- **Environment variable:** `CONNECTORS_TABLE_NAME` = `<prefix>-connectors`.
- **IAM:** read (and if you add connector APIs later, write) access to the connector DynamoDB table.

In the current stack, `CONNECTORS_TABLE_NAME` and connector table access are set on the **api-handler** (GraphQL) Lambda. If the **request-handler** does not have this env and table access, the chat flow will not use connectors even if registry items exist. If you find connectors are not used in chat, add the same `CONNECTORS_TABLE_NAME` and `connectorsTable.grantReadData(requestHandler)` (or equivalent) for the LangChain request-handler in your CDK stack, then redeploy.

### 2.6 Verify in chat

1. Log in to the chatbot UI as a user that has access to the workspace you used in the connector item (e.g. admin or workspace_manager).
2. In **Playground**, select the **same workspace** (the one in `workspace_id`).
3. Ask a question that should trigger a connector (e.g. “What’s in the database?” for Azure SQL, or “Search my Dropbox for X” for Dropbox).
4. If credentials and endpoint are correct, the model should receive connector context and answer using that data. Check CloudWatch Logs for the **request-handler** Lambda and the connector ECS services if something fails.

---

## Summary

| Step | Action |
|------|--------|
| **Deploy** | Set `connectors.enabled` and per-connector flags in `config.json` → `npm ci && npm run build` → `npm run cdk deploy`. |
| **Secrets** | Create Secrets Manager secrets for Azure SQL (server/database/username/password or connection string) and Dropbox (access_token). |
| **ECS credentials** | (Optional) Add `CREDENTIALS_SECRET_ARN` to the Azure SQL and Dropbox ECS task definitions so the MCP servers can read the secrets. |
| **Registry** | Insert connector items into `<prefix>-connectors` with `workspace_id`, `connector_type`, `endpoint.url` = `http://<connector-alb-dns>/azure-sql` or `/dropbox`. |
| **Request-handler** | Ensure the LangChain request-handler Lambda has `CONNECTORS_TABLE_NAME` and read access to the connector table. |
| **Chat** | Use a workspace that matches the connector’s `workspace_id` and ask questions that require SQL or Dropbox. |

For more on connector architecture, security, and registry schema, see [MCP_CONNECTORS_KNOWLEDGE_BASE.md](../MCP_CONNECTORS_KNOWLEDGE_BASE.md) and [CONNECTOR_SECURITY_ARCHITECTURE_REVIEW.md](../CONNECTOR_SECURITY_ARCHITECTURE_REVIEW.md).
