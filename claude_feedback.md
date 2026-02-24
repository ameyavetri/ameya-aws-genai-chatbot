AWS GenAI LLM Chatbot — Architecture Analysis

How It's Designed: Layer-by-Layer
1. Infrastructure Layer (AWS CDK, TypeScript)
Everything is provisioned as code via CDK constructs, organized in lib/. Each major concern is its own Construct:

Shared — VPC, KMS, SSM config, Lambda layers (PowerTools, common Python SDK), WAF rules, API key secrets
Authentication — Cognito UserPool with email auth and optional OIDC/SAML federation; Lambda triggers for pre-signup/post-confirmation
ChatBotApi — AppSync GraphQL API (USER_POOL + IAM auth), WAF, all DynamoDB tables, SNS topic, SQS queues, S3 buckets
RagEngines — Aurora pgvector, OpenSearch Serverless, Kendra, Bedrock Knowledge Base; Step Functions for workspace and document lifecycle
LangChainInterface, BedrockAgentsInterface, IdeficsInterface — each is an independent Lambda consumer off the SNS topic
Connectors — DynamoDB, Secrets Manager, ECS Fargate Connector Gateway for MCP-based external systems
UserInterface — CloudFront-hosted React SPA

The config-driven approach (via config.json / SSM Parameter Store) means which RAG engines, models, connectors, and features exist is all toggled at deploy time without code changes.

2. API Layer (AppSync GraphQL)
AppSync serves as the single API surface for both REST-style operations (CRUD on workspaces, applications, connectors, documents) and real-time streaming (chat). All field resolvers — except sendQuery and publishResponse — are routed to the api-handler Lambda, which internally dispatches by fieldName to Python route modules under lib/chatbot-api/functions/api-handler/routes/.
Authorization is schema-level via @aws_cognito_user_pools(cognito_groups: [...]) — clean, declarative RBAC.

3. Chat Message Bus (SNS/SQS Fan-Out)
This is the core runtime pattern:
sendQuery Lambda
    → SNS topic (direction=IN, modelInterface=<langchain|agent|idefics>)
        → SQS per interface (filter by modelInterface)
            → Lambda consumer (LangChain / Bedrock Agent / Idefics)
                → LLM (Bedrock / SageMaker / Nexus)
                    → SNS topic (direction=OUT)
                        → outgoing-message Lambda
                            → AppSync publishResponse mutation
                                → WebSocket subscription → Frontend
The SNS message filter on modelInterface and direction is what enables clean fan-out to multiple handler types without coupling. This is a deliberately async, event-driven design — chat is not synchronous HTTP.

4. LangChain Interface (Core Backend Runtime)
lib/model-interfaces/langchain/functions/request-handler/ is the workhorse:

Loads session history from DynamoDB (DynamoDBChatMessageHistory)
Resolves RAG context if a workspaceId is set (resolve_context_for_prompt → Aurora, OpenSearch, Kendra, Bedrock KB)
Pulls connector context via Connector Gateway (MCP)
Calls the LLM via LangChain (adapter pattern — ChatBedrockConverse and equivalents)
Streams tokens back via SNS OUT messages

The model provider abstraction lives in lib/shared/layers/python-sdk/python/genai_core/model_providers/ — Bedrock, SageMaker, Nexus are registered in a registry, selected by provider::modelName key format.

5. RAG Pipeline
Workspaces are the unit of RAG configuration. Each workspace maps to one engine (Aurora pgvector, OpenSearch, Kendra, Bedrock KB). Document ingestion (file, website, RSS, connector) is handled by Step Functions workflows, not inline Lambda. This keeps ingestion decoupled from query-time retrieval.

6. Frontend (React 18, Cloudscape Design System)
Built with Vite, AWS Amplify (auth + AppSync client), and Cloudscape. The Amplify subscription model handles WebSocket streaming from AppSync — tokens render progressively as they arrive. The UI has distinct sections for chat playground, workspace/RAG management, application management, connector management, and admin.

Design Pros
Modularity via CDK Constructs. Each system concern is a CDK Construct with explicit input props. Adding or removing a RAG engine or model interface doesn't touch unrelated infrastructure. This is genuinely good IaC design.
Config-driven deployment. Whether Aurora, OpenSearch, Kendra, Bedrock KB, Connectors, or specific model interfaces are deployed is controlled purely by config.json. Zero conditional code in runtime.
Clean async message bus. The SNS→SQS→Lambda pattern with attribute filtering means model interfaces are fully decoupled from the API layer. Adding a new model interface (e.g., OpenAI) only requires a new SNS subscription filter and Lambda — no changes to sendQuery or the frontend.
Real-time streaming without WebSocket server management. AppSync subscriptions handle the WebSocket layer. Streaming is achieved by publishing multiple partial response messages through the SNS→outgoing-message→AppSync pipeline. No custom WebSocket server to manage.
Declarative RBAC at the schema level. GraphQL schema annotations on Cognito groups mean authorization is auditable and not scattered in Lambda business logic.
Shared Python SDK layer (genai_core). All business logic (workspace queries, document management, model provider registry, connector orchestration) is centralized in a Lambda Layer shared across all Lambda functions. This prevents drift.
Lambda PowerTools. Structured JSON logging, tracing, and metrics are baked in via the PowerTools layer. The logging format and retention are config-driven.
Step Functions for document ingestion. Ingestion workflows are durable and observable, not fire-and-forget Lambdas. Status tracking in DynamoDB is a first-class concern.

Design Cons and Genuine Risk Areas
Lambda cold start sensitivity. The LangChain request handler is 1024 MB with a 15-minute timeout, loaded with Python dependencies including LangChain, boto3, and provider-specific libraries. Cold starts on this function will be noticeable (1-3+ seconds). There's mitigation via the Lambda Layer (separating dependencies from code) but no provisioned concurrency strategy documented.
15-minute Lambda timeout for long-running RAG operations. For large document corpora or slow LLM responses, the LangChain handler could approach this ceiling. There's no circuit breaker or graceful timeout-and-retry visible at the architecture level.
SNS→SQS→Lambda latency for streaming. The streaming path involves SNS publish → SQS delivery → Lambda batch trigger → AppSync mutation → WebSocket push — for every token chunk. This adds per-token latency that a direct WebSocket streaming approach (e.g., API Gateway WebSocket or Bedrock's streaming SDK directly to a connection) would not have. At scale, this also means high SNS/SQS message volume per conversation.
No visible rate limiting or per-user throttling at the message bus level. AppSync has WAF at the edge, but there's no per-user request quota visible in the sendQuery path. A single user can flood the SNS topic.
api-handler is a single Lambda with fieldName dispatch. All GraphQL non-streaming operations (workspace CRUD, document ops, connector CRUD, semantic search, user management) go through one Lambda with internal routing. This is a monolithic handler — it shares memory, cold start, IAM role, and VPC config across all operations. As route modules grow, this becomes a scaling and isolation concern.
DynamoDB as session store with no TTL visible in the module docs. Chat sessions accumulate indefinitely unless TTL is configured on the table. Large session histories also affect LangChain context window usage since DynamoDBChatMessageHistory loads the full history.
LangChain as a hard dependency. LangChain's API surface has historically been unstable (v0.1 → v0.2 → v0.3 had significant breaking changes). The adapter pattern (base.py) mitigates this partially, but the entire inference pipeline depends on LangChain chain types (ConversationChain, ConversationalRetrievalChain, RunnableWithMessageHistory). A LangChain upgrade is a high-risk operation.
Connector Gateway is ECS Fargate (always-on cost). The MCP Connector Gateway runs as persistent ECS services, incurring baseline compute cost even when no connectors are in use. There's no scale-to-zero mechanism for connectors.
Frontend bundle coupling. The React app is a single SPA with all features included. Feature flags exist at the config level, but the frontend doesn't appear to do code splitting per feature. Admin, workspace management, and chat are all bundled together regardless of the user's role.
OpenSearch Serverless and Aurora are both deployed simultaneously if both RAG engines are enabled. There's no shared vector store abstraction — workspaces are bound 1:1 to an engine type. Cross-engine search or engine migration is not supported.

Summary Verdict
This is a well-structured, AWS-native enterprise platform with strong IaC practices, clean separation of concerns across CDK constructs, and a thoughtful async event-driven backbone. The config-driven modularity makes it genuinely extensible for new model providers, RAG engines, and connectors without touching existing code paths.
The main architectural debt areas are: the per-token SNS/SQS streaming overhead, the monolithic api-handler Lambda, LangChain version fragility, and the always-on cost profile of ECS Connector Gateway. These are solvable incrementally and none are blocking for most enterprise use cases, but they are the right places to invest engineering attention as the platform scales.