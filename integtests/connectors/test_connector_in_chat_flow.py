"""Integration tests for connector context in chat flow (Part 6).

Verifies:
- Chat with connector: response received; optional connector_sources/citations in metadata.
- Chat without connector trigger: normal response (backward compatibility).
- Connector failure does not break chat (fail-safe).
"""

import json
import os
import pytest
import time
import uuid
from clients.appsync_client import AppSyncClient


@pytest.fixture(scope="module")
def connectors_enabled():
    """Skip if connectors are not enabled."""
    if not os.getenv("CONNECTORS_TABLE_NAME"):
        pytest.skip("Connectors not enabled: CONNECTORS_TABLE_NAME not set")
    return True


@pytest.fixture(scope="module")
def test_workspace_id(client: AppSyncClient):
    """First available workspace."""
    workspaces = client.list_workspaces()
    if not workspaces:
        pytest.skip("No workspace available for connector tests")
    return workspaces[0].get("id")


@pytest.fixture(scope="module")
def test_application(client: AppSyncClient, test_workspace_id):
    """Application in test workspace for chat (create if needed)."""
    for app in client.list_applications():
        if app.get("workspace") == test_workspace_id:
            return app
    try:
        return client.create_application(
            input={
                "name": "INTEG_TEST_CONNECTOR_APP",
                "model": "bedrock::anthropic.claude-3-haiku-20240307-v1:0",
                "workspace": test_workspace_id,
                "roles": ["user"],
            }
        )
    except Exception as e:
        pytest.skip(f"Could not create test application: {e}")


@pytest.fixture(scope="module")
def test_connector(
    client: AppSyncClient, connectors_enabled, test_workspace_id, test_application
):
    """Create a connector for chat flow tests; delete in teardown."""
    if not hasattr(client, "create_connector"):
        pytest.skip("GraphQL schema does not include connector mutations")
    connector_input = {
        "workspaceId": test_workspace_id,
        "type": "azure_sql",
        "name": "CHAT_FLOW_TEST_CONNECTOR",
        "endpoint": {"type": "mcp_server", "url": "http://localhost:8080/azure-sql"},
        "credentials": '{"placeholder": true}',
        "allowedResources": {"schemas": ["dbo"], "tables": ["dbo.customers"], "views": []},
        "applicationIds": [test_application.get("id")],
    }
    try:
        connector = client.create_connector(input=connector_input)
    except Exception as e:
        if "connector" in str(e).lower() or "unknown field" in str(e).lower():
            pytest.skip(f"Connector schema not available: {e}")
        raise
    yield connector
    try:
        client.delete_connector(
            connector_id=connector.get("id"),
            workspace_id=connector.get("workspaceId"),
        )
    except Exception:
        pass


def test_chat_with_connector_context(
    client: AppSyncClient, connectors_enabled, test_connector, test_application
):
    """Chat with a prompt that may trigger connector; assert response and optional citations."""
    session_id = str(uuid.uuid4())
    request = {
        "action": "run",
        "modelInterface": "langchain",
        "applicationId": test_application.get("id"),
        "data": {
            "mode": "chain",
            "text": "Show me customers from the database",
            "images": [],
            "documents": [],
            "videos": [],
            "sessionId": session_id,
        },
    }
    try:
        client.send_query(json.dumps(request))
    except Exception as e:
        if "connector" in str(e).lower() and "not available" in str(e).lower():
            pytest.skip(f"Connector not available: {e}")
        raise

    found = False
    session = None
    for _ in range(10):
        time.sleep(2)
        try:
            session = client.get_session(session_id)
            if session and len(session.get("history", [])) > 1:
                found = True
                break
        except Exception:
            continue
    try:
        client.delete_session(session_id)
    except Exception:
        pass

    assert found, "Chat response not received"
    assert session is not None
    assert len(session.get("history", [])) > 0

    last_message = session.get("history", [])[-1]
    content = (last_message.get("content") or "").lower()
    assert len(content) > 0, "Empty chat response"

    # Optional: metadata may include connector_sources / connector_citations (Part 5)
    metadata = last_message.get("metadata") or {}
    if metadata.get("connector_sources") or metadata.get("connector_citations"):
        assert isinstance(metadata.get("connector_sources"), list) or isinstance(
            metadata.get("connector_citations"), list
        )


def test_chat_without_connector_trigger(client: AppSyncClient, test_application):
    """Normal chat without connector; backward compatibility."""
    session_id = str(uuid.uuid4())
    request = {
        "action": "run",
        "modelInterface": "langchain",
        "applicationId": test_application.get("id"),
        "data": {
            "mode": "chain",
            "text": "What is the capital of France?",
            "images": [],
            "documents": [],
            "videos": [],
            "sessionId": session_id,
        },
    }
    client.send_query(json.dumps(request))

    found = False
    session = None
    for _ in range(10):
        time.sleep(2)
        try:
            session = client.get_session(session_id)
            if session and len(session.get("history", [])) > 1:
                found = True
                break
        except Exception:
            continue
    try:
        client.delete_session(session_id)
    except Exception:
        pass

    assert found, "Chat response not received"
    assert session is not None
    assert len(session.get("history", [])) > 0
    content = (session.get("history", [])[-1].get("content") or "")
    assert len(content) > 0, "Empty chat response"


def test_connector_failure_does_not_break_chat(
    client: AppSyncClient, connectors_enabled, test_connector, test_application
):
    """If connector is unavailable, chat still returns a response (fail-safe)."""
    session_id = str(uuid.uuid4())
    request = {
        "action": "run",
        "modelInterface": "langchain",
        "applicationId": test_application.get("id"),
        "data": {
            "mode": "chain",
            "text": "Query the database for customer information",
            "images": [],
            "documents": [],
            "videos": [],
            "sessionId": session_id,
        },
    }
    client.send_query(json.dumps(request))

    found = False
    session = None
    for _ in range(10):
        time.sleep(2)
        try:
            session = client.get_session(session_id)
            if session and len(session.get("history", [])) > 1:
                found = True
                break
        except Exception:
            continue
    try:
        client.delete_session(session_id)
    except Exception:
        pass

    assert found, "Chat should respond even when connector fails"
    assert session is not None
    assert len(session.get("history", [])) > 0
    content = (session.get("history", [])[-1].get("content") or "")
    assert len(content) > 0, "Chat response should not be empty even if connector fails"
