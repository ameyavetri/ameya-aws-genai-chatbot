"""Unit tests for MCPClient with mocked HTTP responses."""

import pytest
from unittest.mock import patch, MagicMock
import requests

from genai_core.connectors.mcp_client import MCPClient
from genai_core.types import CommonError


def test_mcp_client_stub_mode():
    """Test MCPClient in stub mode (no endpoint)."""
    client = MCPClient(endpoint=None)

    result = client.call_tool("test_tool", {"arg1": "value1"})

    assert result["tool_name"] == "test_tool"
    assert result["arguments"] == {"arg1": "value1"}
    assert "raw_response" in result
    assert result["raw_response"]["items"] == []
    assert result["raw_response"]["metadata"]["source"] == "mcp_stub"


def test_mcp_client_list_tools_stub_mode():
    """Test list_tools in stub mode."""
    client = MCPClient(endpoint=None)

    result = client.list_tools()

    assert result == []


@patch("genai_core.connectors.mcp_client.requests.post")
def test_mcp_client_call_tool_success(mock_post):
    """Test successful MCP tool call."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {
        "items": [{"id": 1, "name": "Item 1"}],
        "metadata": {"row_count": 1},
        "citations": ["source1"],
    }
    mock_post.return_value = mock_response

    result = client.call_tool("query_customers", {"filter": "active"})

    assert result["tool_name"] == "query_customers"
    assert result["arguments"] == {"filter": "active"}
    assert result["raw_response"]["items"] == [{"id": 1, "name": "Item 1"}]
    mock_post.assert_called_once_with(
        f"{endpoint}/tools/query_customers",
        json={"arguments": {"filter": "active"}},
        timeout=30,
    )


@patch("genai_core.connectors.mcp_client.requests.post")
def test_mcp_client_call_tool_custom_timeout(mock_post):
    """Test MCPClient with custom timeout."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint, timeout_seconds=60)

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"items": []}
    mock_post.return_value = mock_response

    client.call_tool("test_tool", {})

    mock_post.assert_called_once_with(
        f"{endpoint}/tools/test_tool",
        json={"arguments": {}},
        timeout=60,
    )


@patch("genai_core.connectors.mcp_client.requests.post")
def test_mcp_client_call_tool_http_error(mock_post):
    """Test MCP tool call with HTTP error."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response

    with pytest.raises(CommonError) as exc_info:
        client.call_tool("test_tool", {})

    assert "MCP tool call failed with status 500" in str(exc_info.value)


@patch("genai_core.connectors.mcp_client.requests.post")
def test_mcp_client_call_tool_request_exception(mock_post):
    """Test MCP tool call with network error."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_post.side_effect = requests.RequestException("Connection timeout")

    with pytest.raises(CommonError) as exc_info:
        client.call_tool("test_tool", {})

    assert "MCP tool call failed" in str(exc_info.value)


@patch("genai_core.connectors.mcp_client.requests.post")
def test_mcp_client_call_tool_invalid_json(mock_post):
    """Test MCP tool call with invalid JSON response."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_post.return_value = mock_response

    with pytest.raises(CommonError) as exc_info:
        client.call_tool("test_tool", {})

    assert "Failed to parse MCP response as JSON" in str(exc_info.value)


@patch("genai_core.connectors.mcp_client.requests.get")
def test_mcp_client_list_tools_success(mock_get):
    """Test successful list_tools call."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = [
        {"name": "tool1", "description": "Tool 1"},
        {"name": "tool2", "description": "Tool 2"},
    ]
    mock_get.return_value = mock_response

    result = client.list_tools()

    assert len(result) == 2
    assert result[0]["name"] == "tool1"
    mock_get.assert_called_once_with(f"{endpoint}/tools", timeout=30)


@patch("genai_core.connectors.mcp_client.requests.get")
def test_mcp_client_list_tools_non_list_response(mock_get):
    """Test list_tools with non-list response (wrapped)."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"name": "tool1"}  # Single dict instead of list
    mock_get.return_value = mock_response

    result = client.list_tools()

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["name"] == "tool1"


@patch("genai_core.connectors.mcp_client.requests.get")
def test_mcp_client_list_tools_http_error(mock_get):
    """Test list_tools with HTTP error."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    mock_get.return_value = mock_response

    with pytest.raises(CommonError) as exc_info:
        client.list_tools()

    assert "MCP list_tools failed with status 404" in str(exc_info.value)


@patch("genai_core.connectors.mcp_client.requests.get")
def test_mcp_client_list_tools_request_exception(mock_get):
    """Test list_tools with network error."""
    endpoint = "http://example.com/mcp"
    client = MCPClient(endpoint=endpoint)

    mock_get.side_effect = requests.RequestException("Connection timeout")

    with pytest.raises(CommonError) as exc_info:
        client.list_tools()

    assert "MCP list_tools failed" in str(exc_info.value)


@patch("genai_core.connectors.mcp_client.requests.post")
def test_mcp_client_endpoint_trailing_slash(mock_post):
    """Test that endpoint trailing slashes are handled correctly."""
    endpoint = "http://example.com/mcp/"
    client = MCPClient(endpoint=endpoint)

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"items": []}
    mock_post.return_value = mock_response

    client.call_tool("test_tool", {})

    # Should not have double slashes
    call_url = mock_post.call_args[0][0]
    assert "//tools" not in call_url
    assert call_url == "http://example.com/mcp/tools/test_tool"
