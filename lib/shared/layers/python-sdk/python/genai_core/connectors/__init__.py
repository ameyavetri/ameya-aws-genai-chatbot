"""
genai_core.connectors
~~~~~~~~~~~~~~~~~~~~~

Orchestration layer for external data source connectors accessed via MCP.

This package provides:
- A common connector interface and result types (`base`).
- A registry abstraction over the connectors DynamoDB table (`registry`).
- An MCP client wrapper used by Lambda functions (`mcp_client`).
- Safety and intent helpers (`safety`, `intent`).
- High-level orchestration helpers for executing connector queries (`orchestrator`).

Phase 4 note:
The implementations here are intentionally minimal and safe stubs that focus on
type shapes and orchestration flow rather than full production behavior. They
are designed to be extended in later phases without breaking the public API.
"""

from .base import BaseConnector, QueryResult, SchemaMetadata
from . import intent, mcp_client, orchestrator, registry, safety

__all__ = [
    "BaseConnector",
    "QueryResult",
    "SchemaMetadata",
    "intent",
    "mcp_client",
    "orchestrator",
    "registry",
    "safety",
]

