# High-Level Architecture Summary

**Source:** Phase 1 System Inventory, ARCHITECTURE_SUMMARY.md, validated against repository.

---

## 1. System Purpose

Enterprise-ready generative AI chatbot with Retrieval Augmented Generation (RAG) capabilities. Enables organizations to deploy a secure, feature-rich chatbot powered by multiple LLMs (Bedrock, SageMaker, Nexus, OpenAI) with vector search, conversation memory, enterprise security, and a modern React interface. Supports optional data connectors (Dropbox, SharePoint) for RAG data ingestion.

**Evidence:** `package.json` (description), `README.md`, `lib/aws-genai-llm-chatbot-stack.ts`, `lib/shared/types.ts` (SystemConfig, ModelProvider, RAG engines).

---

## 2. Main Actors / Users

| Actor | Role | Evidence |
|-------|------|----------|
| **End User** | Chats with AI, views sessions, uses embedded application chat | `lib/user-interface/react-app/src/app.tsx` (ApplicationChat, Playground), `lib/user-interface/react-app/src/pages/application/` |
| **Admin** | Manages applications, connectors, models; full RAG configuration | `lib/authentication/index.ts` (AdminGroup), `lib/user-interface/react-app/src/app.tsx` (UserRole.ADMIN), Applications, ManageApplication, Connectors pages |
| **Workspace Manager** | Manages RAG workspaces, embeddings, documents; create/delete workspaces | `lib/authentication/index.ts` (workspace_manager group), `lib/user-interface/react-app/src/pages/rag/` |
| **Regular User** | Chat, limited workspace access | `lib/authentication/index.ts` (UserGroup) |
| **Scheduled Process** | EventBridge-triggered RSS poll (15 min), batch crawl (5 min), SageMaker start/stop | `lib/rag-engines/data-import/rss-subscription.ts`, `lib/models/sagemaker-schedule.ts` |
| **External System (optional)** | Application embedding via /application/:applicationId | `lib/user-interface/react-app/src/pages/application/application.tsx` |

---

## 3. External Systems / Third-Party Services

| External System | Purpose | Evidence |
|-----------------|---------|----------|
| **Amazon Bedrock** | LLM inference, embeddings, agents | `lib/shared/layers/python-sdk/python/genai_core/clients.py`, `bedrock_agent/client.py`, `config.json` |
| **Amazon SageMaker** | Custom model endpoints (FalconLite, Mistral, Idefics, etc.) | `lib/models/index.ts`, `lib/sagemaker-model/`, `lib/shared/types.ts` |
| **Nexus Gateway** | Unified model proxy (when enabled) | `lib/shared/types.ts` (nexus config), `lib/shared/layers/python-sdk/python/genai_core/model_providers/nexus/` |
| **OpenAI API** | GPT, text-embedding-ada-002 | `lib/shared/layers/python-sdk/python/genai_core/clients.py`, `embeddings.py` |
| **Azure OpenAI** | Azure-hosted models | `lib/shared/layers/python-sdk/python/genai_core/model_providers/direct/models.py` |
| **Cohere** | Embeddings (cohere.embed-*) | `genai_core/model_providers/direct/embeddings.py`, `provider.py` |
| **Dropbox API** | Connector file listing, fetch | `lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py` |
| **SharePoint API** | Connector (when enabled) | `lib/connectors/connector-gateway/index.ts`, `config.json` |
| **AWS Secrets Manager** | Connector OAuth, API keys | `lib/chatbot-api/functions/api-handler/routes/connectors.py` |
| **OIDC/SAML IdP** | Federated auth (optional) | `lib/authentication/index.ts` (customOIDC, customSAML) |
| **Web Search (external)** | HTTP GET for hybrid mode | `lib/model-interfaces/websearch/functions/websearch-handler/index.py` |
| **Amazon Comprehend** | Language detection | `lib/shared/layers/python-sdk/python/genai_core/utils/comprehend.py` |

---

## 4. Deployable / Runtime Components

| Component | Type | Evidence |
|-----------|------|----------|
| **React SPA** | Frontend (Vite + React) | `lib/user-interface/react-app/`, `vite.config.ts` |
| **CloudFront** | CDN / Reverse Proxy | `lib/user-interface/public-website.ts` |
| **Private ALB** | Load Balancer (optional) | `lib/user-interface/private-website.ts` |
| **AppSync GraphQL API** | Backend API | `lib/chatbot-api/index.ts`, `schema/schema.graphql` |
| **AppSync Realtime** | WebSocket API | `lib/chatbot-api/websocket-api.ts`, `appsync-ws.ts` |
| **API Handler Lambda** | GraphQL resolvers | `lib/chatbot-api/rest-api.ts`, `functions/api-handler/index.py` |
| **SendQuery Lambda** | Chat ingestion | `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py` |
| **Outgoing Message Handler Lambda** | WebSocket delivery | `lib/chatbot-api/appsync-ws.ts`, `functions/outgoing-message-appsync/` |
| **LangChain Request Handler Lambda** | LLM processing | `lib/model-interfaces/langchain/` |
| **Bedrock Agents Request Handler Lambda** | Agent processing | `lib/model-interfaces/bedrock-agents/` |
| **Idefics Request Handler Lambda** | Multi-modal | `lib/model-interfaces/idefics/` |
| **WebSearch Handler Lambda** | Web search | `lib/model-interfaces/websearch/` |
| **Upload Handler Lambda** | S3 → File Import | `lib/rag-engines/data-import/` |
| **RSS Ingestor Lambda** | RSS poll | `lib/rag-engines/data-import/rss-subscription.ts` |
| **Trigger RSS / Batch Crawl Lambdas** | Scheduled | `lib/rag-engines/data-import/rss-subscription.ts` |
| **Connector Gateway (ECS Fargate + ALB)** | MCP gateway | `lib/connectors/connector-gateway/index.ts` |
| **Dropbox MCP Service** | ECS Task | `lib/connectors/dropbox-mcp-server/` |
| **SharePoint MCP Service** | ECS Task | `lib/connectors/connector-gateway/index.ts` |
| **File Import Batch Job** | AWS Batch (Fargate) | `lib/rag-engines/data-import/file-import-batch-job.ts` |
| **Web Crawler Batch Job** | AWS Batch (Fargate) | `lib/rag-engines/data-import/web-crawler-batch-job.ts` |
| **Step Functions** | File Import, Website Crawl, Connector Import, Delete Workspace/Document | `lib/rag-engines/data-import/*.ts`, `lib/rag-engines/workspaces/` |
| **EventBridge Scheduler** | SageMaker start/stop | `lib/models/sagemaker-schedule.ts` |
| **EventBridge Rules** | RSS 15min, 5min | `lib/rag-engines/data-import/rss-subscription.ts` |
| **WAF** | Rate limiting (AppSync) | `lib/chatbot-api/index.ts` |
| **AddFederatedUserToUserGroup Lambda** | Cognito trigger | `lib/authentication/index.ts` |

---

## 5. Main Data Stores

| Data Store | Type | Purpose | Evidence |
|------------|------|---------|----------|
| **DynamoDB Sessions** | NoSQL | Chat sessions, byUserId GSI | `lib/chatbot-api/chatbot-dynamodb-tables/`, `genai_core/sessions.py` |
| **DynamoDB Applications** | NoSQL | Application configs, embeddings | `lib/chatbot-api/application-dynamodb-tables/`, `genai_core/applications.py` |
| **DynamoDB Workspaces** | NoSQL | RAG workspaces | `lib/rag-engines/rag-dynamodb-tables/`, `genai_core/workspaces.py` |
| **DynamoDB Documents** | NoSQL | Document metadata, status | `lib/rag-engines/rag-dynamodb-tables/`, `genai_core/documents.py` |
| **DynamoDB Connectors** | NoSQL | Connector registry | `lib/connectors/connector-dynamodb-tables/`, `genai_core/connectors/registry.py` |
| **Aurora PostgreSQL (pgvector)** | Relational + Vector | RAG vector store | `lib/rag-engines/aurora-pgvector/`, `genai_core/aurora/` |
| **OpenSearch** | Search | Vector index (optional) | `lib/rag-engines/opensearch-vector/`, `genai_core/opensearch/` |
| **Amazon Kendra** | Search | Managed search (optional) | `lib/rag-engines/kendra-retrieval/`, `genai_core/kendra/` |
| **S3 Upload Bucket** | Object Storage | User uploads for RAG | `lib/rag-engines/data-import/index.ts` |
| **S3 Processing Bucket** | Object Storage | Intermediate chunks | `lib/rag-engines/data-import/` |
| **S3 Chatbot Files Bucket** | Object Storage | User chat files | `lib/chatbot-api/chatbot-s3-buckets/` |
| **S3 User Feedback Bucket** | Object Storage | Feedback | `lib/chatbot-api/chatbot-s3-buckets/` |
| **SSM Parameter Store** | Config | Config, models list | `lib/shared/index.ts` |

---

## 6. Main Synchronous Flows

| Flow | Path | Evidence |
|------|------|----------|
| **User Sign-In** | User → React SPA → Cognito → JWT | `lib/authentication/index.ts`, Amplify auth in React app |
| **GraphQL Query/Mutation** | User → CloudFront → AppSync → API Handler Lambda → DynamoDB/Aurora/OpenSearch/Kendra/S3/Step Functions | `lib/chatbot-api/index.ts`, `rest-api.ts`, `functions/api-handler/` |
| **Workspace CRUD** | API Handler → DynamoDB Workspaces, CreateWorkspace SF | `lib/chatbot-api/functions/api-handler/routes/workspaces.py`, `genai_core/workspaces.py` |
| **Connector list_folder / fetch** | API Handler → Connector Gateway (ALB) → Dropbox/SharePoint MCP → External API | `lib/chatbot-api/functions/api-handler/routes/connectors.py`, `genai_core/connectors/connector_files.py` |
| **Presigned Upload** | API Handler → S3 presign URL | `genai_core/presign.py`, API handler env CHATBOT_FILES_BUCKET |
| **RAG Semantic Search** | API Handler → Aurora/OpenSearch/Kendra | `genai_core/workspace_retriever.py`, `genai_core/opensearch/`, `genai_core/kendra/` |
| **SendQuery (request)** | User → AppSync Realtime → SendQuery Lambda → SNS Publish | `lib/chatbot-api/functions/resolvers/send-query-lambda-resolver/index.py` |
| **Model Invocation (sync part)** | LangChain/Bedrock Agents Handler → Bedrock/SageMaker/OpenAI/Nexus | `genai_core/clients.py`, model adapters |

---

## 7. Main Asynchronous Flows

| Flow | Path | Evidence |
|------|------|----------|
| **Chat Response Delivery** | SendQuery → SNS → SQS (per interface) → Model Handler → SNS (Direction.Out) → SQS Outgoing → Outgoing Handler → AppSync publishResponse → WebSocket | `lib/chatbot-api/websocket-api.ts`, `appsync-ws.ts`, `lib/aws-genai-llm-chatbot-stack.ts` |
| **File Import** | S3 Upload event → Upload Handler Lambda → File Import Step Function → File Import Batch (Fargate) → Aurora/OpenSearch | `lib/rag-engines/data-import/file-import-workflow.ts`, `file-import-batch-job.ts` |
| **Website Crawling** | EventBridge (5 min) → Batch Crawl Lambda → Website Crawling SF → Web Crawler Batch (Fargate) | `lib/rag-engines/data-import/rss-subscription.ts`, `website-crawling-workflow.ts` |
| **RSS Poll** | EventBridge (15 min) → Trigger RSS Lambda → RSS Ingestor (per workspace) → Website Crawling SF | `lib/rag-engines/data-import/rss-subscription.ts` |
| **Connector File Import** | API Handler → Connector File Import SF → File Import Batch | `lib/rag-engines/data-import/connector-file-import-workflow.ts` |
| **Delete Workspace / Document** | API Handler → Delete Workspace/Document Step Function → Aurora/OpenSearch/Kendra/DynamoDB cleanup | `lib/rag-engines/workspaces/delete-workspace.ts`, `delete-document.ts` |
| **SageMaker Start/Stop** | EventBridge Scheduler (cron) → SageMaker createEndpoint/deleteEndpoint | `lib/models/sagemaker-schedule.ts` |
| **Federated User Group Assignment** | Cognito PreSignUp/PostConfirmation → AddFederatedUserToUserGroup Lambda | `lib/authentication/index.ts` |

---

## 8. C4-Style Container Model

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ ACTORS (Left)                    │ AWS GenAI LLM Chatbot System (Center)            │
├──────────────────────────────────┼──────────────────────────────────────────────────┤
│ End User                         │  ┌─────────────────────────────────────────────┐ │
│ Admin                            │  │ Web UI (React SPA)                           │ │
│ Workspace Manager                │  │ - CloudFront / Private ALB                    │ │
│ Scheduled Process                │  └───────────────────┬─────────────────────────┘ │
│ External App (embed)             │                      │                           │
│                                  │  ┌───────────────────▼─────────────────────────┐ │
│                                  │  │ API (AppSync GraphQL + Realtime)              │ │
│                                  │  │ - API Handler Lambda                         │ │
│                                  │  │ - SendQuery / Outgoing Message Lambdas       │ │
│                                  │  └───────────────────┬─────────────────────────┘ │
│                                  │                      │                           │
│                                  │  ┌───────────────────▼─────────────────────────┐ │
│                                  │  │ Message Bus (SNS + SQS)                      │ │
│                                  │  │ - SNS Messages Topic                         │ │
│                                  │  │ - SQS (LangChain, Bedrock Agents, Idefics,   │ │
│                                  │  │   WebSearch, Outgoing)                       │ │
│                                  │  └───────────────────┬─────────────────────────┘ │
│                                  │                      │                           │
│                                  │  ┌───────────────────▼─────────────────────────┐ │
│                                  │  │ Model Processors (Lambdas)                    │ │
│                                  │  │ - LangChain, Bedrock Agents, Idefics,        │ │
│                                  │  │   WebSearch Handlers                         │ │
│                                  │  └───────────────────┬─────────────────────────┘ │
│                                  │                      │                           │
│                                  │  ┌───────────────────▼─────────────────────────┐ │
│                                  │  │ RAG & Data Import                             │ │
│                                  │  │ - Step Functions, Batch Jobs, Upload Handler │ │
│                                  │  │ - Connector Gateway (ECS + ALB)               │ │
│                                  │  └───────────────────┬─────────────────────────┘ │
└──────────────────────────────────┼──────────────────────┼───────────────────────────┘
                                   │                      │
┌──────────────────────────────────┼──────────────────────┼───────────────────────────┐
│ DATA STORES (Below)               │                      ▼                           │
├──────────────────────────────────┤  ┌───────────────────────────────────────────────┤
│ DynamoDB (Sessions, Apps,        │  │ DynamoDB │ Aurora │ OpenSearch │ Kendra │ S3   │
│ Workspaces, Documents, Connectors)│  │ SSM Parameter Store                           │
│ Aurora pgvector │ OpenSearch     │  └───────────────────────────────────────────────┘
│ Kendra │ S3 (Upload, Processing, │
│ Chatbot Files, Feedback)         │
│ SSM Parameter Store               │
└──────────────────────────────────┴────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL SYSTEMS (Right)                                                             │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Amazon Bedrock │ SageMaker │ Nexus Gateway │ OpenAI │ Azure OpenAI │ Cohere          │
│ Dropbox API │ SharePoint API │ OIDC/SAML IdP │ Web Search │ Secrets Manager          │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Evidence / File References

- `package.json` — System description, scripts
- `README.md` — Overview, architecture bullets
- `config.json` — RAG engines, connectors, bedrock, VPC
- `lib/aws-genai-llm-chatbot-stack.ts` — Main stack, all constructs wired
- `lib/shared/types.ts` — SystemConfig, ModelProvider, connectors, RAG
- `lib/authentication/index.ts` — Cognito, groups, federation, triggers
- `lib/chatbot-api/index.ts` — AppSync, resolvers, SNS, SQS
- `lib/chatbot-api/rest-api.ts` — API Handler Lambda, env vars
- `lib/chatbot-api/websocket-api.ts` — SNS Messages Topic, SQS Outgoing, subscriptions
- `lib/chatbot-api/appsync-ws.ts` — SendQuery, Outgoing Message Handler
- `lib/chatbot-api/schema/schema.graphql` — GraphQL schema
- `lib/model-interfaces/langchain/` — LangChain interface
- `lib/model-interfaces/bedrock-agents/` — Bedrock Agents interface
- `lib/model-interfaces/idefics/` — Idefics interface
- `lib/model-interfaces/websearch/` — WebSearch handler
- `lib/rag-engines/` — Aurora, OpenSearch, Kendra, data-import, workspaces
- `lib/rag-engines/data-import/rss-subscription.ts` — EventBridge 15min, 5min
- `lib/connectors/connector-gateway/index.ts` — ECS, ALB, Dropbox/SharePoint MCP
- `lib/connectors/connector-dynamodb-tables/` — Connectors table
- `lib/connectors/dropbox-mcp-server/` — Dropbox MCP
- `lib/user-interface/react-app/src/app.tsx` — Routes, roles (ADMIN, WORKSPACE_MANAGER)
- `lib/shared/layers/python-sdk/python/genai_core/clients.py` — Bedrock, OpenAI, Nexus
- `lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py` — Dropbox/SharePoint HTTP
- `lib/models/sagemaker-schedule.ts` — SageMaker EventBridge Scheduler
- `ARCHITECTURE_SUMMARY.md` — Validated component list, relationship matrix

---

## 10. Needs Verification

| Item | Location | Question |
|------|----------|----------|
| Nexus Gateway as exclusive provider | `lib/shared/types.ts`, nexus config | When Nexus is enabled, whether it fully replaces Bedrock/SageMaker/OpenAI or co-exists |
| Web Search external URL | `lib/model-interfaces/websearch/functions/websearch-handler/index.py` | Exact external search service(s) used; config source |
| Private website auth | `lib/user-interface/private-website.ts` | Whether ALB performs Cognito auth or relies on VPC-only access |
| REST vs GraphQL | `lib/chatbot-api/rest-api.ts` | File name suggests REST, but content is AppSync/GraphQL resolver wiring |
| Azure SQL connector | Deleted per git status | Whether replacement or re-enablement is planned |
| VitePress deploy target | `.github/workflows/deploy.yml` | Whether VitePress deploys docs only or also the main chatbot app |

---

## draw.io XML

Import the XML below into draw.io (diagrams.net): File → Import from → Device, then paste or select the file. A standalone file is also at `high-level-architecture.drawio`.

```xml
<mxfile host="app.diagrams.net" modified="2025-03-10T00:00:00.000Z" agent="Cursor" version="22.1.0" etag="hla" type="device">
  <diagram id="High Level Architecture" name="High Level Architecture">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1400" pageHeight="1000" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="title" value="AWS GenAI LLM Chatbot - High Level Architecture" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=16;fontStyle=1" vertex="1" parent="1">
          <mxGeometry x="450" y="20" width="500" height="30" as="geometry"/>
        </mxCell>
        <mxCell id="actorLabel" value="Actors" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=12;fontStyle=1" vertex="1" parent="1">
          <mxGeometry x="40" y="70" width="80" height="20" as="geometry"/>
        </mxCell>
        <mxCell id="actor1" value="End User" style="shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;" vertex="1" parent="1">
          <mxGeometry x="70" y="100" width="40" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="actor2" value="Admin" style="shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;" vertex="1" parent="1">
          <mxGeometry x="70" y="200" width="40" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="actor3" value="Workspace Manager" style="shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;" vertex="1" parent="1">
          <mxGeometry x="70" y="300" width="40" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="actor4" value="Scheduled Process" style="shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;" vertex="1" parent="1">
          <mxGeometry x="70" y="420" width="40" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="systemBoundary" value="AWS GenAI LLM Chatbot System" style="swimlane;horizontal=1;startSize=30;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1" vertex="1" parent="1">
          <mxGeometry x="200" y="80" width="800" height="520" as="geometry"/>
        </mxCell>
        <mxCell id="webui" value="Web UI (React SPA) CloudFront / ALB" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;" vertex="1" parent="systemBoundary">
          <mxGeometry x="40" y="50" width="180" height="70" as="geometry"/>
        </mxCell>
        <mxCell id="api" value="API Layer - AppSync GraphQL + Realtime - API Handler, SendQuery, Outgoing" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="systemBoundary">
          <mxGeometry x="40" y="140" width="180" height="80" as="geometry"/>
        </mxCell>
        <mxCell id="msgbus" value="Message Bus - SNS Messages Topic - SQS (LangChain, Agents, Idefics, WebSearch, Outgoing)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;" vertex="1" parent="systemBoundary">
          <mxGeometry x="40" y="240" width="180" height="90" as="geometry"/>
        </mxCell>
        <mxCell id="modelproc" value="Model Processors - LangChain, Bedrock Agents, Idefics, WebSearch Handlers" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;" vertex="1" parent="systemBoundary">
          <mxGeometry x="40" y="350" width="180" height="70" as="geometry"/>
        </mxCell>
        <mxCell id="rag" value="RAG and Data Import - Step Functions, Batch Jobs, Upload Handler, Connector Gateway" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;" vertex="1" parent="systemBoundary">
          <mxGeometry x="40" y="440" width="180" height="70" as="geometry"/>
        </mxCell>
        <mxCell id="datastoreLabel" value="Data Stores" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=12;fontStyle=1" vertex="1" parent="1">
          <mxGeometry x="40" y="620" width="100" height="20" as="geometry"/>
        </mxCell>
        <mxCell id="ds1" value="DynamoDB (Sessions, Apps, Workspaces, Documents, Connectors)" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=12;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="200" y="640" width="140" height="80" as="geometry"/>
        </mxCell>
        <mxCell id="ds2" value="Aurora pgvector" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=12;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="360" y="640" width="100" height="80" as="geometry"/>
        </mxCell>
        <mxCell id="ds3" value="OpenSearch Kendra" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=12;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="480" y="640" width="100" height="80" as="geometry"/>
        </mxCell>
        <mxCell id="ds4" value="S3 (Upload, Processing, Chatbot Files)" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=12;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="600" y="640" width="120" height="80" as="geometry"/>
        </mxCell>
        <mxCell id="ds5" value="SSM Parameter" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=10;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="740" y="660" width="80" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="extLabel" value="External Systems" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=12;fontStyle=1" vertex="1" parent="1">
          <mxGeometry x="1050" y="70" width="120" height="20" as="geometry"/>
        </mxCell>
        <mxCell id="ext1" value="Amazon Bedrock" style="shape=cloud;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;" vertex="1" parent="1">
          <mxGeometry x="1040" y="100" width="130" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="ext2" value="SageMaker" style="shape=cloud;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;" vertex="1" parent="1">
          <mxGeometry x="1040" y="180" width="130" height="50" as="geometry"/>
        </mxCell>
        <mxCell id="ext3" value="Nexus Gateway OpenAI Azure OpenAI" style="shape=cloud;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;" vertex="1" parent="1">
          <mxGeometry x="1040" y="250" width="130" height="70" as="geometry"/>
        </mxCell>
        <mxCell id="ext4" value="Cognito OIDC SAML" style="shape=cloud;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;" vertex="1" parent="1">
          <mxGeometry x="1040" y="340" width="130" height="50" as="geometry"/>
        </mxCell>
        <mxCell id="ext5" value="Dropbox SharePoint Secrets Manager" style="shape=cloud;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;" vertex="1" parent="1">
          <mxGeometry x="1040" y="410" width="130" height="70" as="geometry"/>
        </mxCell>
        <mxCell id="e1" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="actor1" target="webui">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e2" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="actor2" target="webui">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e3" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="actor3" target="webui">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e4" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="actor4" target="rag">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e5" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="webui" target="api">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e6" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="api" target="msgbus">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e7" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="msgbus" target="modelproc">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e8" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="modelproc" target="rag">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e9" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="api" target="ds1">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e10" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="api" target="ds2">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e11" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="rag" target="ds1">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e12" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="rag" target="ds2">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e13" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;" edge="1" parent="1" source="rag" target="ds4">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e14" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;dashed=1;" edge="1" parent="1" source="api" target="ext4">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e15" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="modelproc" target="ext1">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e16" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="modelproc" target="ext2">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e17" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="modelproc" target="ext3">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="e18" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="rag" target="ext5">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="flowlabel" value="Sync: HTTPS/WSS | Async: SNS/SQS, Step Functions, Batch" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=10;" vertex="1" parent="1">
          <mxGeometry x="300" y="740" width="400" height="20" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```
