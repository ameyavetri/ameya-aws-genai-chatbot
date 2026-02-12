"""
List folder and fetch file content for connector-backed file sources (Dropbox, SharePoint).
Used to treat Dropbox/SharePoint as equivalent to S3 for RAG ingestion.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import requests

from genai_core.types import CommonError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dropbox token resolution (supports access_token and refresh_token formats)
# ---------------------------------------------------------------------------


def _get_dropbox_access_token(creds: Dict[str, Any]) -> str:
    """Resolve a valid Dropbox access token from credentials.

    Supports two formats (backward compatible):
    1. New (recommended): {"app_key": "...", "app_secret": "...", "refresh_token": "..."}
       - Calls Dropbox OAuth2 token endpoint to obtain a fresh access_token.
    2. Legacy: {"access_token": "..."}
       - Uses the static token directly (deprecated; expires in ~4 hours).

    Raises CommonError if credentials are invalid or missing required fields.
    """
    if "refresh_token" in creds:
        app_key = creds.get("app_key")
        app_secret = creds.get("app_secret")
        refresh_token = creds.get("refresh_token")
        if not all([app_key, app_secret, refresh_token]):
            raise CommonError(
                "Dropbox refresh_token format requires app_key, app_secret, and refresh_token. "
                "All three must be present in the credentials JSON."
            )
        try:
            resp = requests.post(
                "https://api.dropbox.com/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": app_key,
                    "client_secret": app_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise CommonError("Dropbox token refresh did not return access_token")
            logger.info(
                "Dropbox client initialized with refresh token (auto-refresh succeeded)"
            )
            return token
        except requests.RequestException as e:
            status = None
            if hasattr(e, "response") and e.response is not None:
                status = e.response.status_code
            if status == 401:
                raise CommonError(
                    "Dropbox refresh token expired or invalid. "
                    "Re-authorize the app to obtain a new refresh_token and update the connector credentials."
                ) from e
            raise CommonError(f"Failed to refresh Dropbox token: {e}") from e
    # Legacy: static access_token
    token = creds.get("access_token")
    if not token:
        raise CommonError(
            "Dropbox credentials must include either access_token (legacy, expires in ~4h) "
            "or app_key, app_secret, and refresh_token (recommended, auto-refreshes)."
        )
    logger.warning(
        "Dropbox client initialized with static access_token (will expire in ~4 hours). "
        "Consider migrating to refresh_token format for automatic token refresh."
    )
    return token


def _get_connector_credentials(connector: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve connector credentials from Secrets Manager if ARN stored."""
    import boto3
    from botocore.exceptions import ClientError

    arn = connector.get("credentials_secret_arn")
    if not arn:
        raise CommonError("Connector has no credentials (credentials_secret_arn)")
    try:
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=arn)
        return json.loads(resp.get("SecretString", "{}"))
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "ResourceNotFoundException":
            raise CommonError(
                "Connector credentials secret not found in Secrets Manager. "
                "Re-create the connector in Admin → Connectors with valid credentials, or update the connector to use an existing secret ARN."
            ) from e
        raise CommonError(f"Failed to get connector credentials: {e}") from e
    except ValueError as e:
        raise CommonError(f"Failed to get connector credentials: {e}") from e


def list_folder(
    connector_id: str,
    workspace_id: str,
    path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List files and folders at the given path for a connector (Dropbox or SharePoint).
    Returns list of {"id", "name", "path", "type": "file"|"folder", "size" (optional)}.
    """
    from genai_core.connectors import registry as connector_registry

    connector = connector_registry.get_connector(connector_id, workspace_id)
    if not connector:
        raise CommonError("Connector not found")
    conn_type = (connector.get("connector_type") or connector.get("type") or "").lower()
    creds = _get_connector_credentials(connector)

    if conn_type == "dropbox":
        return _list_folder_dropbox(creds, path or "")
    if conn_type == "sharepoint":
        return _list_folder_sharepoint(creds, path, connector)
    raise CommonError(f"Connector type {conn_type} does not support list_folder")


def _list_folder_dropbox(creds: Dict[str, Any], path: str) -> List[Dict[str, Any]]:
    """List folder using Dropbox API v2."""
    token = _get_dropbox_access_token(creds)
    path = path or ""
    if path and not path.startswith("/"):
        path = "/" + path
    url = "https://api.dropboxapi.com/2/files/list_folder"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"path": path, "recursive": False}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        status = None
        detail = ""
        if hasattr(e, "response") and e.response is not None:
            status = e.response.status_code
            try:
                err_body = e.response.json()
                detail = str(err_body.get("error_summary", err_body.get("error", err_body)))
            except Exception:
                detail = (e.response.text or "")[:200]
        if status == 401:
            raise CommonError(
                "Dropbox token expired or invalid. If using access_token, consider migrating "
                "to refresh_token format (app_key, app_secret, refresh_token) for auto-refresh."
            ) from e
        if status == 400 and detail:
            raise CommonError(
                f"Dropbox list_folder 400 Bad Request: {detail}. "
                "For root folder use path=''. For Dropbox Business/team, you may need Dropbox-API-Path-Root header."
            ) from e
        raise CommonError(f"Dropbox list_folder failed: {e}") from e
    entries = data.get("entries", [])
    result = []
    for e in entries:
        tag = e.get(".tag", "file")
        is_folder = tag == "folder"
        name = e.get("name", "")
        item_path = e.get("path_display", path.rstrip("/") + "/" + name)
        size = e.get("size") if not is_folder else None
        result.append({
            "id": e.get("id", item_path),
            "name": name,
            "path": item_path,
            "type": "folder" if is_folder else "file",
            "size": size,
        })
    return result


def _list_folder_sharepoint(
    creds: Dict[str, Any], path: Optional[str], connector: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """List folder using Microsoft Graph API (SharePoint/OneDrive)."""
    import msal

    client_id = creds.get("clientId") or creds.get("client_id")
    client_secret = creds.get("clientSecret") or creds.get("client_secret")
    tenant_id = creds.get("tenantId") or creds.get("tenant_id")
    if not all([client_id, client_secret, tenant_id]):
        raise CommonError(
            "SharePoint credentials must include clientId, clientSecret, tenantId"
        )
    site_id = creds.get("siteId") or creds.get("site_id") or connector.get("site_id")
    drive_id = creds.get("driveId") or creds.get("drive_id") or connector.get("drive_id")
    if not drive_id:
        raise CommonError(
            "SharePoint connector must have driveId (or drive_id) in credentials or connector config"
        )

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    token_result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if not token_result.get("access_token"):
        raise CommonError("Failed to acquire Microsoft Graph token")
    access_token = token_result["access_token"]

    path = (path or "").strip().strip("/")
    if path:
        # If path looks like a Graph item id (no slashes, long), list by item id
        if "/" not in path and len(path) > 20:
            graph_path = f"/drives/{drive_id}/items/{path}/children"
        else:
            graph_path = f"/drives/{drive_id}/root:/{path}:/children"
    else:
        graph_path = f"/drives/{drive_id}/root/children"
    url = f"https://graph.microsoft.com/v1.0{graph_path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise CommonError(f"SharePoint list_folder failed: {e}") from e
    value = data.get("value", [])
    result = []
    for item in value:
        is_folder = item.get("folder") is not None
        name = item.get("name", "")
        item_id = item.get("id", "")
        size = item.get("size") if not is_folder else None
        result.append({
            "id": item_id,
            "name": name,
            "path": item_id,
            "type": "folder" if is_folder else "file",
            "size": size,
        })
    return result


def fetch_file_content(
    connector_id: str,
    workspace_id: str,
    file_path: str,
) -> bytes:
    """
    Fetch raw file content from the connector (Dropbox or SharePoint).
    Returns bytes. Caller decides decoding (e.g. UTF-8 for text) and extraction (e.g. PDF).
    """
    from genai_core.connectors import registry as connector_registry

    connector = connector_registry.get_connector(connector_id, workspace_id)
    if not connector:
        raise CommonError("Connector not found")
    conn_type = (connector.get("connector_type") or connector.get("type") or "").lower()
    creds = _get_connector_credentials(connector)

    if conn_type == "dropbox":
        return _fetch_file_dropbox(creds, file_path)
    if conn_type == "sharepoint":
        return _fetch_file_sharepoint(creds, file_path, connector)
    raise CommonError(f"Connector type {conn_type} does not support fetch_file_content")


def _fetch_file_dropbox(creds: Dict[str, Any], file_path: str) -> bytes:
    """Download file using Dropbox Content API."""
    token = _get_dropbox_access_token(creds)
    if file_path and not file_path.startswith("/"):
        file_path = "/" + file_path
    url = "https://content.dropboxapi.com/2/files/download"
    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps({"path": file_path}),
    }
    try:
        resp = requests.post(url, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        status = None
        if hasattr(e, "response") and e.response is not None:
            status = e.response.status_code
        if status == 401:
            raise CommonError(
                "Dropbox token expired or invalid. If using access_token, consider migrating "
                "to refresh_token format (app_key, app_secret, refresh_token) for auto-refresh."
            ) from e
        raise CommonError(f"Dropbox download failed: {e}") from e


def _fetch_file_sharepoint(
    creds: Dict[str, Any], file_path: str, connector: Dict[str, Any]
) -> bytes:
    """Download file using Microsoft Graph (file_path is item id or path)."""
    import msal

    client_id = creds.get("clientId") or creds.get("client_id")
    client_secret = creds.get("clientSecret") or creds.get("client_secret")
    tenant_id = creds.get("tenantId") or creds.get("tenant_id")
    if not all([client_id, client_secret, tenant_id]):
        raise CommonError(
            "SharePoint credentials must include clientId, clientSecret, tenantId"
        )
    drive_id = creds.get("driveId") or creds.get("drive_id") or connector.get("drive_id")
    if not drive_id:
        raise CommonError("SharePoint connector must have driveId")

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    token_result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if not token_result.get("access_token"):
        raise CommonError("Failed to acquire Microsoft Graph token")
    access_token = token_result["access_token"]

    # file_path can be Graph item id or path; if it looks like an id (no slashes or path), use items/{id}/content
    if "/" not in file_path and len(file_path) > 20:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_path}/content"
    else:
        path_enc = requests.utils.quote(file_path.strip("/"))
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{path_enc}:/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        raise CommonError(f"SharePoint download failed: {e}") from e
