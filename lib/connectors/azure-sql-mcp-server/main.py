"""Azure SQL MCP Server entry point.

This server exposes tools via HTTP using MCP-compatible endpoints:
- GET /health: Health check endpoint for ALB
- GET /tools: List available tools
- POST /tools/{tool_name}: Execute a tool
"""

import json
import logging
import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from connector import AzureSqlConnector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Azure SQL MCP Server")

# Initialize connector
connector = AzureSqlConnector()


class ToolArguments(BaseModel):
    """Tool arguments model."""

    arguments: Dict[str, Any] = {}


@app.get("/health")
async def health_endpoint():
    """Health check endpoint for ALB health checks.

    Returns 200 when the server is running so the ALB marks the target healthy.
    If DB credentials are not configured or DB is unreachable, returns 200 with
    status 'degraded' so the service can stabilize; use response body for details.
    """
    try:
        result = connector.health()
        # Always return 200 for ALB: healthy = OK, unhealthy = degraded but process is up
        status_code = 200
        return JSONResponse(content=result, status_code=status_code)
    except Exception as e:
        logger.warning(f"Health check (degraded): {e}")
        # Return 200 so ECS/ALB stabilizes when credentials are not yet configured
        return JSONResponse(
            content={
                "status": "degraded",
                "details": {"error": str(e), "message": "Credentials not configured or DB unreachable"},
            },
            status_code=200,
        )


@app.get("/tools")
async def list_tools():
    """List available MCP tools."""
    return [
        {
            "name": "health",
            "description": "Check the health of the Azure SQL connector",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "discover_schema",
            "description": "Discover schema metadata for allowed schemas, tables, and views",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "query",
            "description": "Execute a safe SQL query",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Query intent (e.g., 'query_customers', 'query_orders')",
                    },
                    "sql_template": {
                        "type": "string",
                        "description": "SQL query template with placeholders (e.g., '{customer_id}')",
                    },
                    "sql": {
                        "type": "string",
                        "description": "Alternative to sql_template - direct SQL query",
                    },
                    "params": {
                        "type": "object",
                        "description": "Query parameters dict (e.g., {'customer_id': '123', 'limit': 100})",
                    },
                },
                "required": ["intent"],
            },
        },
    ]


@app.post("/tools/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    """Execute an MCP tool."""
    try:
        body = await request.json()
        arguments = body.get("arguments", {})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    try:
        if tool_name == "health":
            result = connector.health()
            return JSONResponse(content=result)

        elif tool_name == "discover_schema":
            result = connector.discover_schema()
            return JSONResponse(content=result)

        elif tool_name == "query":
            intent = arguments.get("intent", "")
            sql_template = arguments.get("sql_template", "")
            sql = arguments.get("sql", "")
            params = arguments.get("params", {})

            if not sql_template and not sql:
                raise HTTPException(
                    status_code=400, detail="Either sql_template or sql parameter is required"
                )

            query_params = {
                "sql_template": sql_template or sql,
                "params": params or {},
            }

            result = connector.query(intent, query_params)
            return JSONResponse(content=result)

        else:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    except ValueError as e:
        logger.error(f"Tool '{tool_name}' validation failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Tool '{tool_name}' execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {e}")


if __name__ == "__main__":
    import uvicorn

    # Get port from environment or default to 8080
    port = int(os.getenv("PORT", "8080"))

    logger.info(f"Starting Azure SQL MCP Server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
