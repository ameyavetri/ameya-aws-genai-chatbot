from __future__ import annotations

from typing import Any, Dict

from genai_core.types import CommonError


def validate_query(
    connector_type: str,
    intent: str,
    params: Dict[str, Any],
    allowed_resources: Dict[str, Any],
) -> None:
    """Dispatch safety validation based on connector type.

    Currently a no-op for all connector types.
    Extend this function to add validation for specific connector types.
    """
    pass
