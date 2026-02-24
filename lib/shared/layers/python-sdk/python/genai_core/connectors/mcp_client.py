from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from genai_core.types import CommonError


@dataclass
class MCPClient:
    """Very small HTTP-based MCP client wrapper.

    Phase 4 behavior:
    - If `endpoint` is not provided, calls return a deterministic stub
      response that matches the expected structure.
    - When `endpoint` is provided, this class can be wired to a real MCP
      gateway in later phases without changing the call sites.
    """

    endpoint: Optional[str] = None
    timeout_seconds: int = 30

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call a remote MCP tool and return a normalized result dict.

        The normalized result is intentionally generic:
        {
            "tool_name": "...",
            "arguments": {...},
            "raw_response": ...,
        }
        The orchestrator will further normalize this into a `QueryResult`.
        """

        args = arguments or {}

        if not self.endpoint:
            # Stubbed response for Phase 4; useful for unit tests and local runs.
            return {
                "tool_name": tool_name,
                "arguments": args,
                "raw_response": {
                    "items": [],
                    "metadata": {"source": "mcp_stub", "row_count": 0},
                    "citations": [],
                },
            }

        try:
            response = requests.post(
                self.endpoint.rstrip("/") + "/tools/" + tool_name,
                json={"arguments": args},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise CommonError(f"MCP tool call failed: {exc}") from exc

        if not response.ok:
            raise CommonError(
                f"MCP tool call failed with status {response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise CommonError("Failed to parse MCP response as JSON") from exc

        return {
            "tool_name": tool_name,
            "arguments": args,
            "raw_response": payload,
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        """List tools exposed by the MCP server.

        In Phase 4, without a real MCP server, we return an empty list when
        no endpoint is configured.
        """

        if not self.endpoint:
            return []

        try:
            response = requests.get(
                self.endpoint.rstrip("/") + "/tools",
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise CommonError(f"MCP list_tools failed: {exc}") from exc

        if not response.ok:
            raise CommonError(
                f"MCP list_tools failed with status {response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise CommonError("Failed to parse MCP list_tools response as JSON") from exc

        # Expect a list-like payload; if not, wrap it conservatively.
        if isinstance(payload, list):
            return payload
        return [payload]

