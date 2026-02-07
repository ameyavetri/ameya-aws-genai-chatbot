"""Dropbox MCP connector: list/search files and get file content.

Credentials are read from AWS Secrets Manager (CREDENTIALS_SECRET_ARN).
When not configured, health returns degraded and tools return placeholder messages.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DropboxConnector:
    """Dropbox connector with optional Secrets Manager credentials."""

    def __init__(self) -> None:
        self.connector_type = os.getenv("CONNECTOR_TYPE", "dropbox")
        self.credentials_secret_arn = os.getenv("CREDENTIALS_SECRET_ARN")
        self.region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self._access_token: str | None = None

    def _get_access_token(self) -> str | None:
        """Get Dropbox access token from Secrets Manager (cached)."""
        if self._access_token is not None:
            return self._access_token
        if not self.credentials_secret_arn:
            return None
        try:
            import boto3
            client = boto3.client("secretsmanager", region_name=self.region)
            resp = client.get_secret_value(SecretId=self.credentials_secret_arn)
            secret = json.loads(resp["SecretString"])
            self._access_token = secret.get("access_token") or secret.get("access_token_v2")
            return self._access_token
        except Exception as e:
            logger.warning("Failed to get Dropbox credentials: %s", e)
            return None

    def health(self) -> Dict[str, Any]:
        """Report health; healthy only when credentials are configured and valid."""
        token = self._get_access_token()
        if token:
            return {
                "status": "healthy",
                "details": {"connector_type": self.connector_type},
            }
        return {
            "status": "degraded",
            "details": {
                "connector_type": self.connector_type,
                "message": "Credentials not configured. Set CREDENTIALS_SECRET_ARN with Dropbox access_token.",
            },
        }

    def list_files(self, path: str = "") -> Dict[str, Any]:
        """List files in a Dropbox path. Stub until Dropbox API is wired."""
        if not self._get_access_token():
            return {
                "error": "Dropbox connector not configured",
                "message": "Set CREDENTIALS_SECRET_ARN with Dropbox access_token in Secrets Manager.",
                "files": [],
            }
        # TODO: Call Dropbox API files_list_folder when implementing full integration
        return {"path": path or "/", "files": [], "message": "Dropbox API integration pending."}

    def search_files(self, query: str) -> Dict[str, Any]:
        """Search files in Dropbox. Stub until Dropbox API is wired."""
        if not self._get_access_token():
            return {
                "error": "Dropbox connector not configured",
                "message": "Set CREDENTIALS_SECRET_ARN with Dropbox access_token.",
                "matches": [],
            }
        # TODO: Call Dropbox API files_search_v2 when implementing full integration
        return {"query": query, "matches": [], "message": "Dropbox API integration pending."}

    def get_file_content(self, path: str) -> Dict[str, Any]:
        """Get content of a file from Dropbox. Stub until Dropbox API is wired."""
        if not self._get_access_token():
            return {
                "error": "Dropbox connector not configured",
                "message": "Set CREDENTIALS_SECRET_ARN with Dropbox access_token.",
                "content": None,
            }
        # TODO: Call Dropbox API files_download when implementing full integration
        return {"path": path, "content": None, "message": "Dropbox API integration pending."}
