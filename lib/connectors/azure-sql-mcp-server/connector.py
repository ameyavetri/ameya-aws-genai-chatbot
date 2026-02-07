"""Azure SQL connector implementation with connection pooling and safety checks."""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
import pyodbc

from safety import SafetyError, validate_sql

logger = logging.getLogger(__name__)


class AzureSqlConnector:
    """Azure SQL connector with connection pooling and safety enforcement."""

    def __init__(self):
        """Initialize connector from environment variables."""
        self.connector_type = os.getenv("CONNECTOR_TYPE", "azure_sql")
        self.credentials_secret_arn = os.getenv("CREDENTIALS_SECRET_ARN")
        self.allowed_resources_json = os.getenv("ALLOWED_RESOURCES", "{}")
        self.region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

        # Parse allowed resources
        try:
            self.allowed_resources = json.loads(self.allowed_resources_json)
        except json.JSONDecodeError:
            logger.warning("Failed to parse ALLOWED_RESOURCES, using empty allowlist")
            self.allowed_resources = {}

        # Connection string cache
        self._connection_string: Optional[str] = None
        self._connection_string_lock = threading.Lock()

        # Connection pool (simple in-memory pool)
        self._pool: List[pyodbc.Connection] = []
        self._pool_lock = threading.Lock()
        self._max_pool_size = 5

        # Secrets Manager client
        self._secrets_client = boto3.client("secretsmanager", region_name=self.region)

    def _get_connection_string(self) -> str:
        """Get connection string from Secrets Manager, caching it in memory."""
        if self._connection_string:
            return self._connection_string

        with self._connection_string_lock:
            if self._connection_string:
                return self._connection_string

            if not self.credentials_secret_arn:
                raise ValueError("CREDENTIALS_SECRET_ARN environment variable is required")

            try:
                response = self._secrets_client.get_secret_value(SecretId=self.credentials_secret_arn)
                secret_value = response["SecretString"]

                # Parse JSON secret if needed
                try:
                    secret_dict = json.loads(secret_value)
                    # Support both direct connection string and dict format
                    if isinstance(secret_dict, dict):
                        # Build connection string from dict components
                        conn_str_parts = []
                        if "server" in secret_dict:
                            conn_str_parts.append(f"Server={secret_dict['server']}")
                        if "database" in secret_dict:
                            conn_str_parts.append(f"Database={secret_dict['database']}")
                        if "username" in secret_dict:
                            conn_str_parts.append(f"UID={secret_dict['username']}")
                        if "password" in secret_dict:
                            conn_str_parts.append(f"PWD={secret_dict['password']}")
                        if "driver" in secret_dict:
                            conn_str_parts.append(f"Driver={secret_dict['driver']}")
                        else:
                            conn_str_parts.append("Driver={ODBC Driver 18 for SQL Server}")
                        conn_str_parts.append("Encrypt=yes")
                        conn_str_parts.append("TrustServerCertificate=no")
                        self._connection_string = ";".join(conn_str_parts)
                    else:
                        self._connection_string = secret_value
                except json.JSONDecodeError:
                    # Assume it's a direct connection string
                    self._connection_string = secret_value

            except Exception as e:
                logger.error(f"Failed to retrieve secret: {e}", exc_info=True)
                raise

            return self._connection_string

    @contextmanager
    def _get_connection(self):
        """Get a connection from the pool or create a new one."""
        conn = None
        try:
            with self._pool_lock:
                if self._pool:
                    conn = self._pool.pop()
                else:
                    conn = pyodbc.connect(self._get_connection_string(), timeout=10)

            yield conn
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            raise
        finally:
            if conn:
                # Return to pool if not full
                with self._pool_lock:
                    if len(self._pool) < self._max_pool_size:
                        self._pool.append(conn)
                    else:
                        try:
                            conn.close()
                        except Exception:
                            pass

    def health(self) -> Dict[str, Any]:
        """Check connectivity to Azure SQL database.

        Returns:
            Dict with 'status' ('healthy' or 'unhealthy') and 'details'.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()

            return {
                "status": "healthy",
                "details": {
                    "connector_type": self.connector_type,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {
                "status": "unhealthy",
                "details": {
                    "connector_type": self.connector_type,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            }

    def discover_schema(self) -> Dict[str, Any]:
        """Discover schema metadata for allowed objects only.

        Returns:
            Dict with 'tables' and 'last_updated'.
        """
        from schema_discovery import discover_schema

        connection_string = self._get_connection_string()
        return discover_schema(connection_string, self.allowed_resources)

    def query(self, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a safe SQL query.

        Args:
            intent: Query intent (e.g., 'query_customers', 'query_orders').
            params: Query parameters including 'sql_template' or 'sql', and query params.

        Returns:
            Dict with 'items', 'metadata', and 'citations'.
        """
        # Get SQL template from params
        sql_template = params.get("sql_template") or params.get("sql") or ""
        if not sql_template:
            raise ValueError("sql_template or sql parameter is required")

        # Validate SQL safety
        try:
            validate_sql(sql_template, params, self.allowed_resources)
        except SafetyError as e:
            raise ValueError(f"SQL validation failed: {e}") from e

        # Get timeout and row cap
        timeout = (
            (self.allowed_resources.get("rate_limits") or {}).get("query_timeout_seconds") or 30
        )
        max_rows = (
            (self.allowed_resources.get("rate_limits") or {}).get("max_rows_per_query") or 1000
        )

        # Build parameterized query
        # For now, we'll use simple parameter substitution
        # In production, use proper parameterized queries with pyodbc
        sql = sql_template
        query_params = params.get("params", {})

        # Replace placeholders in SQL (simple approach - in production use proper parameterization)
        for key, value in query_params.items():
            placeholder = f"{{{key}}}"
            if placeholder in sql:
                # Escape single quotes for safety
                if isinstance(value, str):
                    value = value.replace("'", "''")
                    sql = sql.replace(placeholder, f"'{value}'")
                else:
                    sql = sql.replace(placeholder, str(value))

        # Execute query
        items = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, timeout=timeout)

                # Fetch rows (up to max_rows)
                columns = [column[0] for column in cursor.description] if cursor.description else []
                row_count = 0
                for row in cursor.fetchall():
                    if row_count >= max_rows:
                        break
                    items.append(dict(zip(columns, row)))
                    row_count += 1

                cursor.close()

        except Exception as e:
            logger.error(f"Query execution failed: {e}", exc_info=True)
            raise ValueError(f"Query execution failed: {e}") from e

        # Build citations
        citations = []
        if self.allowed_resources.get("schemas"):
            schema = self.allowed_resources["schemas"][0]
            citations.append(f"azure_sql://{schema}/...")

        return {
            "items": items,
            "metadata": {
                "source": "azure_sql",
                "row_count": len(items),
                "intent": intent,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            "citations": citations,
        }
