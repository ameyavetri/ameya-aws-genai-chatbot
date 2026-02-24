from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from aws_lambda_powertools import Logger

from genai_core.connectors.base import QueryResult
from genai_core.connectors import intent as intent_module
from genai_core.connectors import mcp_client as mcp_client_module
from genai_core.connectors import metrics as metrics_module
from genai_core.connectors import registry as registry_module
from genai_core.connectors import safety as safety_module
from genai_core.types import CommonError

logger = Logger()


def execute_query(
    workspace_id: str,
    connector_id: str,
    user_prompt: str,
    intent: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    application_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Main orchestration function for connector queries.

    Returns a dict shaped for GraphQL and chat flow:
        {
            "items": [...],
            "metadata": {...},
            "citations": [...],
        }
    """
    start_time = time.perf_counter()
    logger.info(
        "execute_query start",
        connector_id=connector_id,
        workspace_id=workspace_id,
        operation="execute_query",
    )

    # 1. Fetch connector configuration (with workspace_id for composite key)
    connector = registry_module.get_connector(connector_id, workspace_id)

    # Basic workspace guardrail
    if connector.get("workspace_id") != workspace_id:
        raise CommonError("Connector does not belong to this workspace")

    # 2. RBAC: ensure application is allowed to use this connector
    if application_id and application_id not in connector.get("application_ids", []):
        raise CommonError("Connector not enabled for this application")

    connector_type = connector.get("connector_type") or connector.get("type")
    if not connector_type:
        raise CommonError("Connector type is not configured")

    # 3. Intent classification if not explicitly provided
    if not intent:
        analysis = intent_module.classify_intent(
            user_prompt=user_prompt,
            connector_type=connector_type,
            schema=connector.get("schema_cache"),
        )
        intent = analysis["intent"]
        params = (params or {}) | (analysis.get("params") or {})
    else:
        params = params or {}

    # 4. Safety validation
    allowed_resources = connector.get("allowed_resources") or {}
    safety_module.validate_query(
        connector_type=connector_type,
        intent=intent,
        params=params,
        allowed_resources=allowed_resources,
    )

    try:
        # 5. Call MCP server (or stub)
        endpoint_cfg = connector.get("endpoint") or {}
        endpoint_url = endpoint_cfg.get("url")

        client = mcp_client_module.MCPClient(endpoint=endpoint_url)
        tool_result = client.call_tool(tool_name=intent, arguments=params)

        # 6. Normalize to Context Pack / QueryResult shape
        context_pack = _normalize_to_context_pack(tool_result, connector)
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "execute_query success",
            connector_id=connector_id,
            workspace_id=workspace_id,
            connector_type=connector_type,
            operation="execute_query",
            status="success",
            item_count=len(context_pack.items),
            duration_ms=round(duration_ms, 2),
        )
        metrics_module.put_connector_query_success(
            connector_type=connector_type,
            workspace_id=workspace_id,
        )
        metrics_module.put_connector_response_time_ms(
            connector_type=connector_type,
            workspace_id=workspace_id,
            duration_ms=duration_ms,
        )
        return {
            "items": context_pack.items,
            "metadata": context_pack.metadata,
            "citations": context_pack.citations,
        }
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_type = type(exc).__name__
        logger.warning(
            "execute_query failure",
            connector_id=connector_id,
            workspace_id=workspace_id,
            connector_type=connector_type,
            operation="execute_query",
            status="failure",
            error_type=error_type,
            error_message=str(exc),
            duration_ms=round(duration_ms, 2),
        )
        metrics_module.put_connector_query_failure(
            connector_type=connector_type,
            workspace_id=workspace_id,
            error_type=error_type,
        )
        raise


def test_connector(
    connector_id: str, workspace_id: Optional[str] = None
) -> Dict[str, Any]:
    """Lightweight health check for a connector.

    For Phase 4 this simply verifies that the connector exists and, if an
    endpoint URL is configured, attempts a 'health' tool call. When
    workspace_id is provided, the connector is fetched with composite key.
    """
    logger.info(
        "test_connector",
        connector_id=connector_id,
        workspace_id=workspace_id,
        operation="test_connector",
    )

    connector = registry_module.get_connector(connector_id, workspace_id)
    endpoint_cfg = connector.get("endpoint") or {}
    endpoint_url = endpoint_cfg.get("url")
    connector_type = connector.get("connector_type") or connector.get("type") or "unknown"

    client = mcp_client_module.MCPClient(endpoint=endpoint_url)

    status = "healthy"
    details: Optional[str] = None

    if endpoint_url:
        try:
            result = client.call_tool("health", {})
            details = str(result.get("raw_response"))
        except Exception as exc:  # noqa: BLE001
            status = "unhealthy"
            details = f"Health check failed: {exc}"
            logger.warning(
                "test_connector unhealthy",
                connector_id=connector_id,
                workspace_id=workspace_id,
                connector_type=connector_type,
                operation="test_connector",
                status="failure",
                error_message=str(exc),
            )
    else:
        details = "No endpoint configured; treating as stub connector"

    logger.info(
        "test_connector result",
        connector_id=connector_id,
        workspace_id=workspace_id,
        operation="test_connector",
        status=status,
    )
    return {
        "status": status,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_to_context_pack(tool_result: Dict[str, Any], connector: Dict[str, Any]) -> QueryResult:
    """Convert MCP tool result into a `QueryResult` / context pack.

    We expect the MCP server (or stub) to return something shaped like:
        {
            "items": [...],
            "metadata": {...},
            "citations": [...],
        }
    inside the `raw_response` field.
    """

    raw = tool_result.get("raw_response") or {}

    items = raw.get("items") or []
    metadata = raw.get("metadata") or {}
    citations = raw.get("citations") or []

    connector_id = connector.get("connector_id")
    connector_type = connector.get("connector_type") or connector.get("type")
    connector_name = connector.get("name") or connector_type or "connector"

    # Enrich metadata with connector information
    metadata = {
        **metadata,
        "connector_id": connector_id,
        "connector_type": connector_type,
        "connector_name": connector_name,
        "source": metadata.get("source") or "connector",
    }

    # Ensure items are a list of dicts with minimally expected keys; add per-item source attribution.
    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            item = {"content": str(item)}
        # Per-item source attribution for citations (Part 5)
        item = {
            **item,
            "connector_id": item.get("connector_id") or connector_id,
            "connector_type": item.get("connector_type") or connector_type,
            "connector_name": item.get("connector_name") or connector_name,
            "source": item.get("source") or connector_name,
            "source_url": item.get("source_url") or item.get("url") or "",
        }
        normalized_items.append(item)

    return QueryResult(
        items=normalized_items,
        metadata=metadata,
        citations=citations,
    )

