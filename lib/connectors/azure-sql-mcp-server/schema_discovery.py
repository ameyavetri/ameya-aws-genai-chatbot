"""Schema discovery for Azure SQL connector.

Queries INFORMATION_SCHEMA to discover allowed schemas, tables, views, and columns.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pyodbc

logger = logging.getLogger(__name__)


def discover_schema(
    connection_string: str, allowed_resources: Dict[str, Any]
) -> Dict[str, Any]:
    """Discover schema metadata for allowed objects only.

    Args:
        connection_string: Azure SQL connection string.
        allowed_resources: Dict with 'schemas', 'tables', 'views' allowlists.

    Returns:
        Dict with 'tables' (list of table metadata) and 'last_updated' (ISO timestamp).
    """
    allowed_schemas = set((allowed_resources.get("schemas") or []))
    allowed_tables = set((allowed_resources.get("tables") or []))
    allowed_views = set((allowed_resources.get("views") or []))

    tables: List[Dict[str, Any]] = []

    try:
        conn = pyodbc.connect(connection_string, timeout=10)
        cursor = conn.cursor()

        # Build WHERE clause for allowed schemas
        schema_filter = ""
        if allowed_schemas:
            schema_placeholders = ",".join("?" * len(allowed_schemas))
            schema_filter = f"AND TABLE_SCHEMA IN ({schema_placeholders})"

        # Query for tables
        if allowed_tables or not allowed_tables:  # If allowlist is empty, allow all (for discovery)
            table_query = f"""
                SELECT 
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    TABLE_TYPE
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                {schema_filter}
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
            params = list(allowed_schemas) if allowed_schemas else []
            cursor.execute(table_query, params)

            for row in cursor.fetchall():
                schema, table_name, table_type = row
                fq_name = f"{schema}.{table_name}"

                # Check if table is in allowlist (if allowlist is non-empty)
                if allowed_tables and fq_name.upper() not in {t.upper() for t in allowed_tables}:
                    continue

                # Get columns for this table
                columns = _get_columns(cursor, schema, table_name)

                tables.append(
                    {
                        "name": table_name,
                        "schema": schema,
                        "type": table_type.lower(),
                        "columns": columns,
                    }
                )

        # Query for views
        if allowed_views or not allowed_views:
            view_query = f"""
                SELECT 
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    TABLE_TYPE
                FROM INFORMATION_SCHEMA.VIEWS
                {schema_filter}
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
            params = list(allowed_schemas) if allowed_schemas else []
            cursor.execute(view_query, params)

            for row in cursor.fetchall():
                schema, view_name, table_type = row
                fq_name = f"{schema}.{view_name}"

                # Check if view is in allowlist (if allowlist is non-empty)
                if allowed_views and fq_name.upper() not in {v.upper() for v in allowed_views}:
                    continue

                # Get columns for this view
                columns = _get_columns(cursor, schema, view_name)

                tables.append(
                    {
                        "name": view_name,
                        "schema": schema,
                        "type": "view",
                        "columns": columns,
                    }
                )

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"Schema discovery failed: {e}", exc_info=True)
        raise

    from datetime import datetime

    return {
        "tables": tables,
        "folders": [],  # Not applicable for SQL
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


def _get_columns(cursor: pyodbc.Cursor, schema: str, table_name: str) -> List[Dict[str, Any]]:
    """Get column metadata for a table or view.

    Args:
        cursor: Database cursor.
        schema: Schema name.
        table_name: Table or view name.

    Returns:
        List of column metadata dicts.
    """
    columns = []
    column_query = """
        SELECT 
            COLUMN_NAME,
            DATA_TYPE,
            IS_NULLABLE,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """
    cursor.execute(column_query, (schema, table_name))

    for row in cursor.fetchall():
        col_name, data_type, is_nullable, char_max_len, num_precision, num_scale = row
        columns.append(
            {
                "name": col_name,
                "type": data_type,
                "nullable": is_nullable == "YES",
                "max_length": char_max_len,
                "precision": num_precision,
                "scale": num_scale,
            }
        )

    return columns
