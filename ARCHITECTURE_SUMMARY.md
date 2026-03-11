# AWS GenAI LLM Chatbot — Architecture Summary

**Status:** Validated against System Inventory  
**Date:** 2025-03-10

---

## 1. Architecture Overview

The system is an **enterprise AI chatbot** with:
- Multi-provider LLM support (Bedrock, SageMaker, Nexus Gateway, OpenAI)
- RAG over Aurora pgvector, OpenSearch, Kendra, Bedrock KB
- Real-time chat via AppSync GraphQL + WebSocket
- Connectors (Dropbox, SharePoint) via MCP over ECS Fargate
- Cognito authentication with optional OIDC/SAML federation

**Data flow (high-level):** User → React SPA → AppSync (GraphQL/WebSocket) → Lambda resolvers → SNS Messages Topic → Model interfaces (LangChain/Bedrock Agents/Idefics/WebSearch) → LLM providers → SQS Outgoing → WebSocket → User.

---

## 2. Component List (Stabilized)

### 2.1 User-Facing / Edge

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C01 | React SPA | Web App | Vite + React 18, Cognito-hosted UI, AppSync client |
| C02 | CloudFront (public) | CDN | Serves SPA, API proxy; WAF optional |
| C03 | Private ALB (optional) | Load Balancer | For private website mode |

### 2.2 Authentication

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C10 | Cognito User Pool | IdP | Email/password, groups (admin, workspace_manager, user) |
| C11 | Cognito Federation | IdP | Optional OIDC/SAML with custom:chatbot_role |
| C12 | AddFederatedUserToUserGroup | Lambda | PreSignUp/PostConfirmation trigger for group assignment |

### 2.3 API Layer

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C20 | AppSync GraphQL API | API | Queries, mutations; USER_POOL + IAM auth |
| C21 | AppSync Realtime (WebSocket) | API | Real-time chat, subscribeToResponse |
| C22 | API Handler Lambda | Lambda | Single Lambda for all GraphQL resolvers (Python) |
| C23 | SendQuery Resolver | Lambda | Publishes chat message to SNS Messages Topic |
| C24 | Outgoing Message Handler | Lambda | Consumes SQS, pushes responses to WebSocket |
| C25 | WAF (AppSync) | Security | Rate limiting for SendQuery |

### 2.4 Message Bus

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C30 | SNS Messages Topic | Pub/Sub | Routes messages by direction, modelInterface |
| C31 | SQS Outgoing Queue | Queue | Outbound LLM responses to WebSocket |
| C32 | SQS LangChain Ingestion | Queue | SNS → LangChain RequestHandler |
| C33 | SQS Bedrock Agents Ingestion | Queue | SNS → Bedrock Agents RequestHandler |
| C34 | SQS Idefics Ingestion | Queue | SNS → Idefics RequestHandler |
| C35 | SQS WebSearch Ingestion | Queue | SNS → WebSearch Handler |
| C36 | SQS Data Import Ingestion | Queue | Upload/connector → File Import Batch |

### 2.5 Model Interfaces (LLM Processing)

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C40 | LangChain Request Handler | Lambda | Bedrock/SageMaker/OpenAI/Nexus via LangChain |
| C41 | Bedrock Agents Request Handler | Lambda | Bedrock Agent runtime |
| C42 | Idefics Request Handler | Lambda | Multi-modal (image) models |
| C43 | WebSearch Handler | Lambda | External web search for hybrid mode |

### 2.6 LLM Providers (External)

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C50 | Amazon Bedrock | Service | Claude, Titan, Cohere |
| C51 | Amazon SageMaker | Service | Custom endpoints (FalconLite, Mistral, etc.) |
| C52 | Nexus Gateway | Service | Unified model proxy |
| C53 | OpenAI API | Service | GPT, text-embedding-ada-002 |
| C54 | Azure OpenAI | Service | Azure-hosted models |

### 2.7 RAG & Data Import

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C60 | Aurora PostgreSQL (pgvector) | Database | Vector store for RAG |
| C61 | OpenSearch | Service | Vector index (optional) |
| C62 | Amazon Kendra | Service | Managed search (optional) |
| C63 | Bedrock Knowledge Base | Service | Managed KB (optional) |
| C64 | File Import Step Function | Workflow | S3 → Batch → chunk → vectorize |
| C65 | Website Crawling Step Function | Workflow | RSS/URL → Web Crawler Batch |
| C66 | Connector File Import Step Function | Workflow | Dropbox/SharePoint → File Import Batch |
| C67 | File Import Batch Job | ECS | Fargate container, processes files |
| C68 | Web Crawler Batch Job | ECS | Fargate container, crawls websites |
| C69 | RSS Ingestor Lambda | Lambda | Polls RSS, queues posts for crawl |
| C70 | Trigger RSS Ingestors Lambda | Lambda | EventBridge 15min → invokes ingestors |
| C71 | Batch Crawl RSS Posts Lambda | Lambda | EventBridge 5min → crawl queued posts |
| C72 | Upload Handler Lambda | Lambda | S3 event → starts File Import workflow |
| C73 | Delete Workspace Step Function | Workflow | Removes workspace and vectors |
| C74 | Delete Document Step Function | Workflow | Removes document and vectors |

### 2.8 Connectors

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C80 | Connector Gateway (ECS + ALB) | Infrastructure | Internal ALB, path-based routing |
| C81 | Dropbox MCP Service | ECS Task | Python MCP server, /dropbox path |
| C82 | SharePoint MCP Service | ECS Task | MCP server, /sharepoint path |
| C83 | Connectors DynamoDB Table | Database | Connector registry |

### 2.9 Databases & Storage

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C90 | DynamoDB Sessions | Database | Chat sessions, byUserId GSI |
| C91 | DynamoDB Applications | Database | Application configs |
| C92 | DynamoDB Workspaces | Database | RAG workspaces |
| C93 | DynamoDB Documents | Database | Document metadata, status |
| C94 | S3 Upload Bucket | Storage | User uploads for RAG |
| C95 | S3 Processing Bucket | Storage | Intermediate processing |
| C96 | S3 Chatbot Files Bucket | Storage | User-uploaded chat files |
| C97 | S3 User Feedback Bucket | Storage | Feedback storage |
| C98 | SSM Parameter Store | Config | Config, models parameter |

### 2.10 Shared Infrastructure

| ID | Component | Type | Description |
|----|-----------|------|-------------|
| C99 | VPC | Network | Shared VPC or existing |
| C100 | KMS | Crypto | CMK for encryption |
| C101 | genai_core Lambda Layer | Layer | Python SDK (RAG, connectors, models) |
| C102 | EventBridge Scheduler | Scheduler | SageMaker start/stop (cron) |
| C103 | Monitoring | Alarms | CloudWatch, X-Ray, composite alarms |

---

## 3. Relationship Matrix

### 3.1 User → API

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| C01 React SPA | C10 Cognito | OAuth/OIDC | Sign-in |
| C01 React SPA | C20 AppSync GraphQL | HTTPS/WebSocket | Queries, mutations |
| C01 React SPA | C21 AppSync Realtime | WSS | Real-time chat |
| C02 CloudFront | C20 AppSync | HTTPS | GraphQL proxy |
| C02 CloudFront | C21 AppSync | WSS | WebSocket proxy |

### 3.2 API → Message Bus

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| C23 SendQuery Resolver | C30 SNS Messages Topic | SNS Publish | Publish chat message |
| C30 SNS Messages Topic | C32 SQS LangChain | SNS→SQS | Route to LangChain |
| C30 SNS Messages Topic | C33 SQS Bedrock Agents | SNS→SQS | Route to Bedrock Agents |
| C30 SNS Messages Topic | C34 SQS Idefics | SNS→SQS | Route to Idefics |
| C30 SNS Messages Topic | C35 SQS WebSearch | SNS→SQS | Route to WebSearch |
| C40 LangChain Handler | C30 SNS Messages Topic | SNS Publish (Direction.Out) | Push response |
| C41 Bedrock Agents Handler | C30 SNS Messages Topic | SNS Publish (Direction.Out) | Push response |
| C42 Idefics Handler | C30 SNS Messages Topic | SNS Publish (Direction.Out) | Push response |
| C43 WebSearch Handler | C30 SNS Messages Topic | SNS Publish (Direction.Out) | Push response |
| C30 SNS Messages Topic | C31 SQS Outgoing | SNS→SQS (filter: Direction.Out) | Route responses |
| C31 SQS Outgoing | C24 Outgoing Message Handler | SQS Poll | Consume responses |
| C24 Outgoing Message Handler | C21 AppSync Realtime | AppSync publishResponse | Deliver to WebSocket |

### 3.3 Model Interfaces → LLM Providers

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| C40 LangChain Handler | C50 Bedrock | Bedrock API | LLM, embeddings |
| C40 LangChain Handler | C51 SageMaker | SageMaker Runtime | LLM |
| C40 LangChain Handler | C52 Nexus | HTTPS | Model proxy |
| C40 LangChain Handler | C53 OpenAI | HTTPS | GPT, embeddings |
| C40 LangChain Handler | C54 Azure OpenAI | HTTPS | Azure models |
| C41 Bedrock Agents Handler | C50 Bedrock | Bedrock Agent API | Agent invoke |
| C43 WebSearch Handler | External search | HTTP GET | Web search |

### 3.4 API Handler → RAG / Connectors

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| C22 API Handler | C60 Aurora | PostgreSQL | Workspace CRUD, queries |
| C22 API Handler | C61 OpenSearch | OpenSearch API | Vector search |
| C22 API Handler | C62 Kendra | Kendra API | Search |
| C22 API Handler | C64 File Import SF | Step Functions | Start file import |
| C22 API Handler | C66 Connector File Import SF | Step Functions | Start connector import |
| C22 API Handler | C80 Connector Gateway | HTTP (VPC) | list_folder, fetch file |
| C22 API Handler | C83 Connectors Table | DynamoDB | Connector CRUD |
| C22 API Handler | C94 S3 Upload | S3 Presign | Upload URL |

### 3.5 RAG Data Flow

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| C94 S3 Upload | C72 Upload Handler | S3 Event | Trigger file import |
| C72 Upload Handler | C64 File Import SF | Step Functions | Start workflow |
| C64 File Import SF | C67 File Import Batch | Batch | Process files |
| C67 File Import Batch | C36 SQS Ingestion | (internal) | Chunk ingestion |
| C69 RSS Ingestor | C65 Website Crawling SF | Step Functions | Crawl RSS posts |
| C71 Batch Crawl RSS | C65 Website Crawling SF | Step Functions | Crawl queued |
| C65 Website Crawling SF | C68 Web Crawler Batch | Batch | Crawl sites |
| C102 EventBridge Scheduler | C70 Trigger RSS | Lambda invoke | Every 15 min |
| Events (15min) | C70 Trigger RSS | EventBridge | Schedule |
| Events (5min) | C71 Batch Crawl RSS | EventBridge | Schedule |
| C102 EventBridge Scheduler | C51 SageMaker | Scheduler API | Start/stop endpoints |

### 3.6 Connector Flow

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| C22 API Handler | C80 Connector Gateway | HTTP | MCP requests |
| C80 Connector Gateway | C81 Dropbox MCP | ALB path /dropbox | Dropbox operations |
| C80 Connector Gateway | C82 SharePoint MCP | ALB path /sharepoint | SharePoint operations |
| C81/C82 MCP | Dropbox/SharePoint API | HTTPS | External API |
| C40 LangChain Handler | C83 Connectors Table | DynamoDB | Read connector config |
| C40 LangChain Handler | C80 Connector Gateway | HTTP | Fetch connector context |

### 3.7 Auth Integration

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| C20 AppSync | C10 Cognito | USER_POOL | Validate JWT |
| C21 AppSync Realtime | C10 Cognito | USER_POOL | Validate JWT |
| C10 Cognito | C12 AddFederatedUser | Lambda trigger | PreSignUp, PostConfirmation |

---

## 4. Validation Checklist

- [x] All CDK constructs from stack are represented
- [x] SNS/SQS flow matches aws-genai-llm-chatbot-stack.ts subscriptions
- [x] RAG engines (Aurora, OpenSearch, Kendra) from config
- [x] Data import workflows (File, Website, Connector) from data-import/
- [x] EventBridge schedules (RSS 15min, 5min; SageMaker) from inventory
- [x] Connector Gateway + MCP services from connector-gateway/
- [x] DynamoDB tables (Sessions, Applications, Workspaces, Documents, Connectors)
- [x] S3 buckets (Upload, Processing, Chatbot Files, User Feedback)
- [x] Model interfaces (LangChain, Bedrock Agents, Idefics, WebSearch)
- [x] External LLM providers from genai_core/clients.py
- [x] Auth (Cognito, federation, triggers)
- [x] User flow: SPA → AppSync → SendQuery → SNS → Model → SQS → WebSocket

---

## 5. Diagram Layout Hints (for draw.io)

- **Tier 1 (top):** User, React SPA, CloudFront
- **Tier 2:** Cognito, AppSync GraphQL, AppSync Realtime
- **Tier 3:** Lambdas (API Handler, SendQuery, Outgoing, Model Interfaces)
- **Tier 4:** SNS, SQS queues
- **Tier 5:** Model interfaces (LangChain, Bedrock Agents, Idefics, WebSearch)
- **Tier 6:** External (Bedrock, SageMaker, Nexus, OpenAI)
- **Tier 7:** RAG (Aurora, OpenSearch, Kendra, Step Functions, Batch)
- **Tier 8:** Connectors (Gateway, MCP services)
- **Tier 9 (bottom):** DynamoDB, S3, SSM, VPC, KMS

---

## 6. Draw.io Diagram

**File:** `architecture-diagram.drawio`

The diagram is generated from the validated component list and relationship matrix. Open in draw.io (diagrams.net) or VS Code with Draw.io extension.

**Key flows shown:**
- User → React SPA → CloudFront → AppSync (GraphQL + Realtime)
- SendQuery → SNS Messages Topic → SQS (per model interface) → Model Handlers
- Model Handlers → SNS (Direction.Out) → SQS Outgoing → Outgoing Handler → AppSync Realtime → User
- API Handler → RAG (Aurora, Step Functions), Connectors, DynamoDB
- Upload → Upload Handler → File Import SF → File Import Batch
- Connector Gateway → Dropbox/SharePoint MCP

---

*End of Architecture Summary*
