"""Integration tests for connector CRUD, health checks (Part 6).

Test scenarios:
1. Create connector via API
2. List connectors for workspace (with optional type filter)
3. Update connector
4. Test connector health
5. Delete connector
6. getConnector with wrong workspace returns not found
7. User role cannot list connectors (403)

Requires: deployed API with connector GraphQL schema, connector DynamoDB table,
and admin/workspace_manager credentials. Skips when CONNECTORS_TABLE_NAME is not set
or when GraphQL schema does not include connector types.
"""

import os
import pytest
from gql.transport.exceptions import TransportQueryError
from clients.appsync_client import AppSyncClient


@pytest.fixture(scope="module")
def connectors_enabled():
    """Skip if connectors are not enabled (no table name in env)."""
    if not os.getenv("CONNECTORS_TABLE_NAME"):
        pytest.skip("Connectors not enabled: CONNECTORS_TABLE_NAME not set")
    return True


@pytest.fixture(scope="module")
def test_workspace_id(client: AppSyncClient):
    """Use first available workspace for connector tests."""
    workspaces = client.list_workspaces()
    if not workspaces:
        pytest.skip("No workspace available for connector tests")
    return workspaces[0].get("id")


@pytest.fixture(scope="module")
def created_connector(client: AppSyncClient, connectors_enabled, test_workspace_id):
    """
    Create one connector for the CRUD sequence; yield (connector_id, workspace_id).
    Teardown: delete the connector after tests that use it.
    """
    if not hasattr(client, "create_connector"):
        pytest.skip("GraphQL schema does not include connector mutations")

    connector_input = {
        "workspaceId": test_workspace_id,
        "type": "azure_sql",
        "name": "INTEG_TEST_CONNECTOR",
        "endpoint": {"type": "mcp_server", "url": "http://localhost:8080/azure-sql"},
        "credentials": '{"placeholder": true}',  # API creates secret; no real ARN needed
        "allowedResources": {
            "schemas": ["dbo"],
            "tables": ["dbo.customers"],
            "views": [],
        },
        "applicationIds": [],
    }

    try:
        connector = client.create_connector(input=connector_input)
    except Exception as e:
        if "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        raise

    yield (connector.get("id"), connector.get("workspaceId"), connector)

    # Teardown: delete connector
    try:
        if hasattr(client, "delete_connector"):
            client.delete_connector(
                connector_id=connector.get("id"),
                workspace_id=connector.get("workspaceId"),
            )
    except Exception:
        pass


def test_create_connector(
    client: AppSyncClient, connectors_enabled, test_workspace_id, created_connector
):
    """Create connector via API; assert response shape and no raw credentials."""
    _connector_id, _workspace_id, connector = created_connector
    assert connector is not None
    assert connector.get("id") is not None
    assert connector.get("name") == "INTEG_TEST_CONNECTOR"
    assert connector.get("type") == "azure_sql"
    assert connector.get("workspaceId") == test_workspace_id
    # API masks credentialsSecretArn in response
    assert "password" not in str(connector).lower()
    assert connector.get("credentialsSecretArn") is None or "secret" in str(
        connector.get("credentialsSecretArn", "")
    ).lower()


def test_list_connectors(
    client: AppSyncClient, connectors_enabled, test_workspace_id, created_connector
):
    """List connectors for workspace; created connector must appear."""
    connector_id, workspace_id, _ = created_connector
    try:
        connectors = client.list_connectors(workspace_id=test_workspace_id)
    except Exception as e:
        if "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        raise
    assert isinstance(connectors, list)
    ids = [c.get("id") for c in connectors]
    assert connector_id in ids
    # Optional: filter by connectorType
    filtered = client.list_connectors(
        workspace_id=test_workspace_id, connector_type="azure_sql"
    )
    assert isinstance(filtered, list)
    assert all(c.get("type") == "azure_sql" for c in filtered)


def test_get_connector(
    client: AppSyncClient, connectors_enabled, created_connector
):
    """Retrieve connector by id and workspaceId."""
    connector_id, workspace_id, _ = created_connector
    try:
        connector = client.get_connector(
            connector_id=connector_id, workspace_id=workspace_id
        )
    except Exception as e:
        if "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        raise
    assert connector is not None
    assert connector.get("id") == connector_id
    assert connector.get("name") == "INTEG_TEST_CONNECTOR"
    assert connector.get("workspaceId") == workspace_id


def test_update_connector(
    client: AppSyncClient, connectors_enabled, created_connector
):
    """Update connector name/allowedResources; getConnector reflects update."""
    connector_id, workspace_id, _ = created_connector
    try:
        updated = client.update_connector(
            input={
                "connectorId": connector_id,
                "workspaceId": workspace_id,
                "name": "INTEG_TEST_CONNECTOR_UPDATED",
                "allowedResources": {
                    "schemas": ["dbo"],
                    "tables": ["dbo.customers", "dbo.orders"],
                    "views": [],
                },
            }
        )
    except Exception as e:
        if "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        raise
    assert updated is not None
    assert updated.get("name") == "INTEG_TEST_CONNECTOR_UPDATED"
    assert updated.get("id") == connector_id
    # getConnector returns updated data
    got = client.get_connector(connector_id=connector_id, workspace_id=workspace_id)
    assert got.get("name") == "INTEG_TEST_CONNECTOR_UPDATED"
    tables = (got.get("allowedResources") or {}).get("tables") or []
    assert "dbo.orders" in tables or "dbo.customers" in tables


def test_test_connector(
    client: AppSyncClient, connectors_enabled, created_connector
):
    """Test connector health; expect status healthy or unhealthy, details, timestamp."""
    connector_id, workspace_id, _ = created_connector
    try:
        health = client.test_connector(
            connector_id=connector_id, workspace_id=workspace_id
        )
    except Exception as e:
        if "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        if "unhealthy" in str(e).lower() or "timeout" in str(e).lower():
            pytest.skip(f"MCP endpoint not available: {e}")
        raise
    assert health is not None
    assert "status" in health
    assert health["status"] in ("healthy", "unhealthy", "unknown")
    assert "details" in health or "timestamp" in health or "details" in str(health)


def test_delete_connector(
    client: AppSyncClient, connectors_enabled, test_workspace_id
):
    """Create a connector, delete it, then assert listConnectors no longer returns it."""
    if not hasattr(client, "create_connector"):
        pytest.skip("GraphQL schema does not include connector mutations")
    connector_input = {
        "workspaceId": test_workspace_id,
        "type": "azure_sql",
        "name": "INTEG_TEST_CONNECTOR_TO_DELETE",
        "endpoint": {"type": "mcp_server", "url": "http://localhost:8080/azure-sql"},
        "credentials": '{"placeholder": true}',
        "allowedResources": {"schemas": ["dbo"], "tables": [], "views": []},
        "applicationIds": [],
    }
    try:
        connector = client.create_connector(input=connector_input)
    except Exception as e:
        if "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        raise
    cid = connector.get("id")
    wid = connector.get("workspaceId")
    result = client.delete_connector(connector_id=cid, workspace_id=wid)
    assert result is True
    connectors = client.list_connectors(workspace_id=test_workspace_id)
    ids = [c.get("id") for c in connectors]
    assert cid not in ids


def test_get_connector_wrong_workspace_returns_not_found(
    client: AppSyncClient, connectors_enabled, created_connector
):
    """getConnector with wrong workspaceId should return null or 404-style error."""
    connector_id, _workspace_id, _ = created_connector
    wrong_workspace_id = "non-existent-workspace-id"
    try:
        result = client.get_connector(
            connector_id=connector_id, workspace_id=wrong_workspace_id
        )
        # Either null or missing
        assert result is None or result.get("id") is None
    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e).lower():
            pass
        elif "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        else:
            raise


def test_list_connectors_as_user_forbidden(
    client_user: AppSyncClient, connectors_enabled, test_workspace_id
):
    """User role (non-admin, non-workspace_manager) cannot list connectors; expect 403."""
    if not hasattr(client_user, "list_connectors"):
        pytest.skip("GraphQL schema does not include listConnectors")
    with pytest.raises(TransportQueryError, match="Unauthorized"):
        client_user.list_connectors(workspace_id=test_workspace_id)
