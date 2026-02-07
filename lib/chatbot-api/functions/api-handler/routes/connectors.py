"""
Connector CRUD and testConnector API routes.

Part 2 (Backend API) + Part 7.1 (RBAC) + Part 7.2 (Secrets Manager).
Only admin or workspace_manager can manage connectors. Credentials are stored
in Secrets Manager; only the secret ARN is stored in the connector record.
API responses mask credentialsSecretArn.
"""

import os
import time
import uuid
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler.appsync import Router

from common.constant import (
    ID_FIELD_VALIDATION,
    SAFE_SHORT_STR_VALIDATION,
    SAFE_SHORT_STR_VALIDATION_OPTIONAL,
)
from genai_core.auth import UserPermissions
from genai_core.types import CommonError

tracer = Tracer()
router = Router()
logger = Logger()
permissions = UserPermissions(router)

# ARN pattern for Secrets Manager (allow colons and slashes)
ARN_REGEX = r"^[A-Za-z0-9-_.:/]*$"
ARN_VALIDATION_OPTIONAL = Field(
    min_length=0, max_length=512, pattern=ARN_REGEX, default=None
)

# Secret name prefix for app-created secrets (we delete these on connector delete)
CONNECTOR_SECRET_PREFIX = "genai-connector-"


def _connectors_available() -> bool:
    """Return True if CONNECTORS_TABLE_NAME is set (connectors feature enabled)."""
    return bool(os.environ.get("CONNECTORS_TABLE_NAME"))


def _ensure_connectors_available() -> None:
    if not _connectors_available():
        raise CommonError("Connectors are not enabled for this deployment")


# ---------------------------------------------------------------------------
# Secrets Manager (Part 7.2)
# ---------------------------------------------------------------------------


def _create_connector_secret(connector_id: str, credentials_json: str) -> str:
    """Create a secret in Secrets Manager; return the secret ARN."""
    name = f"{CONNECTOR_SECRET_PREFIX}{connector_id}"
    client = boto3.client("secretsmanager")
    try:
        response = client.create_secret(Name=name, SecretString=credentials_json)
        return response["ARN"]
    except ClientError as e:
        logger.exception("Failed to create connector secret", name=name)
        raise CommonError(f"Failed to create credentials secret: {e}") from e


def _update_connector_secret(secret_arn: str, credentials_json: str) -> None:
    """Update an existing secret's value."""
    client = boto3.client("secretsmanager")
    try:
        client.put_secret_value(SecretId=secret_arn, SecretString=credentials_json)
    except ClientError as e:
        logger.exception("Failed to update connector secret", secret_arn=secret_arn)
        raise CommonError(f"Failed to update credentials secret: {e}") from e


def _delete_connector_secret_if_owned(secret_arn: str) -> None:
    """
    Delete the secret only if we own it (Name starts with CONNECTOR_SECRET_PREFIX).
    Otherwise the client provided the ARN and we must not delete it.
    """
    if not secret_arn:
        return
    try:
        client = boto3.client("secretsmanager")
        desc = client.describe_secret(SecretId=secret_arn)
        name = desc.get("Name", "")
        if not name.startswith(CONNECTOR_SECRET_PREFIX):
            return
        client.delete_secret(SecretId=secret_arn, ForceDeleteWithoutRecovery=True)
    except ClientError as e:
        logger.warning(
            "Failed to delete connector secret (may already be deleted)", error=str(e)
        )


def _describe_secret_arn(secret_arn: str) -> bool:
    """Return True if the secret exists (for validation)."""
    try:
        boto3.client("secretsmanager").describe_secret(SecretId=secret_arn)
        return True
    except ClientError:
        return False


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


class CreateConnectorInput(BaseModel):
    workspaceId: str = ID_FIELD_VALIDATION
    name: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9-_\s]+$")
    type: str = SAFE_SHORT_STR_VALIDATION
    endpoint: Optional[Dict[str, Any]] = None
    credentialsSecretArn: Optional[str] = ARN_VALIDATION_OPTIONAL
    credentials: Optional[str] = None  # JSON string when creating new secret
    applicationIds: Optional[List[str]] = None
    allowedResources: Optional[Dict[str, Any]] = None


class UpdateConnectorInput(BaseModel):
    connectorId: str = ID_FIELD_VALIDATION
    workspaceId: str = ID_FIELD_VALIDATION
    name: Optional[str] = Field(None, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9-_\s]+$")
    type: Optional[str] = SAFE_SHORT_STR_VALIDATION_OPTIONAL
    endpoint: Optional[Dict[str, Any]] = None
    credentialsSecretArn: Optional[str] = ARN_VALIDATION_OPTIONAL
    credentials: Optional[str] = None
    applicationIds: Optional[List[str]] = None
    allowedResources: Optional[Dict[str, Any]] = None
    status: Optional[str] = SAFE_SHORT_STR_VALIDATION_OPTIONAL


class TestConnectorInput(BaseModel):
    connectorId: str = ID_FIELD_VALIDATION
    workspaceId: str = ID_FIELD_VALIDATION


# ---------------------------------------------------------------------------
# GraphQL <-> Registry shape conversion
# ---------------------------------------------------------------------------


def _to_registry_allowed_resources(allowed_resources: Optional[Dict]) -> Optional[Dict]:
    if not allowed_resources:
        return None
    out = {}
    if "schemas" in allowed_resources:
        out["schemas"] = allowed_resources["schemas"]
    if "tables" in allowed_resources:
        out["tables"] = allowed_resources["tables"]
    if "views" in allowed_resources:
        out["views"] = allowed_resources["views"]
    if "rateLimits" in allowed_resources:
        rl = allowed_resources["rateLimits"] or {}
        out["rate_limits"] = {}
        if "maxRowsPerQuery" in rl:
            out["rate_limits"]["max_rows_per_query"] = rl["maxRowsPerQuery"]
    return out if out else None


def _to_graphql_connector(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert registry item to GraphQL Connector shape; mask credentialsSecretArn."""
    endpoint = item.get("endpoint")
    if isinstance(endpoint, dict):
        endpoint = {"type": endpoint.get("type"), "url": endpoint.get("url")}
    allowed = item.get("allowed_resources") or {}
    allowed_resources = None
    if allowed:
        allowed_resources = {
            "schemas": allowed.get("schemas"),
            "tables": allowed.get("tables"),
            "views": allowed.get("views"),
            "rateLimits": None,
        }
        if allowed.get("rate_limits"):
            allowed_resources["rateLimits"] = {
                "maxRowsPerQuery": allowed["rate_limits"].get("max_rows_per_query")
            }
    return {
        "id": item.get("connector_id"),
        "workspaceId": item.get("workspace_id"),
        "name": item.get("name", ""),
        "type": item.get("connector_type") or item.get("type", ""),
        "status": item.get("status"),
        "endpoint": endpoint,
        "credentialsSecretArn": None,  # Masked in API response
        "applicationIds": item.get("application_ids"),
        "allowedResources": allowed_resources,
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Resolvers (Part 2 + Part 7.1 RBAC)
# ---------------------------------------------------------------------------


@router.resolver(field_name="listConnectors")
@tracer.capture_method
@permissions.approved_roles(
    [permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE]
)
def list_connectors(workspaceId: str, connectorType: Optional[str] = None):
    start_ms = time.perf_counter()
    logger.info(
        "connector operation",
        operation="listConnectors",
        workspace_id=workspaceId,
    )
    _ensure_connectors_available()
    from genai_core.connectors import registry as connector_registry

    items = connector_registry.list_connectors(workspaceId, connector_type=connectorType)
    duration_ms = (time.perf_counter() - start_ms) * 1000
    logger.info(
        "connector operation complete",
        operation="listConnectors",
        workspace_id=workspaceId,
        status="success",
        duration_ms=round(duration_ms, 2),
    )
    return [_to_graphql_connector(c) for c in items]


@router.resolver(field_name="getConnector")
@tracer.capture_method
@permissions.approved_roles(
    [permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE]
)
def get_connector(connectorId: str, workspaceId: str):
    start_ms = time.perf_counter()
    logger.info(
        "connector operation",
        operation="getConnector",
        workspace_id=workspaceId,
        connector_id=connectorId,
    )
    _ensure_connectors_available()
    from genai_core.connectors import registry as connector_registry

    item = connector_registry.get_connector(connectorId, workspaceId)
    duration_ms = (time.perf_counter() - start_ms) * 1000
    logger.info(
        "connector operation complete",
        operation="getConnector",
        workspace_id=workspaceId,
        connector_id=connectorId,
        status="success",
        duration_ms=round(duration_ms, 2),
    )
    return _to_graphql_connector(item)


@router.resolver(field_name="createConnector")
@tracer.capture_method
@permissions.approved_roles(
    [permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE]
)
def create_connector(input: dict):
    start_ms = time.perf_counter()
    req = CreateConnectorInput(**input)
    workspace_id = req.workspaceId
    logger.info(
        "connector operation",
        operation="createConnector",
        workspace_id=workspace_id,
    )
    _ensure_connectors_available()
    from genai_core.connectors import registry as connector_registry

    credentials_secret_arn: Optional[str] = None

    if req.credentials and req.credentialsSecretArn:
        raise CommonError("Provide either credentials or credentialsSecretArn, not both")
    if req.credentials:
        connector_id = f"conn-{uuid.uuid4().hex}"
        credentials_secret_arn = _create_connector_secret(connector_id, req.credentials)
    elif req.credentialsSecretArn:
        if not _describe_secret_arn(req.credentialsSecretArn):
            raise CommonError("credentialsSecretArn does not exist or is not accessible")
        credentials_secret_arn = req.credentialsSecretArn
        connector_id = None  # let registry generate
    else:
        raise CommonError("Provide either credentials or credentialsSecretArn")

    connector_config: Dict[str, Any] = {
        "connector_type": req.type,
        "name": req.name,
        "status": "active",
        "credentials_secret_arn": credentials_secret_arn,
        "application_ids": req.applicationIds or [],
        "allowed_resources": _to_registry_allowed_resources(req.allowedResources) or {},
    }
    if connector_id is not None:
        connector_config["connector_id"] = connector_id
    if req.endpoint:
        connector_config["endpoint"] = {
            "type": req.endpoint.get("type"),
            "url": req.endpoint.get("url"),
        }

    created_id = connector_registry.create_connector(workspace_id, connector_config)
    item = connector_registry.get_connector(created_id, workspace_id)
    duration_ms = (time.perf_counter() - start_ms) * 1000
    logger.info(
        "connector operation complete",
        operation="createConnector",
        workspace_id=workspace_id,
        connector_id=created_id,
        status="success",
        duration_ms=round(duration_ms, 2),
    )
    return _to_graphql_connector(item)


@router.resolver(field_name="updateConnector")
@tracer.capture_method
@permissions.approved_roles(
    [permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE]
)
def update_connector(input: dict):
    start_ms = time.perf_counter()
    req = UpdateConnectorInput(**input)
    connector_id = req.connectorId
    workspace_id = req.workspaceId
    logger.info(
        "connector operation",
        operation="updateConnector",
        workspace_id=workspace_id,
        connector_id=connector_id,
    )
    _ensure_connectors_available()
    from genai_core.connectors import registry as connector_registry

    existing = connector_registry.get_connector(connector_id, workspace_id)
    updates: Dict[str, Any] = {}

    if req.name is not None:
        updates["name"] = req.name
    if req.type is not None:
        updates["connector_type"] = req.type
    if req.endpoint is not None:
        updates["endpoint"] = {"type": req.endpoint.get("type"), "url": req.endpoint.get("url")}
    if req.applicationIds is not None:
        updates["application_ids"] = req.applicationIds
    if req.allowedResources is not None:
        updates["allowed_resources"] = _to_registry_allowed_resources(req.allowedResources) or {}
    if req.status is not None:
        updates["status"] = req.status
    if req.credentialsSecretArn is not None:
        if not _describe_secret_arn(req.credentialsSecretArn):
            raise CommonError("credentialsSecretArn does not exist or is not accessible")
        updates["credentials_secret_arn"] = req.credentialsSecretArn
    if req.credentials is not None:
        secret_arn = existing.get("credentials_secret_arn")
        if not secret_arn:
            raise CommonError("Connector has no credentials secret to update")
        _update_connector_secret(secret_arn, req.credentials)

    if not updates:
        duration_ms = (time.perf_counter() - start_ms) * 1000
        logger.info(
            "connector operation complete",
            operation="updateConnector",
            workspace_id=workspace_id,
            connector_id=connector_id,
            status="success",
            duration_ms=round(duration_ms, 2),
        )
        return _to_graphql_connector(existing)

    updated = connector_registry.update_connector(
        connector_id, updates, workspace_id=workspace_id
    )
    duration_ms = (time.perf_counter() - start_ms) * 1000
    logger.info(
        "connector operation complete",
        operation="updateConnector",
        workspace_id=workspace_id,
        connector_id=connector_id,
        status="success",
        duration_ms=round(duration_ms, 2),
    )
    return _to_graphql_connector(updated)


@router.resolver(field_name="deleteConnector")
@tracer.capture_method
@permissions.approved_roles(
    [permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE]
)
def delete_connector(connectorId: str, workspaceId: str):
    start_ms = time.perf_counter()
    logger.info(
        "connector operation",
        operation="deleteConnector",
        workspace_id=workspaceId,
        connector_id=connectorId,
    )
    _ensure_connectors_available()
    from genai_core.connectors import registry as connector_registry

    existing = connector_registry.get_connector(connectorId, workspaceId)
    secret_arn = existing.get("credentials_secret_arn")
    if secret_arn:
        _delete_connector_secret_if_owned(secret_arn)
    ok = connector_registry.delete_connector(connectorId, workspace_id=workspaceId)
    duration_ms = (time.perf_counter() - start_ms) * 1000
    logger.info(
        "connector operation complete",
        operation="deleteConnector",
        workspace_id=workspaceId,
        connector_id=connectorId,
        status="success",
        duration_ms=round(duration_ms, 2),
    )
    return ok


@router.resolver(field_name="testConnector")
@tracer.capture_method
@permissions.approved_roles(
    [permissions.ADMIN_ROLE, permissions.WORKSPACES_MANAGER_ROLE]
)
def test_connector(input: dict):
    start_ms = time.perf_counter()
    req = TestConnectorInput(**input)
    connector_id = req.connectorId
    workspace_id = req.workspaceId
    logger.info(
        "connector operation",
        operation="testConnector",
        workspace_id=workspace_id,
        connector_id=connector_id,
    )
    _ensure_connectors_available()
    from genai_core.connectors import orchestrator as connector_orchestrator

    result = connector_orchestrator.test_connector(
        req.connectorId, workspace_id=req.workspaceId
    )
    duration_ms = (time.perf_counter() - start_ms) * 1000
    status = result.get("status", "unknown")
    logger.info(
        "connector operation complete",
        operation="testConnector",
        workspace_id=workspace_id,
        connector_id=connector_id,
        status="success",
        health_status=status,
        duration_ms=round(duration_ms, 2),
    )
    return {
        "status": status,
        "details": result.get("details"),
        "timestamp": result.get("timestamp"),
    }
