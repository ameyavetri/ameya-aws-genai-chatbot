from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from boto3.dynamodb.conditions import Key

from genai_core.types import CommonError


class ConnectorRegistry:
    """DynamoDB-backed registry for connector configurations.

    This is a light, production-shaped implementation that can be used in
    Lambda, but is also easy to mock in tests. It follows the schema described
    in MCP_CONNECTORS_ARCHITECTURE.md.
    """

    def __init__(self, table_name: str) -> None:
        if not table_name:
            raise ValueError("table_name is required for ConnectorRegistry")
        self._table = boto3.resource("dynamodb").Table(table_name)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_connector(self, workspace_id: str, connector_config: Dict[str, Any]) -> str:
        """Create a new connector record and return its connector_id."""

        connector_id = connector_config.get("connector_id") or f"conn-{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()

        item: Dict[str, Any] = {
            "connector_id": connector_id,
            "workspace_id": workspace_id,
            "created_at": connector_config.get("created_at", now),
            "updated_at": connector_config.get("updated_at", now),
            "status": connector_config.get("status", "active"),
        }
        item.update(connector_config)

        try:
            self._table.put_item(Item=item)
        except (BotoCoreError, ClientError) as exc:
            raise CommonError(f"Failed to create connector: {exc}") from exc

        return connector_id

    def get_connector(
        self, connector_id: str, workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get connector by ID, optionally scoped by workspace_id.

        Table has composite primary key (connector_id, workspace_id). When
        workspace_id is provided, get_item is used with both keys. When
        workspace_id is None, query by connector_id and the first item is
        returned (connector_id is expected to be unique per table).
        """
        try:
            if workspace_id is not None:
                response = self._table.get_item(
                    Key={"connector_id": connector_id, "workspace_id": workspace_id}
                )
                item = response.get("Item")
            else:
                response = self._table.query(
                    KeyConditionExpression=Key("connector_id").eq(connector_id),
                    Limit=1,
                )
                items = response.get("Items", [])
                item = items[0] if items else None

            if not item:
                raise CommonError(f"Connector not found: {connector_id}")
            return item
        except CommonError:
            raise
        except (BotoCoreError, ClientError) as exc:
            raise CommonError(f"Failed to get connector: {exc}") from exc

    def list_connectors(
        self, workspace_id: str, connector_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List connectors for a workspace, optionally filtered by type."""

        # Uses GSI `by_workspace` (workspace_id, connector_type)
        key_condition = "workspace_id = :ws"
        expr_values: Dict[str, Any] = {":ws": workspace_id}
        index_name = "by_workspace"

        if connector_type:
            key_condition += " AND connector_type = :type"
            expr_values[":type"] = connector_type

        try:
            response = self._table.query(
                IndexName=index_name,
                KeyConditionExpression=key_condition,  # type: ignore[arg-type]
                ExpressionAttributeValues=expr_values,
            )
        except (BotoCoreError, ClientError) as exc:
            raise CommonError(f"Failed to list connectors: {exc}") from exc

        return response.get("Items", [])

    def update_connector(
        self,
        connector_id: str,
        updates: Dict[str, Any],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update connector config and return the updated item.

        Table has composite primary key (connector_id, workspace_id). When
        workspace_id is provided, it is used in the key. When workspace_id
        is None, the connector is first fetched by query (connector_id only)
        and its workspace_id is used for the update.
        """
        if not updates:
            return self.get_connector(connector_id, workspace_id)

        key: Dict[str, str] = {"connector_id": connector_id}
        if workspace_id is not None:
            key["workspace_id"] = workspace_id
        else:
            existing = self.get_connector(connector_id)
            key["workspace_id"] = existing["workspace_id"]

        # Always bump updated_at
        updates = {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}

        update_expr_parts = []
        expr_attr_values: Dict[str, Any] = {}
        for idx, (k, value) in enumerate(updates.items()):
            placeholder = f":v{idx}"
            update_expr_parts.append(f"{k} = {placeholder}")
            expr_attr_values[placeholder] = value

        update_expr = "SET " + ", ".join(update_expr_parts)

        try:
            response = self._table.update_item(
                Key=key,
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues="ALL_NEW",
            )
        except (BotoCoreError, ClientError) as exc:
            raise CommonError(f"Failed to update connector: {exc}") from exc

        return response.get("Attributes", {})

    def delete_connector(
        self, connector_id: str, workspace_id: Optional[str] = None
    ) -> bool:
        """Soft-delete connector by marking status=inactive.

        When workspace_id is None, the connector is first fetched by query
        and its workspace_id is used for the update.
        """
        try:
            self.update_connector(
                connector_id, {"status": "inactive"}, workspace_id=workspace_id
            )
        except CommonError:
            # Surface deletion issues to caller as False rather than raising,
            # since this is often invoked from admin workflows.
            return False
        return True

    def get_connectors_for_application(
        self, workspace_id: str, application_id: str
    ) -> List[Dict[str, Any]]:
        """Return connectors enabled for a specific application."""

        connectors = self.list_connectors(workspace_id=workspace_id)
        return [
            c
            for c in connectors
            if application_id in c.get("application_ids", [])
            and c.get("status", "active") == "active"
        ]


def _default_registry() -> ConnectorRegistry:
    """Return a registry instance using the standard environment variable.

    This helper allows call sites to use module-level helpers during Phase 4
    without manually wiring the table name everywhere.
    """

    table_name = os.getenv("CONNECTORS_TABLE_NAME")
    if not table_name:
        raise CommonError("CONNECTORS_TABLE_NAME environment variable is not set")
    return ConnectorRegistry(table_name=table_name)


# Convenience module-level helpers used by early routes and orchestrator.
def create_connector(workspace_id: str, connector_config: Dict[str, Any]) -> str:
    return _default_registry().create_connector(workspace_id, connector_config)


def get_connector(
    connector_id: str, workspace_id: Optional[str] = None
) -> Dict[str, Any]:
    return _default_registry().get_connector(connector_id, workspace_id)


def list_connectors(
    workspace_id: str, connector_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    return _default_registry().list_connectors(workspace_id, connector_type)


def update_connector(
    connector_id: str,
    updates: Dict[str, Any],
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _default_registry().update_connector(
        connector_id, updates, workspace_id=workspace_id
    )


def delete_connector(
    connector_id: str, workspace_id: Optional[str] = None
) -> bool:
    return _default_registry().delete_connector(connector_id, workspace_id)


def get_connectors_for_application(
    workspace_id: str, application_id: str
) -> List[Dict[str, Any]]:
    return _default_registry().get_connectors_for_application(workspace_id, application_id)

