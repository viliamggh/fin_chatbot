"""
Database operations for Azure SQL Server connection.

Phase 6: Production-grade enhancements with validation, timeouts, and retry logic.
"""

import os
import pyodbc
import json
import time
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Query timeout in seconds
QUERY_TIMEOUT = 30

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1  # Initial delay in seconds


def validate_sql_query(query: str) -> tuple[bool, str]:
    """
    Validate SQL query for safety.

    Args:
        query: SQL query string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    query_upper = query.strip().upper()

    # Must be a SELECT query
    if not query_upper.startswith("SELECT"):
        return False, "Only SELECT queries are allowed"

    # Dangerous keywords that should not appear
    dangerous_keywords = [
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE",
        "TRUNCATE", "EXEC", "EXECUTE", "sp_"
    ]

    for keyword in dangerous_keywords:
        if keyword in query_upper:
            return False, f"Query contains forbidden keyword: {keyword}"

    return True, ""


def get_connection() -> pyodbc.Connection:
    """
    Create and return a connection to Azure SQL Database with timeout.

    Returns:
        pyodbc.Connection: Active database connection

    Raises:
        pyodbc.Error: If connection fails
    """
    server = os.environ["AZURE_SQL_SERVER"]
    database = os.environ["AZURE_SQL_DATABASE"]
    username = os.environ["SQL_USERNAME"]
    password = os.environ["SQL_PASSWORD"]

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout={QUERY_TIMEOUT};"
    )

    return pyodbc.connect(conn_str)


def get_table_names() -> list[str]:
    """
    Get list of all table names in the database.

    Returns:
        List of table names
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = 'dbo'
    ORDER BY TABLE_NAME
    """

    cursor.execute(query)
    tables = [row.TABLE_NAME for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return tables


def get_table_schema(table_name: Optional[str] = None) -> str:
    """
    Get schema information for tables.

    Args:
        table_name: Specific table name, or None for all tables

    Returns:
        Formatted string with schema information
    """
    conn = get_connection()
    cursor = conn.cursor()

    if table_name:
        query = """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """
        cursor.execute(query, (table_name,))
    else:
        query = """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
        cursor.execute(query)

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        return f"No schema information found for table: {table_name}" if table_name else "No tables found"

    # Format schema information
    schema_info = []
    current_table = None

    for row in rows:
        if row.TABLE_NAME != current_table:
            current_table = row.TABLE_NAME
            schema_info.append(f"\nTable: {current_table}")

        nullable = "NULL" if row.IS_NULLABLE == "YES" else "NOT NULL"
        schema_info.append(f"  - {row.COLUMN_NAME}: {row.DATA_TYPE} ({nullable})")

    return "\n".join(schema_info)


def get_sample_data(table_name: str, limit: int = 3) -> str:
    """
    Get sample data from a table.

    Args:
        table_name: Name of the table
        limit: Number of sample rows to return

    Returns:
        Formatted string with sample data or error message
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Use TOP for SQL Server
        query = f"SELECT TOP {limit} * FROM {table_name}"
        cursor.execute(query)

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        if not rows:
            return f"Table {table_name} is empty"

        # Format sample data
        sample_lines = [f"\nSample data from {table_name}:"]
        for row in rows:
            row_dict = {}
            for i, column in enumerate(columns):
                value = row[i]
                # Convert date/datetime to string
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                # Convert Decimal to float
                elif hasattr(value, '__float__'):
                    value = float(value)
                row_dict[column] = value
            sample_lines.append(f"  {json.dumps(row_dict, ensure_ascii=False)}")

        return "\n".join(sample_lines)

    except Exception as e:
        logger.error(f"Error getting sample data from {table_name}: {e}")
        return f"Could not retrieve sample data from {table_name}"


def execute_sql_query(query: str, retry: bool = True) -> str:
    """
    Execute a SQL query and return results as JSON with validation, timeout, and retry logic.

    Args:
        query: SQL query string to execute
        retry: Whether to retry on transient failures

    Returns:
        JSON string with query results or error message

    Note:
        Only SELECT queries are allowed for safety.
    """
    # Validate query before execution
    is_valid, error_msg = validate_sql_query(query)
    if not is_valid:
        logger.warning(f"Query validation failed: {error_msg}")
        return json.dumps({
            "error": error_msg,
            "query": query
        })

    # Execute with retry logic
    last_error = None
    for attempt in range(MAX_RETRIES if retry else 1):
        try:
            logger.info(f"Executing query (attempt {attempt + 1}/{MAX_RETRIES if retry else 1})")

            conn = get_connection()
            cursor = conn.cursor()

            # Set query timeout
            cursor.execute(f"SET LOCK_TIMEOUT {QUERY_TIMEOUT * 1000}")  # milliseconds

            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

            # Convert rows to list of dicts
            results = []
            for row in rows:
                row_dict = {}
                for i, column in enumerate(columns):
                    value = row[i]
                    # Convert date/datetime to string for JSON serialization
                    if hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    # Convert Decimal to float
                    elif hasattr(value, '__float__'):
                        value = float(value)
                    row_dict[column] = value
                results.append(row_dict)

            cursor.close()
            conn.close()

            logger.info(f"Query executed successfully, returned {len(results)} rows")
            return json.dumps(results, indent=2)

        except pyodbc.Error as e:
            last_error = e
            logger.error(f"Database error on attempt {attempt + 1}: {e}")

            # Check if it's a transient error worth retrying
            error_str = str(e).lower()
            transient_errors = ['timeout', 'connection', 'network', 'deadlock']
            is_transient = any(err in error_str for err in transient_errors)

            if not retry or not is_transient or attempt == MAX_RETRIES - 1:
                # Don't retry or last attempt
                break

            # Exponential backoff
            delay = RETRY_DELAY * (2 ** attempt)
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)

        except Exception as e:
            last_error = e
            logger.error(f"Unexpected error: {e}")
            break

    # All retries failed
    error_message = str(last_error) if last_error else "Unknown error"
    return json.dumps({
        "error": error_message,
        "query": query,
        "attempts": attempt + 1
    })
