from __future__ import annotations

import re
from typing import Any, Dict

from genai_core.types import CommonError


DANGEROUS_KEYWORDS = [
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "MERGE",
    "EXEC",
    "EXECUTE",
    "XP_CMDSHELL",
    "SP_",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "BACKUP",
    "RESTORE",
]


def validate_query(
    connector_type: str,
    intent: str,
    params: Dict[str, Any],
    allowed_resources: Dict[str, Any],
) -> None:
    """Dispatch safety validation based on connector type.

    For Phase 4 we only implement SQL-specific validation for azure_sql and
    keep other connector types as no-ops (to be expanded later).
    """

    if connector_type == "azure_sql":
        sql_template = params.get("sql_template") or params.get("sql") or ""
        validate_sql(sql_template=sql_template, params=params, allowed_resources=allowed_resources)


def validate_sql(sql_template: str, params: Dict[str, Any], allowed_resources: Dict[str, Any]) -> None:
    """Validate SQL text against a conservative safety policy.

    Enforces:
    - Block list of dangerous SQL keywords.
    - Only SELECT (or WITH ... SELECT ...) allowed.
    - All referenced schemas/tables/views must be in allowlist.
    - LIMIT/TOP must be present with a maximum row cap.
    """

    if not sql_template:
        raise CommonError("SQL template is required for azure_sql connectors")

    sql_upper = sql_template.upper()

    # 1. Block dangerous keywords
    for keyword in DANGEROUS_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", sql_upper):
            raise CommonError(f"Dangerous keyword '{keyword}' not allowed in SQL query")

    # 2. Only SELECT or CTEs that lead to SELECT
    stripped = sql_upper.lstrip()
    if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
        raise CommonError("Only SELECT queries (or WITH ... SELECT) are allowed")

    # 3. Ensure LIMIT or TOP appears
    has_limit = " LIMIT " in f" {sql_upper} "
    has_top = " TOP " in f" {sql_upper} "
    if not (has_limit or has_top):
        raise CommonError("Query must include LIMIT or TOP clause")

    # 4. Enforce max row cap if we can detect a numeric limit
    max_rows_allowed = (
        (allowed_resources.get("rate_limits") or {}).get("max_rows_per_query")  # type: ignore[union-attr]
        or 1000
    )
    limit_match = re.search(r"\bLIMIT\s+(\d+)", sql_upper)
    top_match = re.search(r"\bTOP\s+(\d+)", sql_upper)
    row_limit = None
    if limit_match:
        row_limit = int(limit_match.group(1))
    elif top_match:
        row_limit = int(top_match.group(1))

    if row_limit is not None and row_limit > max_rows_allowed:
        raise CommonError(
            f"Requested row limit {row_limit} exceeds maximum of {max_rows_allowed}"
        )

    # 5. Allowlist for schemas/tables/views.
    # This is implemented heuristically: extract tokens that look like
    # schema.table or single identifiers after FROM/JOIN.
    allowed_schemas = set((allowed_resources.get("schemas") or []))
    allowed_tables = set((allowed_resources.get("tables") or []))
    allowed_views = set((allowed_resources.get("views") or []))

    # FROM/JOIN <identifier> or <schema>.<identifier>
    table_refs = re.findall(
        r"\b(?:FROM|JOIN)\s+([A-Z0-9_]+\.[A-Z0-9_]+|[A-Z0-9_]+)",
        sql_upper,
    )

    for ref in table_refs:
        if "." in ref:
            # schema.table
            schema, table = ref.split(".", 1)
            if allowed_schemas and schema not in {s.upper() for s in allowed_schemas}:
                raise CommonError(f"Schema '{schema}' is not allowed")

            fq = f"{schema}.{table}"
            if allowed_tables and fq not in {t.upper() for t in allowed_tables}:
                # Also check views
                if allowed_views and fq not in {v.upper() for v in allowed_views}:
                    raise CommonError(f"Table or view '{fq}' is not allowed")
        else:
            # Bare table or view name
            if allowed_tables and ref not in {t.split(".")[-1].upper() for t in allowed_tables}:
                if allowed_views and ref not in {v.split(".")[-1].upper() for v in allowed_views}:
                    raise CommonError(f"Table or view '{ref}' is not allowed")

