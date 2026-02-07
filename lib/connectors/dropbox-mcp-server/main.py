"""Dropbox MCP Server entry point.

Exposes tools via HTTP (MCP-style):
- GET /health: Health check for ALB
- GET /tools: List available tools
- POST /tools/{tool_name}: Execute a tool
"""

import logging
import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from connector import DropboxConnector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Dropbox MCP Server")
connector = DropboxConnector()


class ToolArguments(BaseModel):
    arguments: Dict[str, Any] = {}


@app.get("/health")
async def health_endpoint():
    """Health check for ALB. Returns 200 so ECS stabilizes."""
    try:
        result = connector.health()
        return JSONResponse(content=result, status_code=200)
    except Exception as e:
        logger.warning("Health check (degraded): %s", e)
        return JSONResponse(
            content={
                "status": "degraded",
                "details": {"error": str(e), "message": "Credentials not configured or Dropbox unreachable"},
            },
            status_code=200,
        )


@app.get("/tools")
async def list_tools():
    """List available MCP tools."""
    return [
        {
            "name": "health",
            "description": "Check the health of the Dropbox connector",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_files",
            "description": "List files and folders in a Dropbox path",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Dropbox path (e.g. / or /Documents)"}},
            },
        },
        {
            "name": "search_files",
            "description": "Search for files in Dropbox by query",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
            },
        },
        {
            "name": "search_documents",
            "description": "Search documents in Dropbox (used by chatbot intent)",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
            },
        },
        {
            "name": "get_file_content",
            "description": "Get content of a file from Dropbox",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Full path to file in Dropbox"}},
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
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}") from e

    if tool_name == "health":
        return JSONResponse(content=connector.health())

    if tool_name == "list_files":
        path = arguments.get("path", "")
        return JSONResponse(content=connector.list_files(path=path))

    if tool_name == "search_files":
        query = arguments.get("query", "")
        return JSONResponse(content=connector.search_files(query=query))

    if tool_name == "search_documents":
        query = arguments.get("query", "")
        result = connector.search_files(query=query)
        # Shape expected by orchestrator: items, metadata, citations
        return JSONResponse(
            content={
                "items": result.get("matches") or [],
                "metadata": {"source": "dropbox", "query": query},
                "citations": [],
            }
        )

    if tool_name == "get_file_content":
        path = arguments.get("path", "")
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        return JSONResponse(content=connector.get_file_content(path))

    raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting Dropbox MCP Server on port %s", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
