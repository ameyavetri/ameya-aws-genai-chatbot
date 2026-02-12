# 02-layers-and-modules-guide.md

## API Route → Handler Mapping

| GraphQL Operation | Field | Handler File |
|-------------------|-------|--------------|
| Query | `checkHealth` | `lib/chatbot-api/functions/api-handler/routes/health.py` |
| Query | `getUploadFileURL`, `listWorkspaces`, `createAuroraWorkspace`, etc. | `lib/chatbot-api/functions/api-handler/routes/rag.py`, `workspaces.py`, `documents.py`, `embeddings.py`, `cross_encoders.py`, `kendra.py`, `bedrock_kb.py`, `semantic_search.py`, `roles.py`, `applications.py`, `connectors.py` |
| Query | `listModels`, `listAgents` | `lib/chatbot-api/functions/api-handler/routes/models.py`, `agents.py` |
| Query | `listSessions`, `getSession`, `deleteSession` | `lib/chatbot-api/functions/api-handler/routes/sessions.py` |
| Query | `listConnectors`, `getConnector`, `testConnector`, `listConnectorFolder` | `lib/chatbot-api/functions/api-handler/routes/connectors.py` |
| Mutation | `sendQuery` | `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py` |
| Mutation | `publishResponse` | Inline JS resolver (none data source); invoked by `outgoing-message-appsync` |
| Subscription | `receiveMessages` | Inline JS resolver; subscribes to `publishResponse` |
| Mutation | `createConnector`, `updateConnector`, `deleteConnector`, `ingestFromConnector` | `lib/chatbot-api/functions/api-handler/routes/connectors.py` |

**Resolver wiring:** `lib/chatbot-api/rest-api.ts` — all Query/Mutation fields (except `sendQuery`, `publishResponse`) use `functionDataSource` → api-handler Lambda. Realtime fields defined in `lib/chatbot-api/appsync-ws.ts`.

---

## Layers/Modules Inventory

| Module | Purpose | Key Files | Public Interfaces | Dependencies | Constraints |
|--------|---------|-----------|-------------------|--------------|-------------|
| **Shared** | VPC, KMS, SSM config, common layer, PowerTools, API keys secret, WAF rules | `lib/shared/index.ts`, `lib/shared/types.ts`, `lib/shared/shared-asset-bundler.ts` | `Shared` construct, `defaultEnvironmentVariables`, `sharedCode`, `vpc`, `kmsKey` | CDK, ec2, kms, ssm, lambda | Config from `config.json` / `bin/config.json` |
| **Authentication** | Cognito UserPool, groups (admin, workspace_manager, user), OIDC/SAML federation | `lib/authentication/index.ts`, `lib/authentication/lambda/` | `userPool`, `userPoolClient`, `cognitoDomain`, `updateUserPoolClient` | CDK, cognito, lambda | Pre-sign-up/post-confirmation triggers for federated users |
| **ChatBotApi** | AppSync GraphQL API, WAF, resolvers, realtime (sendQuery, publishResponse, subscriptions) | `lib/chatbot-api/index.ts`, `lib/chatbot-api/rest-api.ts`, `lib/chatbot-api/websocket-api.ts`, `lib/chatbot-api/appsync-ws.ts`, `lib/chatbot-api/schema/schema.graphql` | `graphqlApi`, `messagesTopic`, `outBoundQueue`, `sessionsTable`, `applicationTable`, `filesBucket` | Shared, RagEngines, Authentication, Models | All Query/Mutation fields (except sendQuery, publishResponse) → api-handler |
| **api-handler** | GraphQL resolver Lambda; routes by `fieldName` to route modules | `lib/chatbot-api/functions/api-handler/index.py`, `lib/chatbot-api/functions/api-handler/routes/*.py` | AppSyncResolver `handler(event, context)` | genai_core, aws_lambda_powertools, pydantic | `POWERTOOLS_SERVICE_NAME`, `LOG_LEVEL`; VPC for Aurora/OpenSearch |
| **Realtime (sendQuery, publishResponse, receiveMessages)** | sendQuery → SNS; SQS → outgoing-message → publishResponse; subscriptions | `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py`, `lib/chatbot-api/functions/outgoing-message-appsync/index.ts`, `lib/chatbot-api/functions/resolvers/*.js` | GraphQL mutations `sendQuery`, `publishResponse`; Subscription `receiveMessages` | SNS, SQS, AppSync | Application-level auth in sendQuery (`applicationId` → Roles check) |
| **LangChain Interface** | Consumes SNS (direction=IN, modelInterface=langchain); RAG, connectors, LLM | `lib/model-interfaces/langchain/index.ts`, `lib/model-interfaces/langchain/functions/request-handler/index.py` | `ingestionQueue`, `requestHandler` | genai_core, LangChain, rag-engines, Bedrock/SageMaker/Nexus | 15 min timeout, 1024 MB |
| **Bedrock Agents Interface** | Consumes SNS (modelInterface=agent); Bedrock Agent | `lib/model-interfaces/bedrock-agents/index.ts` | `ingestionQueue`, `requestHandler` | Bedrock Agent API | Config `bedrock.agent.enabled` |
| **Idefics Interface** | Multimodal (images); SageMaker IDEFICS | `lib/model-interfaces/idefics/index.ts` | `ingestionQueue`, `requestHandler` | SageMaker, S3 | `model.interface === ModelInterface.MultiModal` |
| **WebSearch Interface** | Web/hybrid source mode; invokes WebSearch Lambda | `lib/model-interfaces/websearch/index.ts` | `ingestionQueue`, `webSearchLambda` | Secrets Manager | Filter: `sourceMode` in [web, hybrid] |
| **RagEngines** | Workspaces, documents, data import (file, website, RSS, connector), embeddings, cross-encoders | `lib/rag-engines/index.ts`, `lib/rag-engines/aurora-pgvector/`, `lib/rag-engines/opensearch-vector/`, `lib/rag-engines/kendra-retrieval/`, `lib/rag-engines/data-import/`, `lib/rag-engines/workspaces/` | `workspacesTable`, `documentsTable`, `uploadBucket`, `processingBucket`, workflows | Shared, ConnectorDynamoDBTables (optional) | Conditional on `config.rag.enabled` |
| **Connectors** | Connector DynamoDB table; Connector Gateway (ECS Fargate) for Azure SQL, SharePoint, Dropbox | `lib/connectors/connector-dynamodb-tables/index.ts`, `lib/connectors/connector-gateway/index.ts` | `connectorsTable`, `byWorkspaceIndexName` | Shared, VPC | `config.connectors.enabled`; at least one connector type enabled for Gateway |
| **genai_core** | Shared Python SDK: workspaces, documents, chunks, embeddings, connectors, auth, parameters | `lib/shared/layers/python-sdk/python/genai_core/*.py` | Module-level functions (e.g. `genai_core.workspaces.create_workspace_aurora`) | boto3, opensearch-py, psycopg2, langchain | PYTHONPATH includes `lib/shared/layers/python-sdk/python` |
| **Models** | SageMaker endpoints, Bedrock/Nexus config, SSM models parameter | `lib/models/index.ts` | `models`, `modelsParameter` | Shared, CDK | Driven by `config.llms.sagemaker`, `config.bedrock`, `config.nexus` |
| **UserInterface** | React app build, S3/CloudFront or private ALB deployment, aws-exports.json | `lib/user-interface/index.ts`, `lib/user-interface/react-app/`, `lib/user-interface/public-website.ts`, `lib/user-interface/private-website.ts` | `publishedDomain`, `cloudFrontDistribution`, `privateWebsite` | Shared, ChatBotApi, Authentication | `aws-exports.json` generated at deploy time |
| **Monitoring** | CloudWatch Dashboard, alarms, composite alarm SNS | `lib/monitoring/index.ts` | `compositeAlarmTopic` | cdk-monitoring-constructs | `advancedMonitoring` enables X-Ray, extra alarms |

---

## Change Safety Guide per Module

### Shared

| Action | Where | Patterns | Tests | Backward Compatibility | Do Not Break |
|--------|-------|----------|-------|------------------------|--------------|
| Add env var for Lambdas | `lib/shared/index.ts` → `defaultEnvironmentVariables` | Add to all Lambdas via shared props | — | Avoid removing/renaming env vars | KMS key aliases, config parameter name |
| Add new config option | `lib/shared/types.ts` → `SystemConfig`; `bin/config.ts` default | Use optional fields; normalize in getConfig | tests/utils/config-util.ts | Provide defaults for new fields | Existing required fields |
| Add WAF rule | `lib/shared/index.ts` → `webACLRules` | Append to array | — | Don't block existing valid traffic | — |

### api-handler (GraphQL Lambda)

| Action | Where | Patterns | Tests | Backward Compatibility | Do Not Break |
|--------|-------|----------|-------|------------------------|--------------|
| Add new Query/Mutation | `lib/chatbot-api/schema/schema.graphql`; new `routes/xxx.py`; `index.py` include_router | Follow existing route signatures: `@router.resolver(...)` with `field_name` | tests/chatbot-api/ | Additive only; don't remove fields | fieldName → route mapping; identity/claims access |
| Change RAG/workspace logic | `lib/chatbot-api/functions/api-handler/routes/rag.py`, `workspaces.py`; `genai_core` | Raise `CommonError` for business errors | tests/chatbot-api/ | Response shape for clients | `UserPermissions.approved_roles` checks |
| Add connector operation | `lib/chatbot-api/functions/api-handler/routes/connectors.py` | Use `genai_core.connectors.registry`, `orchestrator` | tests/chatbot-api/ | New fields optional | Secrets handling; workspace_id scope |

### Realtime (sendQuery / publishResponse / subscriptions)

| Action | Where | Patterns | Tests | Backward Compatibility | Do Not Break |
|--------|-------|----------|-------|------------------------|--------------|
| Change sendQuery payload shape | `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py`, `applications.py` | Validate with Pydantic `DataFieldValidation`, `InputValidation` | tests/chatbot-api/functions/outgoing-message-appsync.test.ts | Keep `action`, `modelInterface`, `direction`, `data` structure | SNS filter policies in stack (direction, modelInterface) |
| Change outgoing message format | `lib/chatbot-api/functions/outgoing-message-appsync/`, LangChain/Bedrock/Idefics handlers | `publishResponse(data, sessionId, userId)`; `data` must serialize to GraphQL | — | Client expects `sessionId`, `userId`, `data` | Subscription filter `receiveMessages(sessionId)` |
| Add new model interface | `lib/aws-genai-llm-chatbot-stack.ts` | New SNS subscription with `modelInterface` filter; new Lambda consumer | — | Existing interfaces unchanged | Message schema (`userId`, `direction`, `modelInterface`) |

### LangChain Interface

| Action | Where | Patterns | Tests | Backward Compatibility | Do Not Break |
|--------|-------|----------|-------|------------------------|--------------|
| Add RAG engine or retrieval change | `lib/model-interfaces/langchain/functions/request-handler/index.py` | `resolve_context_for_prompt`; workspace/document lookups via genai_core | tests/model-interfaces/ | Don't change prompt structure without versioning | Session history format (DynamoDBChatMessageHistory) |
| Add connector context | `lib/model-interfaces/langchain/functions/request-handler/index.py` | Use `connector_orchestrator.execute_query`; map to `connector_items` | — | Connector schema in DynamoDB | CONNECTORS_TABLE_NAME env |
| Change LLM provider behavior | `lib/shared/layers/python-sdk/python/genai_core/model_providers/`, `lib/model-interfaces/langchain/` | Registry pattern; Bedrock/SageMaker/Nexus clients | — | Model name format `provider::modelName` | — |

### RAG Engines

| Action | Where | Patterns | Tests | Backward Compatibility | Do Not Break |
|--------|-------|----------|-------|------------------------|--------------|
| Add new workspace engine | `lib/rag-engines/` new subfolder; Step Function + Lambda | Follow Aurora/OpenSearch/Kendra pattern; register in RagEngines index | tests/ | New engine opt-in via config | Workspace schema (workspace_id, object_type); Documents schema |
| Add data import source | `lib/rag-engines/data-import/` | File/website/RSS/connector workflows; update document status | — | Document status values | FILE_IMPORT_WORKFLOW_ARN, etc. |

### Connectors

| Action | Where | Patterns | Tests | Backward Compatibility | Do Not Break |
|--------|-------|----------|-------|------------------------|--------------|
| Add connector type | `lib/shared/layers/python-sdk/python/genai_core/connectors/`; Connector Gateway config | Registry; MCP client; Secrets Manager for creds | tests/shared/layers/python-sdk/genai_core/connectors/ | New type in schema; GraphQL additive | connector_id, workspace_id key schema; credentialsSecretArn |
| Add Connector Gateway service | `lib/connectors/connector-gateway/index.ts` | ECS Fargate service; ALB target group | — | Gateway URL for MCP calls | VPC, security groups |

---

## Integration Playbook

### Adding a New Connector/Provider/Tool

1. **Adapter location**
   - API routes: `lib/chatbot-api/functions/api-handler/routes/connectors.py` (CRUD, list_folder, ingest)
   - Chat context: `lib/shared/layers/python-sdk/python/genai_core/connectors/` (registry, orchestrator, connector-specific module)
   - Gateway (if HTTP MCP): `lib/connectors/connector-gateway/` (add ECS service + route)

2. **Configuration**
   - `lib/shared/types.ts` → `SystemConfig.connectors.<newType>.enabled`
   - `bin/config.ts` → default `enabled: false`
   - `lib/aws-genai-llm-chatbot-stack.ts` → conditional ConnectorGateway, connectorTables usage

3. **Auth/secrets**
   - Store credentials in Secrets Manager with naming pattern `genai-connector-*`
   - api-handler: `secretsmanager:GetSecretValue` on connector secrets (see stack IAM)
   - Use `genai_core.connectors.registry` for CRUD; never log secret values

4. **Logging/metrics**
   - Use `aws_lambda_powertools` Logger; `correlation_paths.APPSYNC_RESOLVER` for correlation
   - Publish custom metrics (e.g. `ConnectorQuerySuccess`) in orchestrator if needed

5. **Failure modes and retries**
   - Connector Lambda/ECS: implement retries in orchestrator; surface `CommonError` to client
   - DLQ for SQS; monitor `outgoing-message` DLQ for chat failures

### Adding a New LLM Model Interface

1. Create new construct in `lib/model-interfaces/<name>/`
2. Add SQS queue, Lambda, SNS subscription with `modelInterface` filter
3. Wire in `lib/aws-genai-llm-chatbot-stack.ts`: subscribe to `chatBotApi.messagesTopic` with filter
4. Implement message handling: parse `data`, call LLM, publish OUT to SNS
5. Ensure outgoing-message handler can parse response (token sequence for streaming)

---

## Refactor Guardrails

| Area | Safe to Refactor | High Risk | Suggested Seams |
|------|------------------|-----------|------------------|
| **api-handler routes** | Extract sub-modules, add helpers | Changing `fieldName` → route mapping; identity structure | Keep `handler` → `app.resolve`; router per domain |
| **SNS message schema** | Add optional fields | Changing `direction`, `modelInterface`, `userId`, `data` | Version payload; maintain backward parse |
| **genai_core** | New modules, internal refactors | Changing `workspaces`, `documents` table schemas; function signatures used by api-handler/request-handler | Keep workspace_id, document_id semantics |
| **DynamoDB tables** | Add GSI, new attributes | Change PK/SK, remove attributes | Migration scripts if schema change |
| **GraphQL schema** | Add types, optional args | Remove/rename fields; change auth directives | Deprecate before remove |
| **Config (config.json / SSM)** | Add optional keys | Remove/rename required keys | Default in `getConfig()` |
