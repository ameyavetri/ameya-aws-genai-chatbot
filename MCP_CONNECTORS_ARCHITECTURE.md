# MCP-Based Data Source Connectors Architecture Proposal

## Part B: MCP Approach Design

### B.1 Connector Interface (Common Contract)

**Location:** `lib/shared/layers/python-sdk/python/genai_core/connectors/base.py`

**Required Capabilities:**

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class SchemaMetadata:
    """Schema discovery result"""
    tables: List[Dict[str, Any]]  # For SQL: [{name, columns, type}]
    folders: List[Dict[str, Any]]  # For SharePoint/Dropbox: [{path, id, type}]
    last_updated: str

@dataclass
class QueryResult:
    """Normalized query result"""
    items: List[Dict[str, Any]]
    metadata: Dict[str, Any]  # {source, timestamp, row_count, etc.}
    citations: List[str]  # Source references for attribution

class BaseConnector(ABC):
    """Base interface all connectors must implement"""
    
    @abstractmethod
    def discover_schema(self) -> SchemaMetadata:
        """Returns schema metadata for context building"""
        pass
    
    @abstractmethod
    def query(self, intent: str, params: Dict[str, Any]) -> QueryResult:
        """
        Executes a safe query/action and returns results
        
        Args:
            intent: User intent (e.g., "get_customer_data", "search_documents")
            params: Structured parameters (e.g., {"customer_id": "123", "limit": 10})
        """
        pass
    
    @abstractmethod
    def search(self, query: str, filters: Optional[Dict[str, Any]] = None) -> QueryResult:
        """Returns relevant items/documents based on search query"""
        pass
    
    @abstractmethod
    def get_item(self, item_id: str) -> Dict[str, Any]:
        """Fetches a single item/document by ID"""
        pass
    
    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Connectivity check - returns {status: "healthy|unhealthy", details: {...}}"""
        pass
    
    @abstractmethod
    def capabilities(self) -> List[Dict[str, Any]]:
        """
        Lists supported tools/actions
        
        Returns:
            [{"name": "query_customers", "description": "...", "parameters": {...}}]
        """
        pass
    
    def incremental_sync(self, checkpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        OPTIONAL: For future "index-first RAG" mode
        Returns: {items: [...], next_checkpoint: "...", status: "..."}
        """
        raise NotImplementedError("Incremental sync not supported")
```

---

### B.2 Execution Models

#### Primary: On-Demand (Real-Time) Tool Calls via MCP

**Flow:**
```
User Query: "What customers bought product X last month?"
  ↓
IntentDetector → Detects: intent="query_database", entity="customers", filters={"product": "X", "timeframe": "last_month"}
  ↓
ConnectorRegistry.get_connectors(workspace_id) → Returns: [azure_sql_connector]
  ↓
MCP Client → Calls MCP server tool: "query_customers"
  ↓
Azure SQL Connector (MCP Server) → Executes safe SQL query
  ↓
Returns QueryResult → Normalized to Context Pack
  ↓
Injected into LLM prompt as context block
```

**MCP Protocol Integration:**
- **MCP Server:** Each connector type runs as an MCP server (e.g., Azure SQL MCP Server)
- **MCP Client:** `genai_core.connectors.mcp_client.MCPClient` wraps MCP SDK
- **Tool Calls:** Connectors expose tools via MCP (e.g., `query_customers`, `search_documents`, `get_schema`)

#### Optional: Batch Sync (Future - Index-First RAG Mode)

**Flow:**
```
EventBridge Schedule → Triggers sync Lambda
  ↓
ConnectorRegistry.get_all_connectors() → Returns connectors with sync enabled
  ↓
For each connector:
  - Call incremental_sync(checkpoint)
  - Chunk results
  - Generate embeddings
  - Store in vector store (Aurora/OpenSearch)
  ↓
Future queries use RAG instead of real-time connector calls
```

**Note:** Not in initial scope, but architecture supports it.

---

### B.3 Connector Registry

**Location:** `lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py`

**DynamoDB Table Schema:**

**Table Name:** `{PREFIX}-connectors`

**Key Schema:**
- **PK:** `connector_id` (UUID, e.g., `conn-abc123`)
- **SK:** `workspace_id` (e.g., `ws-xyz789`)

**Attributes:**
```python
{
    "connector_id": "conn-abc123",
    "workspace_id": "ws-xyz789",
    "connector_type": "azure_sql",  # azure_sql | sharepoint | dropbox | ...
    "name": "Production Customer DB",
    "status": "active" | "inactive" | "error",
    "endpoint": {
        "type": "mcp_server",  # mcp_server | lambda | http
        "url": "http://connector-gateway.internal:8080/azure-sql",  # For ECS
        # OR
        "lambda_arn": "arn:aws:lambda:...",  # For Lambda-based
    },
    "credentials_secret_arn": "arn:aws:secretsmanager:...:secret:connector-abc123",
    "allowed_resources": {
        # For Azure SQL:
        "schemas": ["dbo", "sales"],
        "tables": ["dbo.customers", "dbo.orders"],
        "views": ["dbo.customer_summary"],
        # For SharePoint:
        "sites": ["https://company.sharepoint.com/sites/sales"],
        "folders": ["/Shared Documents/Reports"],
        # For Dropbox:
        "folders": ["/Company/Reports", "/Company/Data"]
    },
    "rate_limits": {
        "max_requests_per_minute": 100,
        "max_rows_per_query": 1000,
        "timeout_seconds": 30
    },
    "audit_config": {
        "log_all_queries": True,
        "log_sensitive_data": False
    },
    "created_at": "2026-01-27T10:00:00Z",
    "updated_at": "2026-01-27T10:00:00Z",
    "created_by": "user-123",
    "application_ids": ["app-456"],  # Which applications can use this connector
}
```

**Global Secondary Index:**
- **GSI Name:** `by_workspace`
- **PK:** `workspace_id`
- **SK:** `connector_type`
- **Purpose:** Query all connectors for a workspace, filter by type

**Python Interface:**
```python
# lib/shared/layers/python-sdk/python/genai_core/connectors/registry.py

class ConnectorRegistry:
    def __init__(self, table_name: str):
        self.table = boto3.resource("dynamodb").Table(table_name)
    
    def create_connector(self, workspace_id: str, connector_config: Dict) -> str:
        """Creates connector record, returns connector_id"""
        pass
    
    def get_connector(self, connector_id: str) -> Dict:
        """Gets connector by ID"""
        pass
    
    def list_connectors(self, workspace_id: str, connector_type: Optional[str] = None) -> List[Dict]:
        """Lists connectors for workspace, optionally filtered by type"""
        pass
    
    def update_connector(self, connector_id: str, updates: Dict) -> Dict:
        """Updates connector config"""
        pass
    
    def delete_connector(self, connector_id: str) -> bool:
        """Soft delete (sets status=inactive)"""
        pass
    
    def get_connectors_for_application(self, workspace_id: str, application_id: str) -> List[Dict]:
        """Returns connectors enabled for specific application"""
        pass
```

---

### B.4 MCP Server Deployment Options

#### Option 1: ECS Fargate Service(s) per Connector Type ⭐ RECOMMENDED

**Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│  Connector Gateway (ECS Fargate)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Azure SQL    │  │ SharePoint   │  │ Dropbox      │ │
│  │ MCP Server   │  │ MCP Server   │  │ MCP Server   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                  │                  │          │
│         └──────────────────┼──────────────────┘          │
│                            │                             │
│              ┌─────────────▼─────────────┐              │
│              │  MCP Gateway (Load Bal)   │              │
│              └─────────────┬─────────────┘              │
└────────────────────────────┼────────────────────────────┘
                             │
                ┌────────────▼────────────┐
                │  Lambda (MCP Client)    │
                │  genai_core.connectors  │
                └─────────────────────────┘
```

**Pros:**
- ✅ Long-lived connections (SQL connection pooling)
- ✅ Better for stateful connectors (OAuth token refresh)
- ✅ Cost-effective for high-volume usage
- ✅ Can scale horizontally (ECS service autoscaling)
- ✅ VPC integration for private data sources
- ✅ Health checks and service discovery

**Cons:**
- ❌ More complex deployment (ECS, ALB, VPC)
- ❌ Cold start on first request (mitigated by min capacity)

**Implementation:**
- **CDK Construct:** `lib/connectors/connector-gateway/index.ts`
- **ECS Service:** One service per connector type (or single service with multiple tasks)
- **Application Load Balancer:** Internal ALB for service discovery
- **VPC:** Connectors in private subnets, Lambda in VPC (or VPC endpoint)

---

#### Option 2: Lambda + API Gateway as "MCP Tool Endpoint"

**Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│  API Gateway (REST)                                     │
│  /connectors/{connector_type}/tools/{tool_name}         │
│         │                                                │
│         └──────────────┬─────────────────┐              │
│                       │                 │                │
│         ┌─────────────▼─────┐  ┌───────▼──────────┐  │
│         │ Azure SQL Lambda   │  │ SharePoint Lambda │  │
│         └────────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Pros:**
- ✅ Simpler deployment (no ECS/VPC)
- ✅ Pay-per-request pricing
- ✅ Native AWS integration

**Cons:**
- ❌ Cold starts (15s timeout limit)
- ❌ No connection pooling (reconnect on each invocation)
- ❌ Stateless only (harder for OAuth refresh)
- ❌ Limited to 15min execution time

**Verdict:** ❌ **Not recommended** for SQL connectors (connection pooling needed), but viable for stateless connectors (SharePoint/Dropbox if using SDK).

---

#### Option 3: Single "Connector Gateway" Service (Plugin-Based)

**Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│  Connector Gateway (ECS Fargate)                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  MCP Router                                       │  │
│  │  - Routes to connector plugins                    │  │
│  │  - Manages credentials                            │  │
│  │  - Enforces rate limits                           │  │
│  └──────────────────────────────────────────────────┘  │
│         │                  │                  │          │
│  ┌──────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐ │
│  │ Azure SQL   │  │ SharePoint   │  │ Dropbox      │ │
│  │ Plugin      │  │ Plugin       │  │ Plugin        │ │
│  └─────────────┘  └──────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Pros:**
- ✅ Single deployment unit
- ✅ Shared infrastructure (ALB, VPC)
- ✅ Centralized logging/auditing

**Cons:**
- ❌ Tight coupling (all connectors in one service)
- ❌ Scaling affects all connectors
- ❌ Deployment risk (one bad connector affects all)

**Verdict:** ⚠️ **Possible future optimization**, but start with Option 1 for isolation.

---

### B.5 Recommended Deployment: Option 1 (ECS Fargate per Connector Type)

**Rationale:**
1. **SQL Connection Pooling:** Azure SQL requires persistent connections for performance
2. **OAuth Token Management:** SharePoint/Dropbox need token refresh (stateful)
3. **VPC Integration:** Private data sources require VPC endpoints
4. **Scalability:** ECS autoscaling handles traffic spikes
5. **Cost:** Fargate is cost-effective for long-running services

**CDK Structure:**
```typescript
// lib/connectors/connector-gateway/index.ts

export class ConnectorGateway extends Construct {
  public readonly loadBalancer: elbv2.ApplicationLoadBalancer;
  public readonly azureSqlService: ecs.FargateService;
  public readonly sharepointService: ecs.FargateService;
  public readonly dropboxService: ecs.FargateService;
  
  constructor(scope: Construct, id: string, props: ConnectorGatewayProps) {
    // VPC, Security Groups, ECS Cluster
    // ALB with target groups per connector type
    // ECS Services (one per connector type)
  }
}
```

**MCP Server Implementation (Python):**
```python
# lib/connectors/azure-sql-mcp-server/main.py

from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("azure-sql-connector")

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="query_customers",
            description="Query customer data from Azure SQL",
            inputSchema={
                "type": "object",
                "properties": {
                    "filters": {"type": "object"},
                    "limit": {"type": "integer", "default": 100}
                }
            }
        ),
        # ... more tools
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict) -> List[TextContent]:
    if name == "query_customers":
        # Execute safe SQL query
        # Return results
    # ...
```

---

## Part C: Integrate Connectors into Existing Chat Flow

### C.1 GraphQL Schema Extensions (Additive)

**File:** `lib/chatbot-api/schema/schema.graphql`

**Additions:**

```graphql
# New Types
type Connector @aws_cognito_user_pools {
  id: String!
  workspaceId: String!
  type: String!  # azure_sql, sharepoint, dropbox
  name: String!
  status: String!  # active, inactive, error
  allowedResources: ConnectorResources
  createdAt: AWSDateTime!
  updatedAt: AWSDateTime!
}

type ConnectorResources @aws_cognito_user_pools {
  schemas: [String!]  # For SQL
  tables: [String!]   # For SQL
  views: [String!]    # For SQL
  sites: [String!]    # For SharePoint
  folders: [String!] # For SharePoint/Dropbox
}

type ConnectorHealth @aws_cognito_user_pools {
  status: String!  # healthy, unhealthy
  details: String
  lastChecked: AWSDateTime!
}

type ConnectorQueryResult @aws_cognito_user_pools {
  items: [ConnectorResultItem!]!
  metadata: ConnectorMetadata!
  citations: [String!]!
}

type ConnectorResultItem @aws_cognito_user_pools {
  content: String!
  source: String!
  score: Float
}

type ConnectorMetadata @aws_cognito_user_pools {
  source: String!
  rowCount: Int!
  timestamp: AWSDateTime!
  query: String
}

# New Inputs
input CreateConnectorInput {
  workspaceId: String!
  type: String!
  name: String!
  endpoint: ConnectorEndpointInput!
  credentialsSecretArn: String!
  allowedResources: ConnectorResourcesInput!
  applicationIds: [String!]
}

input ConnectorEndpointInput {
  type: String!  # mcp_server, lambda, http
  url: String
  lambdaArn: String
}

input ConnectorResourcesInput {
  schemas: [String!]
  tables: [String!]
  views: [String!]
  sites: [String!]
  folders: [String!]
}

input TestConnectorInput {
  connectorId: String!
}

input RunConnectorQueryInput {
  workspaceId: String!
  connectorId: String!
  userPrompt: String  # Natural language query
  intent: String      # OR structured intent (e.g., "query_customers")
  params: String      # JSON string of parameters
}

# New Queries
extend type Query {
  listConnectors(workspaceId: String!): [Connector!]!
    @aws_cognito_user_pools(cognito_groups: ["admin", "workspace_manager"])
  getConnector(connectorId: String!): Connector
    @aws_cognito_user_pools(cognito_groups: ["admin", "workspace_manager"])
  testConnector(input: TestConnectorInput!): ConnectorHealth!
    @aws_cognito_user_pools(cognito_groups: ["admin", "workspace_manager"])
  runConnectorQuery(input: RunConnectorQueryInput!): ConnectorQueryResult!
    @aws_cognito_user_pools
}

# New Mutations
extend type Mutation {
  createConnector(input: CreateConnectorInput!): Connector!
    @aws_cognito_user_pools(cognito_groups: ["admin", "workspace_manager"])
  updateConnector(connectorId: String!, input: CreateConnectorInput!): Connector!
    @aws_cognito_user_pools(cognito_groups: ["admin", "workspace_manager"])
  deleteConnector(connectorId: String!): Boolean!
    @aws_cognito_user_pools(cognito_groups: ["admin", "workspace_manager"])
}
```

**Backward Compatibility:** ✅ All additions are new types/queries/mutations - no breaking changes.

---

### C.2 New Route Module

**File:** `lib/chatbot-api/functions/api-handler/routes/connectors.py`

```python
from common.constant import ID_FIELD_VALIDATION, SAFE_PROMPT_STR_REGEX
import genai_core.connectors.registry
import genai_core.connectors.orchestrator
from pydantic import BaseModel, Field
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler.appsync import Router
from genai_core.auth import UserPermissions

tracer = Tracer()
router = Router()
logger = Logger()
permissions = UserPermissions(router)

class CreateConnectorRequest(BaseModel):
    workspaceId: str = ID_FIELD_VALIDATION
    type: str = Field(pattern=r"^(azure_sql|sharepoint|dropbox)$")
    name: str = Field(min_length=1, max_length=100)
    endpoint: dict
    credentialsSecretArn: str
    allowedResources: dict
    applicationIds: list = Field(default=[])

class TestConnectorRequest(BaseModel):
    connectorId: str = ID_FIELD_VALIDATION

class RunConnectorQueryRequest(BaseModel):
    workspaceId: str = ID_FIELD_VALIDATION
    connectorId: str = ID_FIELD_VALIDATION
    userPrompt: str = Field(max_length=1000, pattern=SAFE_PROMPT_STR_REGEX)
    intent: str = Field(default=None)
    params: str = Field(default=None)

@router.resolver(field_name="listConnectors")
@tracer.capture_method
@permissions.approved_roles([permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE])
def list_connectors(input: dict):
    request = {"workspaceId": input["workspaceId"]}
    connectors = genai_core.connectors.registry.list_connectors(request["workspaceId"])
    return [_convert_connector(c) for c in connectors]

@router.resolver(field_name="createConnector")
@tracer.capture_method
@permissions.approved_roles([permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE])
def create_connector(input: dict):
    request = CreateConnectorRequest(**input)
    connector_id = genai_core.connectors.registry.create_connector(
        workspace_id=request.workspaceId,
        connector_config={
            "type": request.type,
            "name": request.name,
            "endpoint": request.endpoint,
            "credentials_secret_arn": request.credentialsSecretArn,
            "allowed_resources": request.allowedResources,
            "application_ids": request.applicationIds,
        }
    )
    connector = genai_core.connectors.registry.get_connector(connector_id)
    return _convert_connector(connector)

@router.resolver(field_name="testConnector")
@tracer.capture_method
@permissions.approved_roles([permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE])
def test_connector(input: dict):
    request = TestConnectorRequest(**input)
    health = genai_core.connectors.orchestrator.test_connector(request.connectorId)
    return {
        "status": health["status"],
        "details": health.get("details"),
        "lastChecked": health.get("timestamp"),
    }

@router.resolver(field_name="runConnectorQuery")
@tracer.capture_method
@permissions.approved_roles([permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE, permissions.USER_ROLE])
def run_connector_query(input: dict):
    request = RunConnectorQueryRequest(**input)
    
    # RBAC: Check if user's application has access to this connector
    user_roles = genai_core.auth.get_user_roles(router)
    application_id = input.get("applicationId")  # From request context
    
    # Execute query via orchestrator
    result = genai_core.connectors.orchestrator.execute_query(
        workspace_id=request.workspaceId,
        connector_id=request.connectorId,
        user_prompt=request.userPrompt,
        intent=request.intent,
        params=json.loads(request.params) if request.params else None,
        application_id=application_id,
    )
    
    return {
        "items": [_convert_result_item(item) for item in result["items"]],
        "metadata": result["metadata"],
        "citations": result["citations"],
    }

def _convert_connector(connector: dict):
    # Convert DynamoDB item to GraphQL type
    pass

def _convert_result_item(item: dict):
    # Convert QueryResult item to GraphQL type
    pass
```

**Register in:** `lib/chatbot-api/functions/api-handler/index.py`
```python
from routes.connectors import router as connectors_router
app.include_router(connectors_router)
```

---

### C.3 Orchestration in genai_core

**File Structure:**
```
lib/shared/layers/python-sdk/python/genai_core/connectors/
├── __init__.py
├── registry.py          # DynamoDB connector registry
├── base.py             # BaseConnector interface & types
├── mcp_client.py       # MCP client wrapper
├── orchestrator.py     # Main orchestration logic
├── intent.py           # Intent classification + tool selection
└── safety.py           # SQL guardrails, prompt injection defense
```

**Key File: `orchestrator.py`**

```python
# lib/shared/layers/python-sdk/python/genai_core/connectors/orchestrator.py

import genai_core.connectors.registry
import genai_core.connectors.mcp_client
import genai_core.connectors.intent
import genai_core.connectors.safety
from genai_core.connectors.base import QueryResult

def execute_query(
    workspace_id: str,
    connector_id: str,
    user_prompt: str,
    intent: Optional[str] = None,
    params: Optional[Dict] = None,
    application_id: Optional[str] = None,
) -> Dict:
    """
    Main orchestration function for connector queries
    
    Returns:
        {
            "items": [...],
            "metadata": {...},
            "citations": [...]
        }
    """
    # 1. Get connector config
    connector = genai_core.connectors.registry.get_connector(connector_id)
    
    # 2. RBAC: Verify application has access
    if application_id and application_id not in connector.get("application_ids", []):
        raise genai_core.types.CommonError("Connector not enabled for this application")
    
    # 3. Intent classification (if not provided)
    if not intent:
        intent_analysis = genai_core.connectors.intent.classify_intent(
            user_prompt=user_prompt,
            connector_type=connector["connector_type"],
            schema=connector.get("schema_cache"),  # Cached schema
        )
        intent = intent_analysis["intent"]
        params = intent_analysis["params"]
    
    # 4. Safety validation
    genai_core.connectors.safety.validate_query(
        connector_type=connector["connector_type"],
        intent=intent,
        params=params,
        allowed_resources=connector["allowed_resources"],
    )
    
    # 5. Call MCP server
    mcp_client = genai_core.connectors.mcp_client.MCPClient(
        endpoint=connector["endpoint"]["url"],
    )
    
    result = mcp_client.call_tool(
        tool_name=intent,
        arguments=params,
    )
    
    # 6. Normalize to Context Pack
    context_pack = _normalize_to_context_pack(result, connector)
    
    return context_pack

def test_connector(connector_id: str) -> Dict:
    """Tests connector health"""
    connector = genai_core.connectors.registry.get_connector(connector_id)
    mcp_client = genai_core.connectors.mcp_client.MCPClient(
        endpoint=connector["endpoint"]["url"],
    )
    health = mcp_client.call_tool("health", {})
    return health

def _normalize_to_context_pack(mcp_result: Dict, connector: Dict) -> Dict:
    """Converts MCP tool result to standardized Context Pack format"""
    # Map MCP result to QueryResult format
    # Add citations with source metadata
    pass
```

---

### C.4 Hook into Chat Flow

**File:** `lib/model-interfaces/langchain/functions/request-handler/index.py`

**Modify `resolve_context_for_prompt()` function:**

```python
def resolve_context_for_prompt(prompt: str, source_mode: str, workspace_id: str, user_id: str, application_id: Optional[str] = None) -> str:
    """
    Phase-2: Enhanced with connector support.
    - INTERNAL: pull RAG context
    - WEB: pull web context
    - CONNECTOR: pull connector context (NEW)
    - HYBRID: combination
    """
    mode = _normalize_source_mode(source_mode)
    
    internal_items = []
    web_items = []
    connector_items = []  # NEW
    
    # ---- INTERNAL RAG ----
    if mode in ["internal", "hybrid"]:
        # Existing RAG retrieval (unchanged)
        internal_items = []
    
    # ---- WEB SEARCH ----
    if mode in ["web", "hybrid"]:
        # Existing web search (unchanged)
        web_items = []
    
    # ---- CONNECTOR CONTEXT (NEW) ----
    if workspace_id and application_id:
        # Check if connectors are enabled for this workspace/application
        try:
            connectors = genai_core.connectors.registry.get_connectors_for_application(
                workspace_id=workspace_id,
                application_id=application_id,
            )
            
            # Detect if query needs connector context
            intent_analysis = genai_core.connectors.intent.detect_connector_intent(prompt)
            
            if intent_analysis["needs_connector"]:
                # Execute connector query
                connector_result = genai_core.connectors.orchestrator.execute_query(
                    workspace_id=workspace_id,
                    connector_id=intent_analysis["connector_id"],
                    user_prompt=prompt,
                    application_id=application_id,
                )
                
                # Format as context items
                connector_items = [
                    {
                        "title": item.get("source", "Connector Result"),
                        "snippet": item.get("content", ""),
                        "url": item.get("source_url", ""),
                    }
                    for item in connector_result["items"]
                ]
        except Exception as e:
            logger.warning(f"Connector context retrieval failed: {e}")
            # Fail gracefully - don't break chat flow
    
    # Format context blocks
    parts = []
    internal_block = _format_context_block("Internal Knowledge Base Results", internal_items)
    if internal_block:
        parts.append(internal_block)
    
    web_block = _format_context_block("Internet Search Results", web_items)
    if web_block:
        parts.append(web_block)
    
    connector_block = _format_context_block("External Data Source Results", connector_items)  # NEW
    if connector_block:
        parts.append(connector_block)
    
    return "\n\n".join(parts).strip()
```

**Why This Hook Point:**
1. ✅ **Non-breaking:** Function already designed for context injection
2. ✅ **Workspace-aware:** Already receives `workspace_id`
3. ✅ **Application-aware:** Can check connector permissions
4. ✅ **Format-compatible:** Returns string block (same as RAG/web)
5. ✅ **Fail-safe:** Errors don't break chat flow

---

## Part D: SeedFarmer Config + Deployment Wiring

### D.1 capability.yaml

**File:** `aws-genai-llm-chatbot/capability.yaml`

**Additions:**

```yaml
input:
  # ... existing inputs ...
  
  - name: CONNECTORS_ENABLE
    type: Boolean
    description: Enable data source connectors via MCP
    defaultValue: false
    label: Enable Connectors
    isRequired: false
  
  - name: CONNECTORS_AZURE_SQL_ENABLE
    type: Boolean
    description: Enable Azure SQL Server connector
    defaultValue: false
    label: Enable Azure SQL Connector
    isRequired: false
  
  - name: CONNECTORS_SHAREPOINT_ENABLE
    type: Boolean
    description: Enable SharePoint connector
    defaultValue: false
    label: Enable SharePoint Connector
    isRequired: false
  
  - name: CONNECTORS_DROPBOX_ENABLE
    type: Boolean
    description: Enable Dropbox connector
    defaultValue: false
    label: Enable Dropbox Connector
    isRequired: false
  
  - name: CONNECTORS_VPC_ID
    type: String
    description: VPC ID for connector gateway (required if connectors enabled)
    defaultValue: ""
    label: Connector Gateway VPC ID
    isRequired: false
```

---

### D.2 cli/magic-config.ts

**File:** `cli/magic-config.ts`

**Additions:**

```typescript
// In the config generation function

const connectorsEnabled = getParameter("CONNECTORS_ENABLE", false);
const connectorsAzureSqlEnabled = getParameter("CONNECTORS_AZURE_SQL_ENABLE", false);
const connectorsSharePointEnabled = getParameter("CONNECTORS_SHAREPOINT_ENABLE", false);
const connectorsDropboxEnabled = getParameter("CONNECTORS_DROPBOX_ENABLE", false);
const connectorsVpcId = getParameter("CONNECTORS_VPC_ID", "");

const config: SystemConfig = {
  // ... existing config ...
  connectors: {
    enabled: connectorsEnabled,
    vpcId: connectorsVpcId || undefined,
    azureSql: {
      enabled: connectorsAzureSqlEnabled,
    },
    sharepoint: {
      enabled: connectorsSharePointEnabled,
    },
    dropbox: {
      enabled: connectorsDropboxEnabled,
    },
  },
};
```

---

### D.3 lib/shared/types.ts

**File:** `lib/shared/types.ts`

**Additions:**

```typescript
export interface SystemConfig {
  // ... existing fields ...
  
  connectors?: {
    enabled: boolean;
    vpcId?: string;
    azureSql?: {
      enabled: boolean;
    };
    sharepoint?: {
      enabled: boolean;
    };
    dropbox?: {
      enabled: boolean;
    };
  };
}
```

---

### D.4 lib/aws-genai-llm-chatbot-stack.ts

**File:** `lib/aws-genai-llm-chatbot-stack.ts`

**Additions:**

```typescript
import { ConnectorGateway } from "./connectors/connector-gateway";
import { ConnectorDynamoDBTables } from "./connectors/connector-dynamodb-tables";

export class AwsGenaiLlmChatbotStack extends Stack {
  constructor(scope: Construct, id: string, props: StackProps) {
    super(scope, id, props);
    
    // ... existing constructs ...
    
    // Conditionally deploy connector infrastructure
    const connectorsEnabled = config.connectors?.enabled ?? false;
    
    if (connectorsEnabled) {
      // DynamoDB table for connector registry
      const connectorTables = new ConnectorDynamoDBTables(this, "ConnectorTables", {
        kmsKey: shared.kmsKey,
        retainOnDelete: config.retainOnDelete,
        deletionProtection: config.ddbDeletionProtection,
      });
      
      // Connector Gateway (ECS services)
      const connectorGateway = new ConnectorGateway(this, "ConnectorGateway", {
        vpc: vpc,  // From existing VPC or create new
        azureSqlEnabled: config.connectors?.azureSql?.enabled ?? false,
        sharepointEnabled: config.connectors?.sharepoint?.enabled ?? false,
        dropboxEnabled: config.connectors?.dropbox?.enabled ?? false,
        secretsManager: shared.secretsManager,
      });
      
      // Grant Lambda access to connector tables
      apiHandler.addEnvironment("CONNECTORS_TABLE_NAME", connectorTables.connectorsTable.tableName);
      connectorTables.connectorsTable.grantReadWriteData(apiHandler);
      
      // Grant Lambda access to connector gateway (VPC endpoint or ALB)
      // ...
    }
  }
}
```

---

### D.5 module.yaml

**File:** `aws-genai-llm-chatbot/modules/chatbot/module.yaml`

**Additions (if needed for outputs):**

```yaml
outputs:
  # ... existing outputs ...
  
  - name: CONNECTOR_GATEWAY_URL
    value: ${ConnectorGateway.LoadBalancer.DNSName}
    description: Internal ALB DNS for connector gateway
  
  - name: CONNECTORS_TABLE_NAME
    value: ${ConnectorTables.ConnectorsTable.TableName}
    description: DynamoDB table name for connector registry
```

---

## Part E: First Connectors (Design + Stubs)

### E.1 Azure SQL Server Connector

**Location:** `lib/connectors/azure-sql-mcp-server/`

**Files:**
```
azure-sql-mcp-server/
├── Dockerfile
├── requirements.txt
├── main.py                    # MCP server entry point
├── connector.py              # Azure SQL connector implementation
├── safety.py                 # SQL safety validation
└── schema_discovery.py       # Schema discovery logic
```

**Key Implementation:**

```python
# lib/connectors/azure-sql-mcp-server/connector.py

import pyodbc
import genai_core.connectors.base
import genai_core.connectors.safety

class AzureSqlConnector(genai_core.connectors.base.BaseConnector):
    def __init__(self, connection_string: str, allowed_resources: Dict):
        self.connection_string = connection_string
        self.allowed_resources = allowed_resources
        self.connection_pool = self._create_connection_pool()
    
    def discover_schema(self) -> SchemaMetadata:
        """Discovers schemas, tables, views from allowed_resources"""
        # Query INFORMATION_SCHEMA for allowed schemas/tables/views
        # Returns: SchemaMetadata(tables=[...], folders=[], last_updated=...)
        pass
    
    def query(self, intent: str, params: Dict) -> QueryResult:
        """
        Executes safe SQL query
        
        Safety checks:
        1. Validate intent maps to allowed table/view
        2. Parameterize all user inputs
        3. Enforce LIMIT/TOP
        4. Block dangerous keywords (DROP, DELETE, UPDATE, INSERT, EXEC, etc.)
        5. Enforce read-only (only SELECT allowed)
        6. Timeout (30s default)
        7. Row cap (1000 default)
        """
        # 1. Map intent to SQL template
        sql_template = self._get_sql_template(intent)
        
        # 2. Safety validation
        genai_core.connectors.safety.validate_sql(
            sql_template=sql_template,
            params=params,
            allowed_resources=self.allowed_resources,
        )
        
        # 3. Build parameterized query
        sql, query_params = self._build_parameterized_query(sql_template, params)
        
        # 4. Execute with timeout
        results = self._execute_query(sql, query_params, timeout=30, max_rows=1000)
        
        # 5. Format as QueryResult
        return QueryResult(
            items=results,
            metadata={"source": "azure_sql", "row_count": len(results), ...},
            citations=[f"azure_sql://{self.allowed_resources['schemas'][0]}/..."],
        )
    
    def _get_sql_template(self, intent: str) -> str:
        """Maps intent to SQL template"""
        templates = {
            "query_customers": "SELECT * FROM {schema}.customers WHERE {filters} LIMIT {limit}",
            "query_orders": "SELECT * FROM {schema}.orders WHERE {filters} LIMIT {limit}",
            # ... more templates
        }
        return templates.get(intent)
    
    def _build_parameterized_query(self, template: str, params: Dict) -> Tuple[str, List]:
        """Builds parameterized SQL query"""
        # Replace {schema}, {filters}, {limit} with safe values
        # Use pyodbc parameterization for user inputs
        pass
    
    def _execute_query(self, sql: str, params: List, timeout: int, max_rows: int) -> List[Dict]:
        """Executes query with connection pooling"""
        with self.connection_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            # Fetch max_rows rows
            # Convert to list of dicts
            pass
```

**SQL Safety Validation (`safety.py`):**

```python
# lib/shared/layers/python-sdk/python/genai_core/connectors/safety.py

DANGEROUS_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "EXEC", "EXECUTE",
    "xp_cmdshell", "sp_", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "BACKUP", "RESTORE",
]

def validate_sql(sql_template: str, params: Dict, allowed_resources: Dict) -> None:
    """Validates SQL query for safety"""
    sql_upper = sql_template.upper()
    
    # 1. Check for dangerous keywords
    for keyword in DANGEROUS_KEYWORDS:
        if keyword in sql_upper:
            raise genai_core.types.CommonError(f"Dangerous keyword '{keyword}' not allowed")
    
    # 2. Ensure only SELECT statements
    if not sql_upper.strip().startswith("SELECT"):
        raise genai_core.types.CommonError("Only SELECT queries are allowed")
    
    # 3. Validate tables/views are in allowlist
    # Extract table/view names from SQL
    # Check against allowed_resources["tables"] and allowed_resources["views"]
    
    # 4. Ensure LIMIT/TOP is present
    if "LIMIT" not in sql_upper and "TOP" not in sql_upper:
        raise genai_core.types.CommonError("Query must include LIMIT or TOP clause")
    
    # 5. Validate schemas are in allowlist
    # Extract schema names
    # Check against allowed_resources["schemas"]
    
    pass
```

**Dynamic Query Generation Strategy:**

1. **Schema Discovery:** Cache schema metadata (tables, columns, types) in connector config
2. **Intent Classification:** Map user prompt to intent (e.g., "query_customers", "search_orders")
3. **Template Selection:** Choose SQL template based on intent
4. **Parameter Extraction:** Extract filters from user prompt (e.g., "last month" → `WHERE order_date >= DATEADD(month, -1, GETDATE())`)
5. **LLM-Assisted (Optional):** Use constrained LLM prompt to generate SQL from schema + user intent, then validate against allowlist

**MCP Server Entry Point:**

```python
# lib/connectors/azure-sql-mcp-server/main.py

from mcp.server import Server
from mcp.types import Tool, TextContent
import genai_core.connectors.base

server = Server("azure-sql-connector")

# Load connector config from environment
connector = AzureSqlConnector(
    connection_string=os.environ["AZURE_SQL_CONNECTION_STRING"],
    allowed_resources=json.loads(os.environ["ALLOWED_RESOURCES"]),
)

@server.list_tools()
async def list_tools() -> List[Tool]:
    """Lists available tools based on schema discovery"""
    schema = connector.discover_schema()
    tools = []
    
    for table in schema.tables:
        tools.append(Tool(
            name=f"query_{table['name']}",
            description=f"Query {table['name']} table",
            inputSchema={
                "type": "object",
                "properties": {
                    "filters": {"type": "object"},
                    "limit": {"type": "integer", "default": 100}
                }
            }
        ))
    
    return tools

@server.call_tool()
async def call_tool(name: str, arguments: Dict) -> List[TextContent]:
    """Executes tool call"""
    if name == "health":
        health = connector.health()
        return [TextContent(type="text", text=json.dumps(health))]
    
    intent = name  # e.g., "query_customers"
    result = connector.query(intent=intent, params=arguments)
    
    return [TextContent(
        type="text",
        text=json.dumps({
            "items": result.items,
            "metadata": result.metadata,
            "citations": result.citations,
        })
    )]

if __name__ == "__main__":
    server.run()
```

---

### E.2 SharePoint Connector (Placeholder)

**Location:** `lib/connectors/sharepoint-mcp-server/`

**Auth Approach:**
- **OAuth 2.0:** Azure AD app registration
- **Token Storage:** Refresh token in Secrets Manager
- **Token Refresh:** Background task in MCP server (stateful)

**Tools:**
- `search_documents(query, site, folder)` - Search SharePoint
- `get_item(item_id)` - Get document by ID
- `list_folder(folder_path)` - List folder contents
- `get_schema()` - Discover sites/folders

**Allowlists:**
- Sites: `allowed_resources["sites"]`
- Folders: `allowed_resources["folders"]`

---

### E.3 Dropbox Connector (Placeholder)

**Location:** `lib/connectors/dropbox-mcp-server/`

**Auth Approach:**
- **OAuth 2.0:** Dropbox app
- **Token Storage:** Access token in Secrets Manager
- **Token Refresh:** As needed (Dropbox tokens are long-lived)

**Tools:**
- `search_files(query, folder)` - Search Dropbox
- `get_file(file_id)` - Get file by ID
- `list_folder(folder_path)` - List folder contents
- `get_schema()` - Discover folders

**Allowlists:**
- Folders: `allowed_resources["folders"]`

---

## Part F: Testing Plan

### F.1 Before Changes Baseline

**Commands:**
```bash
npm run build
npm run test
npm run pytest
npm run integtest  # If available
```

**Expected:** All tests pass, no regressions.

---

### F.2 After Changes

**Same Commands:**
```bash
npm run build
npm run test
npm run pytest
npm run integtest
```

**Expected:** All existing tests still pass (additive changes only).

---

### F.3 New Unit Tests

**Location:** `tests/shared/layers/python-sdk/genai_core/connectors/`

**Test Files:**

1. **`test_registry.py`**
   ```python
   def test_create_connector():
       # Create connector via registry
       # Verify DynamoDB item created
       pass
   
   def test_list_connectors():
       # List connectors for workspace
       # Verify filtering by type
       pass
   
   def test_get_connector():
       # Get connector by ID
       # Verify all fields returned
       pass
   ```

2. **`test_mcp_client.py`** (with mocks)
   ```python
   @patch('requests.post')
   def test_mcp_client_call_tool():
       # Mock MCP server response
       # Verify tool call format
       # Verify result parsing
       pass
   ```

3. **`test_safety.py`**
   ```python
   def test_sql_validation_dangerous_keywords():
       # Test DROP, DELETE, etc. are blocked
       pass
   
   def test_sql_validation_allowlist():
       # Test only allowed tables/views
       pass
   
   def test_sql_validation_parameterization():
       # Test SQL injection prevention
       pass
   
   def test_sql_validation_read_only():
       # Test only SELECT allowed
       pass
   ```

4. **`test_intent.py`**
   ```python
   def test_detect_connector_intent():
       # Test intent classification
       # Test parameter extraction
       pass
   ```

---

### F.4 Integration Tests

**Location:** `integtests/connectors/`

**Test File:** `test_connector_integration.py`

```python
def test_create_and_test_connector():
    """
    Integration test:
    1. Create connector config via GraphQL
    2. Test connector health
    3. Execute sample query
    4. Verify response format
    """
    # 1. Create connector
    create_response = appsync_client.mutate(
        mutation=create_connector_mutation,
        variables={
            "input": {
                "workspaceId": workspace_id,
                "type": "azure_sql",
                "name": "Test DB",
                # ... config
            }
        }
    )
    connector_id = create_response["createConnector"]["id"]
    
    # 2. Test connector
    test_response = appsync_client.query(
        query=test_connector_query,
        variables={"input": {"connectorId": connector_id}}
    )
    assert test_response["testConnector"]["status"] == "healthy"
    
    # 3. Execute query
    query_response = appsync_client.query(
        query=run_connector_query_query,
        variables={
            "input": {
                "workspaceId": workspace_id,
                "connectorId": connector_id,
                "userPrompt": "Show me customers from last month",
            }
        }
    )
    
    # 4. Verify response
    assert "items" in query_response["runConnectorQuery"]
    assert "citations" in query_response["runConnectorQuery"]
    assert len(query_response["runConnectorQuery"]["items"]) > 0
```

**Test File:** `test_connector_in_chat_flow.py`

```python
def test_connector_context_in_chat():
    """
    Integration test: Verify connector context is injected into chat
    """
    # 1. Create connector
    # 2. Send chat message that triggers connector
    # 3. Verify LLM response includes connector context
    # 4. Verify citations are present
    pass
```

---

### F.5 Manual Testing Checklist

**Before Deployment:**
- [ ] Create connector via GraphQL API
- [ ] Test connector health check
- [ ] Execute sample query
- [ ] Verify SQL safety (try dangerous keywords - should fail)
- [ ] Verify allowlist enforcement (try unauthorized table - should fail)
- [ ] Test connector in chat flow (send query that needs connector)
- [ ] Verify citations in response
- [ ] Test RBAC (user without access cannot use connector)

**After Deployment:**
- [ ] Verify existing RAG still works
- [ ] Verify existing chat flow unchanged
- [ ] Verify no DynamoDB schema changes to existing tables
- [ ] Verify GraphQL schema backward compatible

---

## Summary: Implementation Checklist

### Phase 1: Foundation
- [ ] Create `genai_core/connectors/` module structure
- [ ] Implement `ConnectorRegistry` (DynamoDB)
- [ ] Implement `MCPClient` wrapper
- [ ] Create `Connectors` DynamoDB table (CDK)
- [ ] Add GraphQL schema extensions
- [ ] Create `routes/connectors.py`

### Phase 2: Safety & Intent
- [ ] Implement `safety.py` (SQL validation)
- [ ] Implement `intent.py` (intent classification)
- [ ] Unit tests for safety validation
- [ ] Unit tests for intent detection

### Phase 3: Orchestration
- [ ] Implement `orchestrator.py`
- [ ] Hook into `resolve_context_for_prompt()`
- [ ] Integration tests

### Phase 4: Azure SQL Connector
- [ ] Create Azure SQL MCP server (Docker)
- [ ] Implement schema discovery
- [ ] Implement query execution with safety
- [ ] Deploy ECS service
- [ ] End-to-end test

### Phase 5: SeedFarmer Integration
- [ ] Update `capability.yaml`
- [ ] Update `magic-config.ts`
- [ ] Update `types.ts`
- [ ] Update CDK stack
- [ ] Deploy and verify

### Phase 6: SharePoint & Dropbox (Future)
- [ ] SharePoint MCP server
- [ ] Dropbox MCP server
- [ ] OAuth token management
- [ ] End-to-end tests

---

**Estimated Timeline:**
- Phase 1-2: 2 weeks
- Phase 3: 1 week
- Phase 4: 2 weeks
- Phase 5: 1 week
- Phase 6: 2 weeks (future)

**Total:** ~6 weeks for MVP (Azure SQL), ~8 weeks for full implementation (all connectors).
