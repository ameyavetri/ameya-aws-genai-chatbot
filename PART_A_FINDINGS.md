# Part A: Current-State Findings - Data Source Connectors via MCP

## Executive Summary

After comprehensive codebase inspection, **no existing connector/tool abstraction exists**. However, the codebase has strong reusable building blocks and extension points that align perfectly with an MCP-based connector architecture.

---

## 1. Existing Integration Foundations

### 1.1 Search Results Summary

**Files containing relevant terms:**
- `connector/integration/datasource/tool/plugin/adapter/provider`: 242 files
- `ingestion/crawler/import/loader`: 463 files

**Key Finding:** No dedicated "connector" or "MCP" abstraction exists. The codebase uses:
- **Adapter pattern** for model interfaces (`lib/model-interfaces/langchain/functions/request-handler/adapters/`)
- **Registry pattern** for model adapters (`lib/shared/layers/python-sdk/python/genai_core/registry/index.py`)
- **Plugin-style RAG engines** (aurora, opensearch, kendra, bedrock_kb)

---

## 2. Detailed Architecture Inspection

### 2.1 API Handler & Routes (`lib/chatbot-api/functions/api-handler/`)

**File:** `index.py`
- **Pattern:** Router-based modular architecture using `aws_lambda_powertools.event_handler.appsync.Router`
- **Routes:** 14 route modules registered:
  - `health`, `embeddings`, `cross_encoders`, `rag`, `models`, `agents`, `workspaces`, `sessions`, `semantic_search`, `documents`, `kendra`, `user_feedback`, `bedrock_kb`, `roles`, `applications`
- **Extension Point:** ✅ **Add `routes/connectors.py`** - follows exact same pattern

**Key Route Examples:**
- `routes/semantic_search.py`: Calls `genai_core.semantic_search.semantic_search()` → routes to engine-specific query functions
- `routes/documents.py`: Document CRUD + ingestion triggers (file upload, website, RSS)
- `routes/rag.py`: Lists available RAG engines from config

**Evidence:**
```python
# lib/chatbot-api/functions/api-handler/index.py:32-46
app.include_router(health_router)
app.include_router(rag_router)
app.include_router(embeddings_router)
# ... pattern continues
```

---

### 2.2 Shared Python SDK (`lib/shared/layers/python-sdk/python/genai_core/`)

**Structure:**
```
genai_core/
├── semantic_search.py      # Routes to engine-specific queries
├── documents.py            # Document CRUD + ingestion orchestration
├── workspaces.py           # Workspace management
├── embeddings.py           # Embedding generation
├── auth.py                 # RBAC & permissions
├── roles.py                # Role management
├── registry/               # Adapter registry pattern
│   └── index.py           # Regex-based adapter lookup
├── aurora/                 # Aurora RAG engine
├── opensearch/             # OpenSearch RAG engine
├── kendra/                 # Kendra RAG engine
├── bedrock_kb/            # Bedrock KB RAG engine
└── langchain/             # LangChain integrations
    ├── workspace_retriever.py
    └── chat_message_history.py
```

**Key Functions:**
- `semantic_search.py:semantic_search()` - Routes to engine-specific query functions based on workspace config
- `documents.py:create_document()` - Orchestrates document ingestion, triggers workflows
- `registry/index.py:AdapterRegistry` - Regex-based adapter pattern (reusable for connector registry)

**Extension Point:** ✅ **Create `genai_core/connectors/`** - mirrors RAG engine pattern

**Evidence:**
```python
# lib/shared/layers/python-sdk/python/genai_core/semantic_search.py:10-40
def semantic_search(workspace_id: str, query: str, limit: int = 5, full_response: bool = False):
    workspace = genai_core.workspaces.get_workspace(workspace_id)
    if workspace["engine"] == "aurora":
        return query_workspace_aurora(...)
    elif workspace["engine"] == "opensearch":
        return query_workspace_open_search(...)
    # ... engine routing pattern
```

---

### 2.3 RAG Engines (`lib/rag-engines/`)

**Structure:**
```
rag-engines/
├── aurora-pgvector/        # Aurora PostgreSQL vector store
├── opensearch-vector/      # OpenSearch vector store
├── kendra-retrieval/       # Amazon Kendra
├── data-import/            # Ingestion pipelines
│   ├── file-import-batch-job.ts
│   ├── web-crawler-batch-job.ts
│   └── rss-subscription.ts
└── workspaces/             # Workspace lifecycle
```

**Pattern:** Each engine is a CDK construct with:
- `index.ts` - CDK construct definition
- `functions/` - Lambda handlers for workflows
- Engine-specific query functions in `genai_core/{engine}/query.py`

**Extension Point:** ✅ **Connectors follow similar pattern** - but as MCP servers, not RAG engines

---

### 2.4 Model Interfaces (`lib/model-interfaces/`)

**Structure:**
```
model-interfaces/
├── langchain/
│   └── functions/request-handler/
│       ├── index.py                    # Main request handler (SQS batch processor)
│       ├── adapters/                   # Model adapters (bedrock, openai, sagemaker, etc.)
│       └── utils/
│           └── intent_detector.py     # ✅ Intent detection exists!
├── websearch/                          # ✅ Web search integration exists!
│   ├── index.ts                       # CDK construct
│   └── functions/websearch-handler/
│       └── index.py                   # Lambda handler (Bing API)
└── bedrock-agents/                    # Bedrock Agents integration
```

**Key Finding - Request Handler Flow:**
```python
# lib/model-interfaces/langchain/functions/request-handler/index.py:169-302
def handle_run(record):
    # 1. Extract user prompt, workspace_id, source_mode
    # 2. Intent detection (IntentDetector.analyze_query)
    # 3. Context resolution (resolve_context_for_prompt) - ✅ HOOK POINT
    # 4. Model adapter selection (registry.get_adapter)
    # 5. LLM invocation with augmented prompt
```

**Evidence:**
```python
# lib/model-interfaces/langchain/functions/request-handler/index.py:59-94
def resolve_context_for_prompt(prompt: str, source_mode: str, workspace_id: str, user_id: str) -> str:
    """
    Phase-2: Minimal stub wiring.
    - INTERNAL: pull RAG context (hook later)
    - WEB: pull web context (hook later)
    - HYBRID: both
    """
    # TODO (next step): call your existing RAG retriever using workspace_id.
    # TODO (next step): implement web search provider and fill web_items.
```

**Extension Point:** ✅ **Hook connector context retrieval here** - in `resolve_context_for_prompt()` function

---

### 2.5 Web Search Integration (Reference Implementation)

**Files:**
- `lib/model-interfaces/websearch/index.ts` - CDK construct (Lambda + SQS queue)
- `lib/model-interfaces/websearch/functions/websearch-handler/index.py` - Lambda handler

**Pattern:**
1. Lambda receives query via SQS
2. Retrieves API key from Secrets Manager
3. Calls external API (Bing Search)
4. Returns formatted results

**Evidence:**
```python
# lib/model-interfaces/websearch/functions/websearch-handler/index.py:22-96
def handler(event, context):
    query = event.get("query")
    api_key = get_bing_api_key()  # From Secrets Manager
    response = requests.get("https://api.bing.microsoft.com/v7.0/search", ...)
    return {"type": "text", "data": {"content": ..., "sources": results}}
```

**Relevance:** ✅ **MCP connectors can follow similar pattern** - but as long-lived services (ECS) or Lambda per connector type

---

### 2.6 Intent Detection (Already Exists!)

**File:** `lib/model-interfaces/langchain/functions/request-handler/utils/intent_detector.py`

**Capabilities:**
- `IntentDetector.analyze_query()` - Detects user intent (job_posting_creation, resume_assessment, qa_mode, general)
- Extracts structured information (job descriptions)
- Determines if RAG retrieval is needed

**Evidence:**
```python
# lib/model-interfaces/langchain/functions/request-handler/utils/intent_detector.py:54-92
@classmethod
def analyze_query(cls, user_prompt: str, workspace_id: Optional[str] = None, ...) -> Dict:
    intent = cls._detect_intent(user_prompt, workspace_id, session_history)
    job_description, clean_query = cls._extract_job_description(user_prompt)
    requires_rag = cls._requires_rag_retrieval(intent, job_description)
    return {'intent': intent, 'job_description': job_description, ...}
```

**Extension Point:** ✅ **Extend IntentDetector** to detect connector-related intents (e.g., "query database", "search SharePoint")

---

### 2.7 GraphQL Schema (`lib/chatbot-api/schema/schema.graphql`)

**Current Schema Structure:**
- Query: `listWorkspaces`, `performSemanticSearch`, `listDocuments`, `listAgents`, etc.
- Mutation: `createWorkspace*`, `addTextDocument`, `addWebsite`, `addRssFeed`, etc.
- Types: `Workspace`, `Document`, `SemanticSearchResult`, `SemanticSearchItem`, `Application`, etc.

**Extension Point:** ✅ **Additive GraphQL types** - add connector-related queries/mutations without breaking existing contracts

**Evidence:**
```graphql
# lib/chatbot-api/schema/schema.graphql:259-287
type SemanticSearchItem @aws_cognito_user_pools {
  sources: [String]
  chunkId: String
  workspaceId: ID!
  documentId: String
  # ... compatible with connector results
}
```

---

### 2.8 DynamoDB Tables

**Tables:**
1. **Workspaces Table** (`lib/rag-engines/rag-dynamodb-tables/index.ts:24-58`)
   - PK: `workspace_id`, SK: `object_type`
   - GSI: `by_object_type_idx` (PK: `object_type`, SK: `created_at`)

2. **Documents Table** (`lib/rag-engines/rag-dynamodb-tables/index.ts:60-106`)
   - PK: `workspace_id`, SK: `document_id`
   - GSI: `by_compound_key_idx` (PK: `workspace_id`, SK: `compound_sort_key`)
   - GSI: `by_status_idx` (PK: `status`, SK: `document_type`)

3. **Sessions Table** (`lib/chatbot-api/chatbot-dynamodb-tables/index.ts:19-46`)
   - PK: `SessionId`, SK: `UserId`
   - GSI: `byUserId` (PK: `UserId`)

**Extension Point:** ✅ **Create new `Connectors` table** - additive, no breaking changes

**Recommended Schema:**
```
Connectors Table:
- PK: connector_id (UUID)
- SK: workspace_id
- Attributes: connector_type, endpoint, credentials_secret_arn, allowed_resources, status, created_at, updated_at
- GSI: by_workspace (PK: workspace_id, SK: connector_type)
```

---

### 2.9 Ingestion Pipelines (`lib/shared/` & `lib/rag-engines/data-import/`)

**Existing Patterns:**
- `file-import-batch-job/` - Step Functions workflow for file processing
- `web-crawler-batch-job/` - Step Functions workflow for website crawling
- `rss-subscription.ts` - EventBridge scheduler for RSS feeds

**Pattern:** Batch ingestion → S3 → Step Functions → Chunking → Embedding → Vector Store

**Relevance:** ✅ **Connectors can use similar pattern for "index-first" mode** (future), but primary requirement is **on-demand real-time queries**

---

### 2.10 SeedFarmer Configuration Flow

**Flow:**
```
capability.yaml
  → deployment.yaml
    → module.yaml
      → SEEDFARMER_PARAMETER_* env vars
        → cli/magic-config.ts
          → bin/config.json
            → bin/aws-genai-llm-chatbot.ts
              → lib/aws-genai-llm-chatbot-stack.ts
```

**Evidence:**
- `aws-genai-llm-chatbot/capability.yaml` - Defines input parameters (e.g., `RAG_ENABLE`, `BEDROCK_ENABLE`)
- `cli/magic-config.ts` - Maps parameters to `SystemConfig` type
- `lib/shared/types.ts:80-189` - `SystemConfig` interface with `rag.engines.*` structure

**Extension Point:** ✅ **Add `connectors.enabled` and connector-specific configs** to `SystemConfig` interface

---

## 3. Best Integration Points

### 3.1 Where to Attach Connector-Driven Context Retrieval

**✅ RECOMMENDED: Hook into `resolve_context_for_prompt()` in request handler**

**Location:** `lib/model-interfaces/langchain/functions/request-handler/index.py:59-94`

**Rationale:**
1. **Non-breaking:** Function already has TODOs for context injection
2. **Centralized:** All chat requests flow through here
3. **Workspace-aware:** Already receives `workspace_id`
4. **Intent-aware:** Can leverage existing `IntentDetector`
5. **Format-compatible:** Returns string block that gets prepended to prompt (same as RAG context)

**Flow:**
```
User Query
  → IntentDetector.analyze_query() [extend to detect connector intents]
  → resolve_context_for_prompt() [add connector context retrieval]
    → genai_core.connectors.query() [new orchestrator]
      → MCP client → Connector MCP server
        → Returns context pack
          → Format as context block
            → build_augmented_prompt()
              → LLM invocation
```

**Alternative Options (Less Recommended):**
- ❌ **routes/semantic_search.py** - Only for search preview, not chat flow
- ❌ **genai_core.semantic_search** - RAG-specific, not connector-aware
- ✅ **New route: routes/connectors.py** - For connector CRUD/admin, not context retrieval

---

### 3.2 Module Organization

**Recommended Structure:**
```
lib/
├── chatbot-api/
│   └── functions/api-handler/
│       └── routes/
│           └── connectors.py          # ✅ NEW: Connector CRUD/admin routes
├── shared/
│   └── layers/python-sdk/python/genai_core/
│       └── connectors/               # ✅ NEW: Connector orchestration
│           ├── __init__.py
│           ├── registry.py          # Connector registry (DynamoDB)
│           ├── base.py              # Base connector interface/types
│           ├── mcp_client.py        # MCP client wrapper
│           ├── intent.py            # Intent classification + tool selection
│           └── safety.py            # SQL guardrails, prompt injection defense
└── connectors/                      # ✅ NEW: MCP server implementations (optional)
    ├── azure-sql/
    ├── sharepoint/
    └── dropbox/
```

---

## 4. Reusable Building Blocks

### 4.1 Registry Pattern
- **File:** `lib/shared/layers/python-sdk/python/genai_core/registry/index.py`
- **Pattern:** Regex-based adapter lookup
- **Reuse:** ✅ Create `ConnectorRegistry` class with similar pattern

### 4.2 RBAC & Permissions
- **File:** `lib/shared/layers/python-sdk/python/genai_core/auth.py`
- **Pattern:** `UserPermissions` decorator for route-level auth
- **Reuse:** ✅ Apply same decorators to connector routes

### 4.3 Secrets Management
- **Pattern:** Secrets Manager ARN stored in config, retrieved at runtime
- **Evidence:** `lib/model-interfaces/websearch/functions/websearch-handler/index.py:13-19`
- **Reuse:** ✅ Store connector credentials in Secrets Manager, reference ARN in DynamoDB

### 4.4 Intent Detection
- **File:** `lib/model-interfaces/langchain/functions/request-handler/utils/intent_detector.py`
- **Reuse:** ✅ Extend `IntentDetector` to detect connector-related intents

### 4.5 Context Formatting
- **File:** `lib/model-interfaces/langchain/functions/request-handler/index.py:39-56`
- **Pattern:** `_format_context_block()` formats results as markdown
- **Reuse:** ✅ Use same formatting for connector results

---

## 5. Contracts That Must Not Break

### 5.1 GraphQL Schema
- **File:** `lib/chatbot-api/schema/schema.graphql`
- **Contract:** All types marked `@aws_cognito_user_pools` for auth
- **Action:** ✅ Additive only - new types/queries/mutations

### 5.2 SemanticSearchResult Format
- **Type:** `SemanticSearchItem` with fields: `sources`, `chunkId`, `workspaceId`, `documentId`, `content`, `score`, etc.
- **Action:** ✅ Connector results must map to compatible format or extend type

### 5.3 DynamoDB Key Schemas
- **Workspaces:** PK `workspace_id`, SK `object_type`
- **Documents:** PK `workspace_id`, SK `document_id`
- **Action:** ✅ New Connectors table - no changes to existing tables

### 5.4 S3 Path Patterns
- **Pattern:** `{workspace_id}/{document_id}/content.txt`
- **Action:** ✅ Connectors don't use S3 (on-demand only), no impact

### 5.5 Auth/RBAC
- **Pattern:** Cognito User Pools + role-based access (`admin`, `workspace_manager`)
- **Action:** ✅ Apply same patterns to connector routes

---

## 6. Summary: Extension Points

| Component | Extension Point | Action |
|-----------|----------------|--------|
| **API Routes** | `routes/connectors.py` | ✅ Create new route module |
| **SDK Core** | `genai_core/connectors/` | ✅ Create new module |
| **Request Handler** | `resolve_context_for_prompt()` | ✅ Hook connector context retrieval |
| **Intent Detection** | `IntentDetector.analyze_query()` | ✅ Extend to detect connector intents |
| **GraphQL Schema** | Additive types/queries | ✅ Add connector-related schema |
| **DynamoDB** | New `Connectors` table | ✅ Create new table |
| **SeedFarmer Config** | `SystemConfig.connectors` | ✅ Extend config interface |
| **CDK Stack** | Conditional connector infra | ✅ Add ECS/Lambda for MCP servers |

---

## 7. Conclusion

**✅ No existing connector abstraction exists** - clean slate for MCP-based design.

**✅ Strong reusable patterns:**
- Registry pattern (adapters)
- Route-based API structure
- Intent detection framework
- Context injection hook point
- Secrets Manager integration
- RBAC patterns

**✅ Best integration point:** `resolve_context_for_prompt()` in request handler - already designed for context injection, non-breaking, workspace-aware.

**✅ Recommended architecture:** Follow RAG engine plugin pattern, but as MCP servers (ECS Fargate) rather than vector stores.

---

**Next Steps:** Proceed to Part B (MCP Architecture Design) with confidence that the codebase is well-structured for additive connector integration.
