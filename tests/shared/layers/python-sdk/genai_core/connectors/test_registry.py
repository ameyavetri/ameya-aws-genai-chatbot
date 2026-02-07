"""Unit tests for ConnectorRegistry CRUD operations."""

import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from genai_core.connectors.registry import ConnectorRegistry
from genai_core.types import CommonError


@pytest.fixture
def mock_table():
    """Mock DynamoDB table."""
    table = MagicMock()
    return table


@pytest.fixture
def registry(mock_table):
    """Create a ConnectorRegistry instance with mocked table."""
    with patch("genai_core.connectors.registry.boto3.resource") as mock_resource:
        mock_resource.return_value.Table.return_value = mock_table
        reg = ConnectorRegistry(table_name="test-connectors-table")
        reg._table = mock_table
        return reg


def test_create_connector(registry, mock_table):
    """Test creating a connector."""
    workspace_id = "ws-123"
    connector_config = {
        "connector_type": "azure_sql",
        "name": "Test Connector",
        "endpoint": {"url": "http://example.com"},
        "allowed_resources": {"schemas": ["dbo"], "tables": ["dbo.customers"]},
    }

    connector_id = registry.create_connector(workspace_id, connector_config)

    assert connector_id is not None
    assert connector_id.startswith("conn-")
    mock_table.put_item.assert_called_once()
    call_args = mock_table.put_item.call_args[1]["Item"]
    assert call_args["workspace_id"] == workspace_id
    assert call_args["connector_type"] == "azure_sql"
    assert call_args["status"] == "active"
    assert "created_at" in call_args
    assert "updated_at" in call_args


def test_create_connector_with_existing_id(registry, mock_table):
    """Test creating a connector with a provided connector_id."""
    workspace_id = "ws-123"
    connector_config = {
        "connector_id": "conn-custom-id",
        "connector_type": "azure_sql",
    }

    connector_id = registry.create_connector(workspace_id, connector_config)

    assert connector_id == "conn-custom-id"
    call_args = mock_table.put_item.call_args[1]["Item"]
    assert call_args["connector_id"] == "conn-custom-id"


def test_create_connector_dynamodb_error(registry, mock_table):
    """Test that DynamoDB errors are wrapped in CommonError."""
    workspace_id = "ws-123"
    connector_config = {"connector_type": "azure_sql"}

    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
        "PutItem",
    )

    with pytest.raises(CommonError) as exc_info:
        registry.create_connector(workspace_id, connector_config)

    assert "Failed to create connector" in str(exc_info.value)


def test_get_connector(registry, mock_table):
    """Test retrieving a connector by ID with workspace_id (composite key)."""
    connector_id = "conn-123"
    workspace_id = "ws-123"
    expected_item = {
        "connector_id": connector_id,
        "workspace_id": workspace_id,
        "connector_type": "azure_sql",
        "name": "Test Connector",
    }

    mock_table.get_item.return_value = {"Item": expected_item}

    result = registry.get_connector(connector_id, workspace_id)

    assert result == expected_item
    mock_table.get_item.assert_called_once_with(
        Key={"connector_id": connector_id, "workspace_id": workspace_id}
    )


def test_get_connector_not_found(registry, mock_table):
    """Test that missing connector raises CommonError."""
    connector_id = "conn-nonexistent"
    workspace_id = "ws-123"
    mock_table.get_item.return_value = {}

    with pytest.raises(CommonError) as exc_info:
        registry.get_connector(connector_id, workspace_id)

    assert "Connector not found" in str(exc_info.value)


def test_get_connector_dynamodb_error(registry, mock_table):
    """Test that DynamoDB errors are wrapped in CommonError."""
    connector_id = "conn-123"
    workspace_id = "ws-123"
    mock_table.get_item.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
        "GetItem",
    )

    with pytest.raises(CommonError) as exc_info:
        registry.get_connector(connector_id, workspace_id)

    assert "Failed to get connector" in str(exc_info.value)


def test_get_connector_without_workspace_id_uses_query(registry, mock_table):
    """Test that get_connector without workspace_id uses query and returns first item."""
    connector_id = "conn-123"
    expected_item = {
        "connector_id": connector_id,
        "workspace_id": "ws-123",
        "connector_type": "azure_sql",
    }
    mock_table.query.return_value = {"Items": [expected_item]}

    result = registry.get_connector(connector_id)

    assert result == expected_item
    mock_table.query.assert_called_once()
    call_kwargs = mock_table.query.call_args[1]
    assert "KeyConditionExpression" in call_kwargs
    assert call_kwargs.get("Limit") == 1


def test_get_connector_not_found_when_query_returns_empty(registry, mock_table):
    """Test that get_connector raises when workspace_id is None and query returns no items."""
    connector_id = "conn-nonexistent"
    mock_table.query.return_value = {"Items": []}

    with pytest.raises(CommonError) as exc_info:
        registry.get_connector(connector_id)

    assert "Connector not found" in str(exc_info.value)


def test_list_connectors(registry, mock_table):
    """Test listing connectors for a workspace."""
    workspace_id = "ws-123"
    expected_items = [
        {
            "connector_id": "conn-1",
            "workspace_id": workspace_id,
            "connector_type": "azure_sql",
        },
        {
            "connector_id": "conn-2",
            "workspace_id": workspace_id,
            "connector_type": "sharepoint",
        },
    ]

    mock_table.query.return_value = {"Items": expected_items}

    result = registry.list_connectors(workspace_id)

    assert result == expected_items
    mock_table.query.assert_called_once()
    call_kwargs = mock_table.query.call_args[1]
    assert call_kwargs["IndexName"] == "by_workspace"
    assert ":ws" in call_kwargs["ExpressionAttributeValues"]
    assert call_kwargs["ExpressionAttributeValues"][":ws"] == workspace_id


def test_list_connectors_filtered_by_type(registry, mock_table):
    """Test listing connectors filtered by connector_type."""
    workspace_id = "ws-123"
    connector_type = "azure_sql"
    expected_items = [
        {
            "connector_id": "conn-1",
            "workspace_id": workspace_id,
            "connector_type": connector_type,
        }
    ]

    mock_table.query.return_value = {"Items": expected_items}

    result = registry.list_connectors(workspace_id, connector_type=connector_type)

    assert result == expected_items
    call_kwargs = mock_table.query.call_args[1]
    assert ":type" in call_kwargs["ExpressionAttributeValues"]
    assert call_kwargs["ExpressionAttributeValues"][":type"] == connector_type


def test_list_connectors_empty(registry, mock_table):
    """Test listing connectors when none exist."""
    workspace_id = "ws-123"
    mock_table.query.return_value = {"Items": []}

    result = registry.list_connectors(workspace_id)

    assert result == []


def test_update_connector(registry, mock_table):
    """Test updating a connector with workspace_id (composite key)."""
    connector_id = "conn-123"
    workspace_id = "ws-123"
    updates = {
        "name": "Updated Name",
        "status": "active",
    }

    updated_item = {
        "connector_id": connector_id,
        "workspace_id": workspace_id,
        "name": "Updated Name",
        "status": "active",
        "updated_at": "2024-01-01T00:00:00Z",
    }

    mock_table.update_item.return_value = {"Attributes": updated_item}

    result = registry.update_connector(connector_id, updates, workspace_id=workspace_id)

    assert result == updated_item
    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args[1]
    assert call_kwargs["Key"]["connector_id"] == connector_id
    assert call_kwargs["Key"]["workspace_id"] == workspace_id
    assert "updated_at" in call_kwargs["ExpressionAttributeValues"].values()


def test_update_connector_empty_updates(registry, mock_table):
    """Test updating with empty updates calls get_connector with composite key."""
    connector_id = "conn-123"
    workspace_id = "ws-123"
    expected_item = {"connector_id": connector_id, "workspace_id": workspace_id}

    mock_table.get_item.return_value = {"Item": expected_item}

    result = registry.update_connector(connector_id, {}, workspace_id=workspace_id)

    assert result == expected_item
    mock_table.get_item.assert_called_once_with(
        Key={"connector_id": connector_id, "workspace_id": workspace_id}
    )


def test_update_connector_dynamodb_error(registry, mock_table):
    """Test that DynamoDB errors are wrapped in CommonError."""
    connector_id = "conn-123"
    workspace_id = "ws-123"
    updates = {"name": "Updated Name"}

    mock_table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
        "UpdateItem",
    )

    with pytest.raises(CommonError) as exc_info:
        registry.update_connector(connector_id, updates, workspace_id=workspace_id)

    assert "Failed to update connector" in str(exc_info.value)


def test_delete_connector(registry, mock_table):
    """Test deleting (soft-deleting) a connector with workspace_id (composite key)."""
    connector_id = "conn-123"
    workspace_id = "ws-123"
    updated_item = {
        "connector_id": connector_id,
        "workspace_id": workspace_id,
        "status": "inactive",
        "updated_at": "2024-01-01T00:00:00Z",
    }

    mock_table.update_item.return_value = {"Attributes": updated_item}

    result = registry.delete_connector(connector_id, workspace_id)

    assert result is True
    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args[1]
    assert call_kwargs["Key"]["connector_id"] == connector_id
    assert call_kwargs["Key"]["workspace_id"] == workspace_id
    expr_vals = call_kwargs["ExpressionAttributeValues"]
    assert "inactive" in expr_vals.values()


def test_delete_connector_error_returns_false(registry, mock_table):
    """Test that delete errors return False instead of raising."""
    connector_id = "conn-123"
    workspace_id = "ws-123"
    mock_table.update_item.side_effect = CommonError("Update failed")

    result = registry.delete_connector(connector_id, workspace_id)

    assert result is False


def test_get_connectors_for_application(registry, mock_table):
    """Test getting connectors enabled for an application."""
    workspace_id = "ws-123"
    application_id = "app-456"

    all_connectors = [
        {
            "connector_id": "conn-1",
            "workspace_id": workspace_id,
            "application_ids": [application_id],
            "status": "active",
        },
        {
            "connector_id": "conn-2",
            "workspace_id": workspace_id,
            "application_ids": ["app-other"],
            "status": "active",
        },
        {
            "connector_id": "conn-3",
            "workspace_id": workspace_id,
            "application_ids": [application_id],
            "status": "inactive",
        },
    ]

    mock_table.query.return_value = {"Items": all_connectors}

    result = registry.get_connectors_for_application(workspace_id, application_id)

    assert len(result) == 1
    assert result[0]["connector_id"] == "conn-1"
    assert result[0]["status"] == "active"


def test_get_connectors_for_application_no_matches(registry, mock_table):
    """Test getting connectors when none match the application."""
    workspace_id = "ws-123"
    application_id = "app-nonexistent"

    mock_table.query.return_value = {
        "Items": [
            {
                "connector_id": "conn-1",
                "workspace_id": workspace_id,
                "application_ids": ["app-other"],
                "status": "active",
            }
        ]
    }

    result = registry.get_connectors_for_application(workspace_id, application_id)

    assert result == []


def test_registry_init_requires_table_name():
    """Test that ConnectorRegistry requires a table name."""
    with pytest.raises(ValueError) as exc_info:
        ConnectorRegistry(table_name="")

    assert "table_name is required" in str(exc_info.value)
