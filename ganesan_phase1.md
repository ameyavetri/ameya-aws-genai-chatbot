SYSTEM INVENTORY — AWS GenAI LLM Chatbot
STEP 1 — Project Entry Points
Entry Point	File Path	Purpose	Framework/Runtime
CDK App Bootstrap	bin/aws-genai-llm-chatbot.ts	Initializes AWS CDK App, loads config, synthesizes AwsGenAILLMChatbotStack	AWS CDK, Node.js
CDK CLI Entry	cdk.json → "app": "npx ts-node --prefer-ts-exts bin/aws-genai-llm-chatbot.ts"	CDK CLI entrypoint for synth/deploy	ts-node, CDK CLI
Config CLI	cli/magic-config.ts (invoked via node ./dist/cli/magic.js config)	Interactive or non-interactive config generation (SeedFarmer)	Commander.js, Enquirer
React SPA	lib/user-interface/react-app/index.html → src/main.tsx	Web UI entrypoint	Vite, React 18
Lambda Handlers (Python)	Various lib/**/functions/**/index.py	Lambda entrypoints for API, realtime, RAG, model interfaces	AWS Lambda, Python 3.11/3.12
STEP 2 — Top-Level Modules / Packages
Module	Folder Path	Purpose	Key Files
Main Stack	lib/aws-genai-llm-chatbot-stack.ts	Top-level CDK stack; wires Authentication, Models, RAG, ChatBot API, User Interface	Single file stack definition
Shared	lib/shared/	Shared infra (VPC, KMS, SSM, layers, bundler)	index.ts, types.ts, shared-asset-bundler.ts
Authentication	lib/authentication/	Cognito User Pool, federation (OIDC/SAML), groups	index.ts
ChatBot API	lib/chatbot-api/	GraphQL (AppSync), REST, WebSocket, resolvers	index.ts, rest-api.ts, websocket-api.ts, schema/schema.graphql
RAG Engines	lib/rag-engines/	Aurora, OpenSearch, Kendra, KB, data import, workspaces	index.ts, aurora-pgvector/, opensearch-vector/, data-import/, workspaces/
Models	lib/models/	Bedrock, SageMaker, Nexus, model config	index.ts, sagemaker-schedule.ts
Model Interfaces	lib/model-interfaces/	LangChain, Bedrock Agents, Idefics, WebSearch	langchain/, bedrock-agents/, idefics/, websearch/
Connectors	lib/connectors/	Dropbox MCP, SharePoint MCP, DynamoDB tables, Connector Gateway (ECS/ALB)	connector-gateway/index.ts, connector-dynamodb-tables/, dropbox-mcp-server/
User Interface	lib/user-interface/	React app, public/private hosting, CloudFront	index.ts, react-app/src/, public-website.ts, private-website.ts
Monitoring	lib/monitoring/	CloudWatch alarms, X-Ray, monitoring	index.ts
STEP 3 — External Integrations
Service	Where Used	Relevant Files	Purpose
Amazon Bedrock	LLM inference, embeddings	lib/shared/layers/python-sdk/python/genai_core/clients.py, bedrock_agent/client.py	Claude, Titan embeddings, Cohere, agents
Amazon SageMaker	LLM/embedding endpoints	lib/sagemaker-model/, lib/models/	Deployed models (FalconLite, Mistral, etc.)
Nexus Gateway	Alternate model proxy	lib/shared/layers/python-sdk/python/genai_core/model_providers/nexus/	Unified model access behind gateway
OpenAI API	Text + embeddings	lib/shared/layers/python-sdk/python/genai_core/clients.py, embeddings.py, LangChain adapters	text-embedding-ada-002, GPT models
Azure OpenAI	Model access	lib/shared/layers/python-sdk/python/genai_core/model_providers/direct/models.py	Azure-hosted models
Cohere	Embeddings	genai_core/model_providers/direct/embeddings.py, provider.py	cohere.embed-english-v3, multilingual-v3
AWS Secrets Manager	Connector OAuth, API keys	lib/chatbot-api/functions/api-handler/routes/connectors.py, genai_core/connectors/connector_files.py	Connector and API secrets
Web Search (external)	WebSearch handler	lib/model-interfaces/websearch/functions/websearch-handler/index.py	HTTP GET to external search
Dropbox API	Connector	lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py	File listing, download
HuggingFace	Model hosting / API	lib/shared/layers/common/requirements.txt, llm_classifier.py	HuggingFace API key (optional)
Amazon Comprehend	Language detection	lib/shared/layers/python-sdk/python/genai_core/utils/comprehend.py	Text language detection
STEP 4 — Databases and Storage
Technology	Config/Connection	Data Access Layer	Models/Schema
DynamoDB (Sessions)	ChatBot API construct	genai_core/sessions.py	Sessions table, byUserId GSI
DynamoDB (Applications)	ApplicationDynamoDBTables	genai_core/applications.py, dynamodb_provider.py	Applications table
DynamoDB (Workspaces)	RagDynamoDBTables	genai_core/workspaces.py, documents.py	Workspaces, Documents tables
DynamoDB (Connectors)	ConnectorDynamoDBTables	genai_core/connectors/registry.py	Connectors table
Aurora PostgreSQL (pgvector)	lib/rag-engines/aurora-pgvector/	genai_core/aurora/, workspace_retriever.py	Vector store for RAG
OpenSearch	lib/rag-engines/opensearch-vector/	genai_core/opensearch/client.py	Vector index
Amazon Kendra	lib/rag-engines/kendra-retrieval/	genai_core/kendra/client.py	Managed search index
S3 (Upload)	DataImport	genai_core/documents.py, chunks.py	Upload bucket
S3 (Processing)	DataImport	genai_core/chunks.py, file-import	Processing bucket
S3 (Chatbot Files)	ChatBotS3Buckets	genai_core/files.py, presign	User file storage
S3 (User Feedback)	ChatBotS3Buckets	genai_core/user_feedback.py	Feedback storage
SSM Parameter Store	Shared	lib/shared/index.ts	Config and models parameter
STEP 5 — Background Jobs / Schedulers
Job Name	Trigger	File Path	Processes
SageMaker Start Schedule	AWS EventBridge Scheduler (cron)	lib/models/sagemaker-schedule.ts	Start SageMaker endpoints
SageMaker Stop Schedule	AWS EventBridge Scheduler (cron)	lib/models/sagemaker-schedule.ts	Stop SageMaker endpoints
RSS Feed Poll	EventBridge Rule (every 15 min)	lib/rag-engines/data-import/rss-subscription.ts	Invoke RSS ingestor Lambda
RSS Post Crawl	EventBridge Rule (every 5 min)	lib/rag-engines/data-import/rss-subscription.ts	Batch crawl queued RSS posts
File Import Workflow	S3 events / manual start	lib/rag-engines/data-import/file-import-workflow.ts	Step Functions → AWS Batch
Website Crawling Workflow	Triggered by RSS or manual	lib/rag-engines/data-import/website-crawling-workflow.ts	Step Functions → Web Crawler Batch
Connector File Import Workflow	API-initiated	lib/rag-engines/data-import/connector-file-import-workflow.ts	Step Functions → File Import Batch
File Import Batch Job	Step Functions	lib/rag-engines/data-import/file-import-batch-job.ts	Fargate container for file processing
Web Crawler Batch Job	Step Functions	lib/rag-engines/data-import/web-crawler-batch-job.ts	Fargate container for web crawling
STEP 6 — Message Queues / Events
Technology	Producer	Consumer	Event Types
SNS (Messages Topic)	SendQuery resolver, WebSocket	LangChain, Idefics, Bedrock Agents, WebSearch via SQS	Inbound chat messages (direction, modelInterface filters)
SQS (Outgoing Messages)	EventBridge (from model responses)	OutgoingMessageHandler Lambda	Outbound LLM responses to WebSocket
SQS (LangChain Ingestion)	SNS subscription	LangChain RequestHandler Lambda	modelInterface=langchain messages
SQS (Idefics Ingestion)	SNS subscription	Idefics RequestHandler Lambda	MultiModal/idefics messages
SQS (Bedrock Agents Ingestion)	SNS subscription	Bedrock Agents RequestHandler Lambda	modelInterface=agent messages
SQS (WebSearch Ingestion)	SNS subscription	WebSearchHandler Lambda	modelInterface=websearch, source web/hybrid
SQS (Data Import Ingestion)	Upload handler, connector workflows	File Import Batch Job	RAG document ingestion
STEP 7 — Authentication and Authorization
Aspect	Details	Files
Strategy	Cognito User Pool (email/password) + optional federation	lib/authentication/index.ts
Identity Providers	Native Cognito, OIDC, SAML	lib/authentication/index.ts
Groups	admin, workspace_manager, user	lib/authentication/index.ts (CfnUserPoolGroup)
Role Mapping	custom:chatbot_role from OIDC/SAML	lib/authentication/lambda/addFederatedUserToUserGroup/index.py
Triggers	PreSignUp, PostConfirmation (federated)	lib/authentication/index.ts
API Auth	AppSync: USER_POOL + IAM	lib/chatbot-api/index.ts
Middleware	WAF rate limiting (SendQuery)	lib/chatbot-api/index.ts (createWafRules)
STEP 8 — API Layer and Service Layer
Layer	Technology	Route/Resolver Definitions	Service / Logic
GraphQL API	AWS AppSync	lib/chatbot-api/schema/schema.graphql	Queries, mutations, subscriptions
AppSync Resolver	Lambda (Python)	lib/chatbot-api/rest-api.ts	Single Lambda for all resolvers
API Handler Routes	AppSyncResolver (Python)	lib/chatbot-api/functions/api-handler/	health, embeddings, rag, models, workspaces, sessions, documents, connectors, etc.
WebSocket API	AppSync Realtime	lib/chatbot-api/websocket-api.ts, appsync-ws/	Real-time chat over WebSocket
SendQuery Resolver	Lambda	lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py	Publish to SNS Messages Topic
Outgoing Message Handler	Lambda	lib/chatbot-api/websocket-api.ts	Consume SQS, push to WebSocket
REST (GraphQL over HTTP)	API Gateway → AppSync	GraphQL over HTTPS	Same schema as AppSync
GraphQL Schema (main operations):
lib/chatbot-api/schema/schema.graphql defines queries (e.g. listSessions, getWorkspace), mutations (e.g. sendQuery, createWorkspace), and subscriptions (e.g. subscribeToResponse).
STEP 9 — Deployment and Runtime Components
Component	Runtime	Dependencies
CDK Stack	AWS CloudFormation	Node.js 18+, aws-cdk-lib, cdk-nag
Lambda (Python)	Python 3.11/3.12	boto3, LangChain, genai_core layer
Lambda (Node)	Node.js 20	Cognito, OIDC/SAML update Lambdas
ECS Fargate (Connector Gateway)	ECS on Fargate	VPC, ALB, Dropbox/SharePoint MCP images
ECS Fargate (Batch)	AWS Batch	File Import, Web Crawler containers
React SPA	Static (S3 + CloudFront)	Vite build, Cognito, AppSync, WebSocket
Docker	Container images	lib/connectors/dropbox-mcp-server/Dockerfile, lib/shared/file-import-dockerfile, web-crawler-dockerfile
CI/CD	GitHub Actions	.github/workflows/build.yaml, deploy.yml (VitePress), e2e-validation.yml
SeedFarmer	Optional deployment	aws-genai-llm-chatbot/, cli/magic-config.ts (non-interactive mode)
STEP 10 — Final System Inventory Summary
1. System Purpose
Enterprise AI chatbot with multi-provider LLMs and RAG, conversation memory, optional connectors (Dropbox/SharePoint), and a React UI.
2. Entry Points
CDK: bin/aws-genai-llm-chatbot.ts
Config: cli/magic-config.ts (npm run config)
Web UI: lib/user-interface/react-app/src/main.tsx
Lambdas: multiple index.py under lib/**/functions/**/
3. Core Modules
Shared, Authentication, ChatBotApi, RagEngines, Models, Model Interfaces (LangChain, Bedrock Agents, Idefics, WebSearch), Connectors, UserInterface, Monitoring.
4. External Integrations
Bedrock, SageMaker, Nexus Gateway, OpenAI, Azure OpenAI, Cohere, Secrets Manager, web search, Dropbox, HuggingFace, Comprehend.
5. Databases and Storage
DynamoDB (sessions, applications, workspaces, documents, connectors), Aurora pgvector, OpenSearch, Kendra, S3 (upload, processing, chatbot files, feedback), SSM Parameter Store.
6. Background Jobs
EventBridge Scheduler (SageMaker start/stop), EventBridge Rules (RSS poll every 15 min, crawl every 5 min), Step Functions (file import, website crawl, connector import, workspace/document delete).
7. Event/Queue Systems
SNS Messages Topic → SQS for model interfaces; SQS for outgoing WebSocket messages; SQS for data import ingestion.
8. Authentication Model
Cognito User Pool (email) with optional OIDC/SAML federation; groups (admin, workspace_manager, user); AppSync USER_POOL + IAM.
9. API Architecture
AppSync GraphQL (queries, mutations, subscriptions) with Lambda resolvers; AppSync Realtime WebSocket; API Gateway for GraphQL over HTTP where used.
10. Deployment Model
CDK synthesizes CloudFormation; optional SeedFarmer; GitHub Actions for docs/deploy; SPA via S3 + CloudFront or private ALB.
Architecture Questions / Needs Verification
Item	Location	Question
Azure SQL connector	Deleted: lib/connectors/azure-sql-mcp-server/ (per git status)	Whether a replacement connector is planned
REST API vs GraphQL	lib/chatbot-api/rest-api.ts	If REST endpoints are exposed beyond GraphQL; rest-api suggests REST but content is GraphQL
Nexus Gateway integration	lib/model-interfaces/langchain/, Nexus config	Exact wiring when Nexus is the sole model provider
MCP protocol usage	genai_core/connectors/mcp_client.py, dropbox-mcp-server	Exact MCP protocol version and usage scope
Private website	lib/user-interface/private-website.ts	Whether ALB handles Cognito or if it uses a different auth pattern
React build for deploy	lib/user-interface/index.ts	Exact build command used before S3 deployment (npm run build vs Vite CLI)
VitePress deploy	.github/workflows/deploy.yml