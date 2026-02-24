"""
Part 10: CloudWatch metrics for connector usage.

Namespace: GenAIChatbot/Connectors
Metrics: ConnectorQuerySuccess, ConnectorQueryFailure, ConnectorContextUsed, ConnectorResponseTime
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

CONNECTOR_NAMESPACE = "GenAIChatbot/Connectors"


def _dims(**kwargs: str) -> List[Dict[str, str]]:
    return [{"Name": k, "Value": str(v)} for k, v in kwargs.items() if v is not None]


def _put_metric(
    name: str,
    value: float,
    unit: str = "Count",
    dimensions: Optional[List[Dict[str, str]]] = None,
) -> None:
    try:
        import boto3

        cw = boto3.client("cloudwatch")
        entry: Dict[str, Any] = {
            "MetricName": name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.now(timezone.utc),
        }
        if dimensions:
            entry["Dimensions"] = dimensions
        cw.put_metric_data(
            Namespace=CONNECTOR_NAMESPACE,
            MetricData=[entry],
        )
    except Exception:  # noqa: S110
        pass  # Do not fail the request if metrics fail


def put_connector_query_success(
    connector_type: str,
    workspace_id: str,
) -> None:
    _put_metric(
        "ConnectorQuerySuccess",
        1.0,
        dimensions=_dims(connector_type=connector_type, workspace_id=workspace_id),
    )


def put_connector_query_failure(
    connector_type: str,
    workspace_id: str,
    error_type: str = "unknown",
) -> None:
    _put_metric(
        "ConnectorQueryFailure",
        1.0,
        dimensions=_dims(
            connector_type=connector_type,
            workspace_id=workspace_id,
            error_type=error_type,
        ),
    )


def put_connector_response_time_ms(
    connector_type: str,
    workspace_id: str,
    duration_ms: float,
) -> None:
    _put_metric(
        "ConnectorResponseTime",
        duration_ms,
        unit="Milliseconds",
        dimensions=_dims(connector_type=connector_type, workspace_id=workspace_id),
    )


def put_connector_context_used(workspace_id: str) -> None:
    _put_metric(
        "ConnectorContextUsed",
        1.0,
        dimensions=_dims(workspace_id=workspace_id),
    )
