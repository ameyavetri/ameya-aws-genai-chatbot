from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SchemaMetadata:
    """Schema discovery result for a connector.

    This is intentionally generic so it can represent both SQL- and
    document-oriented sources.
    """

    tables: List[Dict[str, Any]]
    folders: List[Dict[str, Any]]
    last_updated: str


@dataclass
class QueryResult:
    """Normalized query result returned by connectors and the orchestrator."""

    items: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    citations: List[str]


class BaseConnector(ABC):
    """Base interface all concrete connectors (MCP servers) should implement.

    NOTE: In Phase 4 this interface is not yet used directly by the Lambda
    layer, but it documents the contract implemented by MCP servers and
    shared code such as the Azure SQL connector.
    """

    @abstractmethod
    def discover_schema(self) -> SchemaMetadata:
        """Return schema metadata for context building."""

    @abstractmethod
    def query(self, intent: str, params: Dict[str, Any]) -> QueryResult:
        """Execute a safe query/action and return results."""

    @abstractmethod
    def search(
        self, query: str, filters: Optional[Dict[str, Any]] = None
    ) -> QueryResult:
        """Return relevant items/documents based on a search query."""

    @abstractmethod
    def get_item(self, item_id: str) -> Dict[str, Any]:
        """Fetch a single item/document by ID."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Connectivity check - should return a small diagnostic payload."""

    @abstractmethod
    def capabilities(self) -> List[Dict[str, Any]]:
        """List supported tools/actions for this connector."""

    def incremental_sync(self, checkpoint: Optional[str] = None) -> Dict[str, Any]:
        """Optional: for future index-first RAG mode.

        Returns:
            A dict such as:
            {
                "items": [...],
                "next_checkpoint": "...",
                "status": "complete" | "partial",
            }
        """

        raise NotImplementedError("Incremental sync not supported")

