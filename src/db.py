"""
Database operations for Azure SQL Server connection.
"""

import os
import pyodbc
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def get_connection() -> pyodbc.Connection:
    """
    Create and return a connection to Azure SQL Database.

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


def execute_sql_query(query: str) -> str:
    """
    Execute a SQL query and return results as JSON.

    Args:
        query: SQL query string to execute

    Returns:
        JSON string with query results or error message

    Note:
        Only SELECT queries are allowed for safety.
    """
    # Safety check: only allow SELECT queries
    query_upper = query.strip().upper()
    if not query_upper.startswith("SELECT"):
        return json.dumps({
            "error": "Only SELECT queries are allowed",
            "query": query
        })

    try:
        conn = get_connection()
        cursor = conn.cursor()

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

        return json.dumps(results, indent=2)

    except pyodbc.Error as e:
        return json.dumps({
            "error": str(e),
            "query": query
        })
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "query": query
        })
