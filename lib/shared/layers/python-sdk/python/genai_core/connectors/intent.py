from __future__ import annotations

import re
from typing import Any, Dict, Optional


def classify_intent(
    user_prompt: str,
    connector_type: str,
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify user intent for a specific connector type.

    Phase 4 uses a simple rule-based approach that is intentionally conservative.
    It returns:
        {"intent": str, "params": dict}
    """

    prompt = user_prompt.lower()
    intent = "generic_query"
    params: Dict[str, Any] = {}

    if connector_type == "azure_sql":
        if "customer" in prompt:
            intent = "query_customers"
        elif "order" in prompt:
            intent = "query_orders"
        else:
            intent = "query_sql"

        # Very small heuristic to guess time-based filters
        if "last month" in prompt:
            params["timeframe"] = "last_month"
        if "last year" in prompt:
            params["timeframe"] = "last_year"

    elif connector_type in {"sharepoint", "dropbox"}:
        intent = "search_documents"
        params["query"] = user_prompt

    else:
        # Fallback for unknown types
        intent = "generic_query"
        params["query"] = user_prompt

    # Optionally use schema to add hints (non-breaking stub for now)
    if schema and isinstance(schema, dict):
        tables = schema.get("tables") or []
        if tables and "table" not in params:
            # If a single table is present, default to that.
            first = tables[0]
            if isinstance(first, dict) and "name" in first:
                params["table"] = first["name"]

    return {"intent": intent, "params": params}


def detect_connector_intent(prompt: str) -> Dict[str, Any]:
    """Detect whether a prompt likely requires a connector.

    Returns a dict shaped for the chat flow:
        {
            "needs_connector": bool,
            "connector_id": Optional[str],
            "intent": Optional[str],
            "params": Optional[dict],
        }

    Phase 4 keeps this very lightweight: it only checks for obviously
    structured data questions. The chat flow is expected to combine this
    with registry metadata to select a specific connector.
    """

    text = prompt.lower()

    needs_connector = any(
        keyword in text
        for keyword in [
            "database",
            "sql",
            "table",
            "spreadsheet",
            "sharepoint",
            "dropbox",
        ]
    )

    # No automatic connector_id selection in this phase – that requires
    # workspace-specific configuration. We leave it to the caller.
    result: Dict[str, Any] = {
        "needs_connector": needs_connector,
        "connector_id": None,
        "intent": None,
        "params": None,
    }

    if not needs_connector:
        return result

    # Very small heuristic to guess intent-ish label
    if re.search(r"\bcustomer(s)?\b", text):
        result["intent"] = "query_customers"
    elif re.search(r"\border(s)?\b", text):
        result["intent"] = "query_orders"
    else:
        result["intent"] = "generic_query"

    # Parameters are left for orchestrator/classify_intent to refine.
    result["params"] = {"raw_prompt": prompt}

    return result

