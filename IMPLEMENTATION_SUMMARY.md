# MCP Connectors Implementation Summary

## Quick Reference

### Key Findings (Part A)
- ✅ **No existing connector abstraction** - clean slate for MCP design
- ✅ **Strong reusable patterns:** Registry, Routes, Intent Detection, Context Injection
- ✅ **Best hook point:** `resolve_context_for_prompt()` in request handler
- ✅ **Non-breaking:** All changes are additive

### Recommended Architecture (Part B)
- **Deployment:** ECS Fargate per connector type (Option 1) ⭐
- **Protocol:** MCP (Model Context Protocol)
- **Registry:** DynamoDB table (`{PREFIX}-connectors`)
- **Interface:** `BaseConnector` with required methods (discover_schema, query, search, get_item, health, capabilities)

### Integration Points (Part C)
1. **GraphQL Schema:** Additive types/queries/mutations
2. **Route:** `routes/connectors.py` for CRUD/admin
3. **SDK:** `genai_core/connectors/` for orchestration
4. **Chat Flow:** Hook into `resolve_context_for_prompt()`

### File Structure

```
lib/
├── chatbot-api/
│   ├── schema/schema.graphql                    # ✅ ADD: Connector types/queries
│   └── functions/api-handler/
│       ├── routes/connectors.py               # ✅ NEW: Connector routes
│       └── index.py                            # ✅ MODIFY: Include connectors router
│
├── shared/
│   └── layers/python-sdk/python/genai_core/
│       └── connectors/                        # ✅ NEW: Connector orchestration
│           ├── __init__.py
│           ├── registry.py                   # DynamoDB connector registry
│           ├── base.py                       # BaseConnector interface
│           ├── mcp_client.py                # MCP client wrapper
│           ├── orchestrator.py              # Main orchestration
│           ├── intent.py                    # Intent classification
│           └── safety.py                    # SQL guardrails
│
├── connectors/                                # ✅ NEW: MCP server implementations
│   ├── connector-gateway/
│   │   └── index.ts                          # CDK: ECS services + ALB
│   ├── connector-dynamodb-tables/
│   │   └── index.ts                          # CDK: Connectors table
│   ├── azure-sql-mcp-server/
│   │   ├── Dockerfile
│   │   ├── main.py                           # MCP server entry
│   │   └── connector.py                     # Azure SQL implementation
│   ├── sharepoint-mcp-server/                # Future
│   └── dropbox-mcp-server/                  # Future
│
└── model-interfaces/langchain/functions/request-handler/
    └── index.py                               # ✅ MODIFY: resolve_context_for_prompt()

aws-genai-llm-chatbot/
├── capability.yaml                            # ✅ ADD: CONNECTORS_ENABLE, etc.
└── modules/chatbot/module.yaml               # ✅ ADD: Outputs (optional)

cli/
└── magic-config.ts                           # ✅ MODIFY: Map connector params

lib/
├── shared/types.ts                           # ✅ MODIFY: Add connectors to SystemConfig
└── aws-genai-llm-chatbot-stack.ts           # ✅ MODIFY: Conditionally deploy connectors
```

---

## Critical Contracts (Must Not Break)

1. **GraphQL Schema:** All existing types/queries unchanged
2. **DynamoDB Tables:** No schema changes to Workspaces/Documents/Sessions
3. **SemanticSearchResult:** Connector results must map to compatible format
4. **Auth/RBAC:** Same Cognito + role patterns
5. **S3 Paths:** No impact (connectors are on-demand)

---

## Security & Governance

### Credentials
- ✅ **All credentials in Secrets Manager** (ARN stored in DynamoDB)
- ✅ **Never in DynamoDB, S3, or config.json**

### SQL Safety (Azure SQL)
- ✅ **Read-only:** Only SELECT allowed
- ✅ **Allowlist:** Only allowed schemas/tables/views
- ✅ **Parameterization:** All user inputs parameterized
- ✅ **Keyword blocking:** DROP, DELETE, UPDATE, INSERT, EXEC, etc.
- ✅ **LIMIT/TOP:** Enforced on all queries
- ✅ **Timeout:** 30s default
- ✅ **Row cap:** 1000 rows max
- ✅ **Audit logs:** All queries logged (configurable)

### RBAC
- ✅ **Admin/WorkspaceManager:** Can create/test connectors
- ✅ **Users:** Can only use connectors enabled for their application
- ✅ **Application-scoped:** Connectors linked to applications

---

## Testing Strategy

### Unit Tests
- `test_registry.py` - Connector registry CRUD
- `test_mcp_client.py` - MCP client (mocked)
- `test_safety.py` - SQL validation
- `test_intent.py` - Intent classification

### Integration Tests
- `test_connector_integration.py` - Create → Test → Query flow
- `test_connector_in_chat_flow.py` - Connector context in chat

### Manual Testing
- Create connector via GraphQL
- Test health check
- Execute query
- Verify safety (dangerous keywords blocked)
- Verify allowlist (unauthorized tables blocked)
- Test in chat flow
- Verify citations

---

## Deployment Steps

1. **Update SeedFarmer config:**
   - `capability.yaml` → Add connector parameters
   - `cli/magic-config.ts` → Map to SystemConfig
   - `lib/shared/types.ts` → Extend SystemConfig

2. **Deploy CDK changes:**
   - Create `ConnectorDynamoDBTables` construct
   - Create `ConnectorGateway` construct (ECS + ALB)
   - Conditionally deploy based on `config.connectors.enabled`

3. **Deploy Python SDK:**
   - Add `genai_core/connectors/` module
   - Update Lambda layers

4. **Deploy API changes:**
   - Add GraphQL schema extensions
   - Add `routes/connectors.py`
   - Update request handler hook

5. **Deploy MCP servers:**
   - Build Docker images
   - Deploy ECS services
   - Configure ALB target groups

6. **Test end-to-end:**
   - Create connector
   - Test health
   - Execute query
   - Verify in chat

---

## Next Steps

1. **Review architecture proposal** (this document + `MCP_CONNECTORS_ARCHITECTURE.md`)
2. **Approve approach** (ECS Fargate vs Lambda, MCP protocol details)
3. **Begin Phase 1:** Foundation (registry, MCP client, DynamoDB table)
4. **Iterate:** Add connectors one at a time (Azure SQL first)

---

## Questions to Resolve

1. **MCP Protocol:** Use official MCP SDK or custom protocol?
2. **VPC:** Use existing VPC or create new VPC for connectors?
3. **ALB:** Internal ALB (VPC-only) or Internet-facing (with auth)?
4. **Schema Caching:** Cache schema in DynamoDB or fetch on-demand?
5. **Dynamic SQL Generation:** Use LLM for SQL generation or template-based only?

---

## References

- **Part A Findings:** `PART_A_FINDINGS.md`
- **Full Architecture:** `MCP_CONNECTORS_ARCHITECTURE.md`
- **MCP Protocol:** https://modelcontextprotocol.io (if using official SDK)

---

**Status:** Ready for review and approval to begin implementation.
