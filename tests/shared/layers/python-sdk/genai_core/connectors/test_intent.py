"""Unit tests for connector intent classification."""

import pytest

from genai_core.connectors.intent import classify_intent, detect_connector_intent


def test_classify_intent_azure_sql_customers():
    """Test intent classification for Azure SQL customer queries."""
    result = classify_intent("Show me all customers", "azure_sql", None)

    assert result["intent"] == "query_customers"
    assert isinstance(result["params"], dict)


def test_classify_intent_azure_sql_orders():
    """Test intent classification for Azure SQL order queries."""
    result = classify_intent("Get orders from last month", "azure_sql", None)

    assert result["intent"] == "query_orders"
    assert isinstance(result["params"], dict)


def test_classify_intent_azure_sql_generic():
    """Test intent classification for generic Azure SQL queries."""
    result = classify_intent("What data do we have?", "azure_sql", None)

    assert result["intent"] == "query_sql"
    assert isinstance(result["params"], dict)


def test_classify_intent_azure_sql_timeframe_last_month():
    """Test timeframe parameter extraction."""
    result = classify_intent("Show customers from last month", "azure_sql", None)

    assert result["intent"] == "query_customers"
    assert result["params"].get("timeframe") == "last_month"


def test_classify_intent_azure_sql_timeframe_last_year():
    """Test last year timeframe extraction."""
    result = classify_intent("Orders from last year", "azure_sql", None)

    assert result["intent"] == "query_orders"
    assert result["params"].get("timeframe") == "last_year"


def test_classify_intent_azure_sql_with_schema():
    """Test intent classification with schema metadata."""
    schema = {
        "tables": [
            {"name": "customers", "columns": ["id", "name"]},
        ],
    }

    result = classify_intent("Get some data", "azure_sql", schema)

    assert result["intent"] == "query_sql"
    # Should default to first table if available
    assert result["params"].get("table") == "customers"


def test_classify_intent_sharepoint():
    """Test intent classification for SharePoint."""
    result = classify_intent("Search for documents about project X", "sharepoint", None)

    assert result["intent"] == "search_documents"
    assert result["params"]["query"] == "Search for documents about project X"


def test_classify_intent_dropbox():
    """Test intent classification for Dropbox."""
    result = classify_intent("Find files in my folder", "dropbox", None)

    assert result["intent"] == "search_documents"
    assert result["params"]["query"] == "Find files in my folder"


def test_classify_intent_unknown_type():
    """Test intent classification for unknown connector type."""
    result = classify_intent("Some query", "unknown_type", None)

    assert result["intent"] == "generic_query"
    assert result["params"]["query"] == "Some query"


def test_classify_intent_case_insensitive():
    """Test that intent classification is case-insensitive."""
    result1 = classify_intent("CUSTOMERS", "azure_sql", None)
    result2 = classify_intent("customers", "azure_sql", None)
    result3 = classify_intent("Customers", "azure_sql", None)

    assert result1["intent"] == result2["intent"] == result3["intent"] == "query_customers"


def test_detect_connector_intent_needs_connector():
    """Test detect_connector_intent identifies connector needs."""
    keywords = ["database", "sql", "table", "spreadsheet", "sharepoint", "dropbox"]

    for keyword in keywords:
        result = detect_connector_intent(f"Show me data from {keyword}")

        assert result["needs_connector"] is True
        assert result["connector_id"] is None  # Not auto-selected in Phase 4


def test_detect_connector_intent_no_connector_needed():
    """Test detect_connector_intent when no connector is needed."""
    result = detect_connector_intent("What is the weather today?")

    assert result["needs_connector"] is False
    assert result["connector_id"] is None
    assert result["intent"] is None
    assert result["params"] is None


def test_detect_connector_intent_customers():
    """Test detect_connector_intent identifies customer queries."""
    result = detect_connector_intent("Show me customers from the database")

    assert result["needs_connector"] is True
    assert result["intent"] == "query_customers"
    assert result["params"]["raw_prompt"] == "show me customers from the database"


def test_detect_connector_intent_orders():
    """Test detect_connector_intent identifies order queries."""
    result = detect_connector_intent("Get orders from SQL table")

    assert result["needs_connector"] is True
    assert result["intent"] == "query_orders"
    assert result["params"]["raw_prompt"] == "get orders from sql table"


def test_detect_connector_intent_generic():
    """Test detect_connector_intent defaults to generic for database queries."""
    result = detect_connector_intent("Query the database for some data")

    assert result["needs_connector"] is True
    assert result["intent"] == "generic_query"
    assert result["params"]["raw_prompt"] == "query the database for some data"


def test_detect_connector_intent_case_insensitive():
    """Test that detect_connector_intent is case-insensitive."""
    result1 = detect_connector_intent("DATABASE")
    result2 = detect_connector_intent("database")
    result3 = detect_connector_intent("Database")

    assert result1["needs_connector"] == result2["needs_connector"] == result3["needs_connector"]


def test_detect_connector_intent_customer_plural():
    """Test that customer pluralization is handled."""
    result1 = detect_connector_intent("Show customers")
    result2 = detect_connector_intent("Show customer")

    assert result1["intent"] == "query_customers"
    assert result2["intent"] == "query_customers"


def test_detect_connector_intent_order_plural():
    """Test that order pluralization is handled."""
    result1 = detect_connector_intent("Get orders")
    result2 = detect_connector_intent("Get order")

    assert result1["intent"] == "query_orders"
    assert result2["intent"] == "query_orders"


def test_classify_intent_schema_multiple_tables():
    """Test intent classification with multiple tables in schema."""
    schema = {
        "tables": [
            {"name": "customers", "columns": ["id", "name"]},
            {"name": "orders", "columns": ["id", "customer_id"]},
        ],
    }

    result = classify_intent("Get some data", "azure_sql", schema)

    # Should default to first table
    assert result["params"].get("table") == "customers"


def test_classify_intent_schema_no_tables():
    """Test intent classification with empty schema."""
    schema = {"tables": []}

    result = classify_intent("Get some data", "azure_sql", schema)

    assert result["intent"] == "query_sql"
    assert "table" not in result["params"]
