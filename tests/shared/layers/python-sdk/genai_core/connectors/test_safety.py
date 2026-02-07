"""Unit tests for connector safety validation."""

import pytest

from genai_core.connectors.safety import validate_query, validate_sql, DANGEROUS_KEYWORDS
from genai_core.types import CommonError


def test_validate_sql_empty_template():
    """Test that empty SQL template raises error."""
    with pytest.raises(CommonError) as exc_info:
        validate_sql("", {}, {})

    assert "SQL template is required" in str(exc_info.value)


def test_validate_sql_dangerous_keywords():
    """Test that dangerous keywords are blocked."""
    for keyword in DANGEROUS_KEYWORDS:
        sql = f"SELECT * FROM table; {keyword} TABLE test;"
        with pytest.raises(CommonError) as exc_info:
            validate_sql(sql, {}, {})

        assert f"Dangerous keyword '{keyword}'" in str(exc_info.value)


def test_validate_sql_dangerous_keywords_case_insensitive():
    """Test that dangerous keywords are detected case-insensitively."""
    # Test lowercase
    with pytest.raises(CommonError):
        validate_sql("DROP TABLE test", {}, {})

    # Test mixed case
    with pytest.raises(CommonError):
        validate_sql("DrOp TaBlE test", {}, {})

    # Test uppercase (already tested above)
    with pytest.raises(CommonError):
        validate_sql("DROP TABLE test", {}, {})


def test_validate_sql_dangerous_keywords_word_boundaries():
    """Test that keywords are matched on word boundaries."""
    # Should pass - "DROPPED" contains "DROP" but not as a keyword
    validate_sql("SELECT * FROM customers WHERE status = 'DROPPED' LIMIT 10", {}, {})

    # Should fail - "DROP" as a keyword
    with pytest.raises(CommonError):
        validate_sql("DROP TABLE test", {}, {})


def test_validate_sql_only_select_allowed():
    """Test that only SELECT queries are allowed."""
    # Valid SELECT
    validate_sql("SELECT * FROM customers LIMIT 10", {}, {})

    # Valid WITH ... SELECT
    validate_sql("WITH cte AS (SELECT * FROM customers) SELECT * FROM cte LIMIT 10", {}, {})

    # Invalid - UPDATE
    with pytest.raises(CommonError) as exc_info:
        validate_sql("UPDATE customers SET name = 'test'", {}, {})

    assert "Only SELECT queries" in str(exc_info.value)

    # Invalid - INSERT
    with pytest.raises(CommonError):
        validate_sql("INSERT INTO customers VALUES (1, 'test')", {}, {})

    # Invalid - starts with non-SELECT
    with pytest.raises(CommonError):
        validate_sql("CREATE TABLE test (id INT)", {}, {})


def test_validate_sql_limit_or_top_required():
    """Test that LIMIT or TOP clause is required."""
    # Valid with LIMIT
    validate_sql("SELECT * FROM customers LIMIT 10", {}, {})

    # Valid with TOP
    validate_sql("SELECT TOP 10 * FROM customers", {}, {})

    # Invalid - no LIMIT or TOP
    with pytest.raises(CommonError) as exc_info:
        validate_sql("SELECT * FROM customers", {}, {})

    assert "must include LIMIT or TOP clause" in str(exc_info.value)


def test_validate_sql_limit_in_subquery():
    """Test that LIMIT/TOP detection works in subqueries."""
    # Valid - LIMIT in outer query
    validate_sql("SELECT * FROM (SELECT * FROM customers) AS sub LIMIT 10", {}, {})

    # Valid - TOP in outer query
    validate_sql("SELECT TOP 10 * FROM (SELECT * FROM customers) AS sub", {}, {})

    # Invalid - LIMIT only in subquery, not outer
    with pytest.raises(CommonError):
        validate_sql("SELECT * FROM (SELECT * FROM customers LIMIT 10) AS sub", {}, {})


def test_validate_sql_row_limit_enforcement():
    """Test that row limits are enforced."""
    allowed_resources = {
        "rate_limits": {"max_rows_per_query": 100},
    }

    # Valid - within limit
    validate_sql("SELECT * FROM customers LIMIT 50", {}, allowed_resources)

    # Valid - at limit
    validate_sql("SELECT * FROM customers LIMIT 100", {}, allowed_resources)

    # Invalid - exceeds limit
    with pytest.raises(CommonError) as exc_info:
        validate_sql("SELECT * FROM customers LIMIT 101", {}, allowed_resources)

    assert "exceeds maximum" in str(exc_info.value)

    # Test with TOP
    with pytest.raises(CommonError):
        validate_sql("SELECT TOP 150 * FROM customers", {}, allowed_resources)


def test_validate_sql_row_limit_default():
    """Test default row limit of 1000."""
    # Valid - within default limit
    validate_sql("SELECT * FROM customers LIMIT 1000", {}, {})

    # Invalid - exceeds default limit
    with pytest.raises(CommonError):
        validate_sql("SELECT * FROM customers LIMIT 1001", {}, {})


def test_validate_sql_allowlist_schemas():
    """Test that schemas are validated against allowlist."""
    allowed_resources = {
        "schemas": ["dbo", "sales"],
    }

    # Valid - allowed schema
    validate_sql("SELECT * FROM dbo.customers LIMIT 10", {}, allowed_resources)

    # Invalid - disallowed schema
    with pytest.raises(CommonError) as exc_info:
        validate_sql("SELECT * FROM unauthorized.customers LIMIT 10", {}, allowed_resources)

    assert "Schema 'UNAUTHORIZED' is not allowed" in str(exc_info.value)


def test_validate_sql_allowlist_tables():
    """Test that tables are validated against allowlist."""
    allowed_resources = {
        "tables": ["dbo.customers", "dbo.orders"],
    }

    # Valid - allowed table
    validate_sql("SELECT * FROM dbo.customers LIMIT 10", {}, allowed_resources)

    # Invalid - disallowed table
    with pytest.raises(CommonError) as exc_info:
        validate_sql("SELECT * FROM dbo.unauthorized LIMIT 10", {}, allowed_resources)

    assert "Table or view 'DBO.UNAUTHORIZED' is not allowed" in str(exc_info.value)


def test_validate_sql_allowlist_views():
    """Test that views are validated against allowlist."""
    allowed_resources = {
        "views": ["dbo.customer_view"],
    }

    # Valid - allowed view
    validate_sql("SELECT * FROM dbo.customer_view LIMIT 10", {}, allowed_resources)

    # Invalid - disallowed view
    with pytest.raises(CommonError):
        validate_sql("SELECT * FROM dbo.unauthorized_view LIMIT 10", {}, allowed_resources)


def test_validate_sql_allowlist_bare_table_name():
    """Test allowlist with bare table names (no schema)."""
    allowed_resources = {
        "tables": ["customers", "orders"],
    }

    # Valid - bare table name
    validate_sql("SELECT * FROM customers LIMIT 10", {}, allowed_resources)

    # Invalid - disallowed bare table
    with pytest.raises(CommonError):
        validate_sql("SELECT * FROM unauthorized LIMIT 10", {}, allowed_resources)


def test_validate_sql_allowlist_case_insensitive():
    """Test that allowlist matching is case-insensitive."""
    allowed_resources = {
        "schemas": ["dbo"],
        "tables": ["dbo.Customers"],
    }

    # Valid - different case
    validate_sql("SELECT * FROM DBO.CUSTOMERS LIMIT 10", {}, allowed_resources)
    validate_sql("SELECT * FROM dbo.customers LIMIT 10", {}, allowed_resources)


def test_validate_sql_allowlist_empty_allowed():
    """Test that empty allowlists allow all (no restriction)."""
    allowed_resources = {
        "schemas": [],
        "tables": [],
    }

    # Should pass - no restrictions
    validate_sql("SELECT * FROM any_schema.any_table LIMIT 10", {}, allowed_resources)


def test_validate_sql_allowlist_missing_keys():
    """Test that missing allowlist keys don't cause errors."""
    allowed_resources = {}

    # Should pass - no restrictions when keys are missing
    validate_sql("SELECT * FROM any_table LIMIT 10", {}, allowed_resources)


def test_validate_sql_joins():
    """Test that JOIN clauses are validated."""
    allowed_resources = {
        "tables": ["dbo.customers", "dbo.orders"],
    }

    # Valid - both tables allowed
    validate_sql(
        "SELECT * FROM dbo.customers JOIN dbo.orders ON customers.id = orders.customer_id LIMIT 10",
        {},
        allowed_resources,
    )

    # Invalid - one table disallowed
    with pytest.raises(CommonError):
        validate_sql(
            "SELECT * FROM dbo.customers JOIN dbo.unauthorized ON customers.id = unauthorized.id LIMIT 10",
            {},
            allowed_resources,
        )


def test_validate_query_azure_sql():
    """Test validate_query dispatches to validate_sql for azure_sql."""
    params = {
        "sql_template": "SELECT * FROM customers LIMIT 10",
    }
    allowed_resources = {}

    # Should not raise
    validate_query("azure_sql", "query_customers", params, allowed_resources)


def test_validate_query_azure_sql_with_sql_key():
    """Test validate_query handles 'sql' key as well."""
    params = {
        "sql": "SELECT * FROM customers LIMIT 10",
    }
    allowed_resources = {}

    # Should not raise
    validate_query("azure_sql", "query_customers", params, allowed_resources)


def test_validate_query_azure_sql_empty_sql():
    """Test validate_query with empty SQL raises error."""
    params = {}
    allowed_resources = {}

    with pytest.raises(CommonError):
        validate_query("azure_sql", "query_customers", params, allowed_resources)


def test_validate_query_other_connector_types():
    """Test that non-SQL connector types are no-ops."""
    params = {"query": "search term"}
    allowed_resources = {}

    # Should not raise for non-SQL types
    validate_query("sharepoint", "search_documents", params, allowed_resources)
    validate_query("dropbox", "search_files", params, allowed_resources)
    validate_query("unknown_type", "generic_query", params, allowed_resources)
