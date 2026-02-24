# 03-deployment-and-operations.md

## How to Run Locally

### Prerequisites

- **Node.js 18+** (< 21), **npm**, **Python 3.9+**
- **AWS CLI** configured with credentials
- **AWS CDK CLI** (compatible with aws-cdk-lib 2.212+)
- **Docker** (with buildx) — for Lambda asset bundling, SageMaker container builds
- **Git** (repo: `aws-samples/aws-genai-llm-chatbot`)

References: `README.md`, `docs/guide/deploy.md`

### Environment Variables

| Variable | Purpose | Source |
|----------|---------|--------|
| `CDK_DEFAULT_ACCOUNT` | AWS account for deploy | `aws sts get-caller-identity` |
| `CDK_DEFAULT_REGION` | Target region | Set or use AWS CLI default |
| `AWS_PROFILE` | Optional CLI profile | — |
| `DOCKER_DEFAULT_PLATFORM` | Set by Shared for Lambda build | `linux/amd64` |

### Local Backend (Deploy to AWS)

No local API/backend server. Backend runs entirely in AWS. To develop:

1. **Deploy stack** (see [Deployment](#build--release) below)
2. **Use deployed AppSync + Cognito** for API calls

### Local Frontend

**Option 1: Fetch aws-exports from deployed site**

```bash
cd lib/user-interface/react-app/public
curl -O https://<your-cloudfront-domain>/aws-exports.json
cd ..
npm install
npm run dev
```

**Option 2: Environment variables**

```bash
cd lib/user-interface/react-app
export AWS_PROJECT_REGION="..."
export AWS_COGNITO_REGION="..."
export AWS_USER_POOLS_ID="..."
export AWS_USER_POOLS_WEB_CLIENT_ID="..."
export API_DISTRIBUTION_DOMAIN_NAME="..."
export RAG_ENABLED=1
export DEFAULT_EMBEDDINGS_MODEL="..."
export DEFAULT_CROSS_ENCODER_MODEL="..."
npm run build:dev
npm run dev
```

**Ports:** Vite dev server typically runs on `5173` (see `lib/user-interface/react-app/vite.config.ts`).

**Reference:** `lib/user-interface/react-app/README.md`

### DevContainer / Codespaces

- **DevContainer:** `.devcontainer/devcontainer.json` — Node 18, AWS CDK, AWS CLI, Docker-in-Docker
- **GitHub Codespaces:** Supported; follow `docs/guide/deploy.md` “Github Codespaces” section

### Docker Compose

No `docker-compose` for local full-stack run. Lambda and AppSync are AWS-only.

---

## Build & Release

### Build Steps

```bash
# Root
npm ci
npm run build          # amplify codegen + tsc

# Optional: tests
npm run test           # Jest (CDK, constructs)
pip install -r pytest_requirements.txt
pytest tests/          # Python unit tests

# Frontend only
cd lib/user-interface/react-app && npm ci && npm run build
```

**Artifacts:**
- `dist/` — compiled TypeScript (bin, lib, cli)
- `lib/user-interface/react-app/dist/` — Vite build output
- CDK synthesis: `cdk.out/`

**Versioning:** Package version in `package.json` (`version`) and `pyproject.toml` (`version`). No separate release pipeline versioning in this repo.

### Configuration (config.json)

- **Paths:** `bin/config.json` (preferred) or `config.json` (root)
- **Generation:** `npm run config` runs `cli/magic.ts` interactive wizard
- **Defaults:** `bin/default-config.json`; fallback in `bin/config.ts` (`getConfig()`)

### Deploy

```bash
# Bootstrap (first-time per account/region)
npm run cdk bootstrap aws://<accountId>/<region>

# Deploy
npm run cdk deploy
# Or: npx cdk deploy
```

**CI/CD:**
- **Smoke build:** `.github/workflows/build.yaml` — lint, build, test, `cdk synth`, pytest
- **Docs deploy:** `.github/workflows/deploy.yml` — VitePress docs to GitHub Pages
- **E2E validation:** `.github/workflows/e2e-validation.yml` — triggers CodePipeline (requires `PIPELINE_*` secrets)

**SeedFarmer:** `aws-genai-llm-chatbot/seedfarmer.yaml` exists; project primarily uses direct CDK deploy. TBD: module layout in `aws-genai-llm-chatbot/modules/`.

### Intent Detection and Prompt Templates (Post-Deploy)

- **Intent detection:** Default rule-based classifier; set `INTENT_CLASSIFIER_ENABLED=true` and `INTENT_CLASSIFIER_MODEL` on the LangChain request-handler for LLM-based classification (requires Bedrock).
- **Prompt templates:** Configure per application in Admin UI: System Prompt, System Prompt when using workspace, Condense System Prompt, Intent Prompts (JSON). Or edit `lib/model-interfaces/langchain/functions/request-handler/adapters/shared/prompts/staffing_prompts.py` for built-in intent-specific prompts (requires redeploy).

### Verifying OpenAI document input (post-deploy)

After deploying changes to model metadata (e.g. OpenAI GPT document support), redeploy the stack so the api-handler Lambda picks up the updated genai_core layer. Then: Admin UI → Applications → Create/Edit Application → select an OpenAI GPT model (e.g. gpt-4, gpt-4o) and confirm the "Allow Document Input" toggle is enabled. Enabling it permits end users to upload documents in chat for that application.

---

## Deployment Architecture

### Cloud Services Used

| Service | Role |
|---------|------|
| **AppSync** | GraphQL API (Query, Mutation, Subscription) |
| **Lambda** | api-handler, sendQuery, outgoing-message, LangChain/Bedrock/Idefics/WebSearch handlers, RAG/import Lambdas |
| **Cognito** | User pool, groups (admin, workspace_manager, user), OIDC/SAML |
| **DynamoDB** | Sessions, Applications, Workspaces, Documents, Connectors |
| **S3** | Website bucket, chatbot files, upload, processing |
| **SNS** | Messages topic (direction/modelInterface routing) |
| **SQS** | Outbound queue, DLQ, ingestion queues per model interface |
| **CloudFront** | Public website distribution (when not private) |
| **ALB** | Private website or Connector Gateway |
| **VPC** | Created or imported; private subnets for Lambdas |
| **Aurora Serverless v2** | RAG (pgvector) when `rag.engines.aurora.enabled` |
| **OpenSearch Serverless** | RAG when `rag.engines.opensearch.enabled` |
| **Kendra** | RAG when `rag.engines.kendra.enabled` |
| **Bedrock** | LLMs, embeddings, optional Knowledge Base, Agents |
| **SageMaker** | Self-hosted LLMs, embeddings, cross-encoders |
| **ECS Fargate** | Connector Gateway (Azure SQL, SharePoint, Dropbox MCP servers) |
| **Secrets Manager** | API keys, config secrets, connector credentials |
| **SSM Parameter Store** | Config parameter, models parameter |
| **Step Functions** | File import, website crawl, workspace create/delete |
| **Batch** | File import, web crawler jobs |

### Networking

- **Public:** CloudFront → S3 (website); AppSync regional endpoint
- **Private website:** ALB → S3 website in VPC; no CloudFront
- **AppSync:** Private or public based on `config.privateWebsite`
- ** Lambdas:** In VPC private subnets (NAT for outbound)

### IAM Model

- Each Lambda has a dedicated execution role
- Least-privilege via CDK `grant*` and `addToRolePolicy`
- api-handler: DynamoDB, S3, Step Functions, Bedrock/Kendra/OpenSearch/Aurora, Secrets Manager, Cognito list groups
- Connector Gateway ECS tasks: IAM role for MCP/connector access

---

## Config & Secrets Management

### Environment Variables (Runtime)

- **Source:** CDK sets env vars on Lambda constructs at deploy time
- **Config:** `CONFIG_PARAMETER_NAME` → SSM Parameter Store (JSON)
- **Models:** `MODELS_PARAMETER_NAME` → SSM
- **Secrets:** `API_KEYS_SECRETS_ARN`, `X_ORIGIN_VERIFY_SECRET_ARN` → Secrets Manager
- **Intent classifier (optional):** `INTENT_CLASSIFIER_ENABLED` (true/false), `INTENT_CLASSIFIER_MODEL` (e.g. `anthropic.claude-3-haiku-20240307-v1:0`) — set on LangChain request-handler when using LLM-based intent detection

### Config Parameter (SSM)

- Populated from `config.json` at deploy
- Lambdas read via `genai_core.parameters.get_config()` or equivalent
- **File:** `lib/shared/index.ts` (configParameter), `genai_core.parameters`

### Secrets

- **API Keys:** Single secret (stack output `ChatbotApiKeysSecretName`) holds JSON: `OPENAI_API_KEY`, etc.
- **Connector credentials:** Per-connector secrets; naming `genai-connector-*`
- **Rotation:** TBD; manual rotation supported by updating secret value; Lambdas cache for ~60 seconds

### Frontend Config

- **File:** `aws-exports.json` — generated at deploy, deployed to S3/CloudFront
- **Content:** Cognito ids, AppSync endpoint, region, `config.rag_enabled`, `config.connectors_enabled`, etc.
- **Reference:** `lib/user-interface/index.ts` (exportsAsset)

---

## Observability

### Logging

- **Library:** AWS Lambda PowerTools (Python `Logger`, TypeScript `Logger`)
- **Format:** JSON (`LoggingFormat.JSON`)
- **Level:** `LOG_LEVEL` env (default `INFO`); `POWERTOOLS_LOG_EVENT: false` for event bodies
- **Correlation:** `correlation_paths.APPSYNC_RESOLVER` for AppSync requests
- **Log Groups:** `/aws/lambda/<function-name>`; retention from `config.logRetention` (default 7 days)

### Tracing

- **X-Ray:** Enabled when `config.advancedMonitoring === true`
- **Propagation:** Via PowerTools Tracer; outgoing-message uses subsegments for AppSync calls

### Metrics & Dashboards

- **Dashboard:** `lib/monitoring/index.ts` — CloudWatch Dashboard via `cdk-monitoring-constructs`
- **Widgets:** AppSync (4XX/5XX, latency), resolver logs, LLM handler logs, DynamoDB, SQS, Aurora, OpenSearch, Kendra, S3, Step Functions
- **Alarms:** 5XX faults, latency P90, DLQ depth; optional with advanced monitoring
- **Composite Alarm:** SNS topic (`CompositeAlarmTopicOutput`) for alerting

### Health Endpoints

| Endpoint | Type | Auth | Purpose |
|----------|------|------|---------|
| `checkHealth` | GraphQL Query | Cognito | Returns `true`; lightweight API liveness |
| Connector Gateway `/health` | HTTP | None | ALB target group health check |
| MCP servers (Azure SQL, Dropbox) `/health` | HTTP | None | Container health |

**File:** `lib/chatbot-api/functions/api-handler/routes/health.py`, `lib/connectors/connector-gateway/index.ts`

---

## Troubleshooting Guide

### Common Failure Points

| Symptom | Where to Look | Likely Cause |
|---------|---------------|--------------|
| Chat no response / timeout | LangChain request-handler logs | LLM timeout, Bedrock/SageMaker throttling, VPC/egress, intent/prompt resolution errors |
| Chat rephrases question instead of answering | LangChain request-handler logs; Application config | Condense vs QA chain confusion; ensure workspace/RAG enabled for document Q&A; check `intentPrompts` / system prompts |
| 403 on GraphQL | Cognito, WAF | User not in group; WAF rate limit (100/10min per IP) |
| Connector test fails | api-handler logs, Connector Gateway logs | Credentials invalid, MCP unreachable, ECS task unhealthy |
| RAG semantic search empty | api-handler, RAG workflows | Workspace not indexed; document status; Aurora/OpenSearch connectivity |
| Outgoing message not received | outgoing-message Lambda, SQS DLQ | PublishResponse mutation failure; check DLQ |
| UI "Configuration error" | Browser console, `/aws-exports.json` | Missing or invalid aws-exports; CORS; wrong domain |

### Log Locations

| Component | Log Group |
|-----------|-----------|
| api-handler | `/aws/lambda/<stack>-ChatBotApi-RestApi-GraphQLApiHandler*` |
| sendQuery | `/aws/lambda/<stack>-ChatBotApi-Realtime-*lambda-resolver*` |
| outgoing-message | `/aws/lambda/<stack>-ChatBotApi-Realtime-*outgoing-message*` |
| LangChain handler | `/aws/lambda/<stack>-LangchainInterface-RequestHandler*` |
| Connector Gateway ECS | `/ecs/<cluster>/<service>` (if configured) |

### Correlation IDs

- AppSync: `correlation_paths.APPSYNC_RESOLVER` injects correlation ID from request
- Use CloudWatch Logs Insights: `fields @timestamp, @message | filter correlation_id = "..."`

### WAF Rate Limit

- Rule `LimitLLMRequestsPerIP`: blocks when requests exceed `config.llms.rateLimitPerIP` (default 100) per 10 minutes
- VPC NAT IPs exempt via `AllowInternalCalls`
- **File:** `lib/chatbot-api/index.ts` (createWafRules)

---

## Rollback Strategy

**Current state:** No automated rollback in this repo. Deployments are immutable (CloudFormation stack updates).

### Recommended Rollback Approach

1. **CloudFormation rollback**
   - For failed stack update: CloudFormation automatically rolls back to previous stack state
   - For manual rollback: redeploy previous CDK app version (e.g. from git tag)

2. **Blue/green for frontend**
   - CloudFront/S3: New deployment overwrites; previous version not retained by default
   - Mitigation: Use S3 versioning; retain previous `dist` artifact and re-run BucketDeployment if needed

3. **Database / state**
   - DynamoDB: No automatic rollback; Point-in-Time Recovery available
   - Aurora/OpenSearch: Same; rely on backups

4. **Operational rollback**
   - Revert `config.json` and redeploy if config change caused issues
   - For Lambda: Rollback = redeploy previous code (new version deploy)

### Pre-Rollback Checklist

- [ ] Identify last known-good commit/tag
- [ ] Ensure `config.json` / `bin/config.json` compatible with that version
- [ ] Check CloudFormation stack status; do not rollback mid-update
- [ ] If connectors/credential changes: verify Secrets Manager state
