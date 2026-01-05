"""Artifact data structures and helpers for structured UI outputs."""

from __future__ import annotations

import base64
import csv
import json
import tempfile
import uuid
from typing import TypedDict


# --- Artifact Type Definitions ---

class TableArtifact(TypedDict):
    """Tabular data for display in gr.Dataframe."""

    type: str  # "table"
    title: str
    columns: list[str]
    rows: list[list]
    row_count: int  # Actual count (before truncation)


class ChartArtifact(TypedDict):
    """Chart image for display in gr.Image."""

    type: str  # "chart"
    title: str
    mime: str  # "image/png"
    data_base64: str


class DetailsArtifact(TypedDict):
    """Debug/developer info (SQL query, notes)."""

    type: str  # "details"
    sql: str
    notes: str


class ErrorArtifact(TypedDict):
    """Error message for display as red banner."""

    type: str  # "error"
    message: str


# Union type for any artifact
Artifact = TableArtifact | ChartArtifact | DetailsArtifact | ErrorArtifact

# Maximum rows to include in table artifact (UI safety)
MAX_TABLE_ROWS = 50


# --- Helper Functions ---


def results_json_to_table(
    sql_results_json: str,
) -> tuple[list[str], list[list], int] | ErrorArtifact:
    """
    Parse SQL results JSON into table components.

    Args:
        sql_results_json: JSON string from db.execute_sql_query().
            Can be:
            - A list of dicts: [{"col1": val1, "col2": val2}, ...]
            - An error object: {"error": "...", "query": "...", "attempts": N}

    Returns:
        On success: tuple of (columns, rows, row_count)
            - columns: list of column names
            - rows: list of row data (each row is a list), capped at MAX_TABLE_ROWS
            - row_count: actual row count before truncation
        On error: ErrorArtifact with the error message
    """
    if not sql_results_json:
        return [], [], 0

    try:
        data = json.loads(sql_results_json)
    except json.JSONDecodeError as e:
        return ErrorArtifact(
            type="error",
            message=f"Failed to parse SQL results: {e}",
        )

    # Check for error response
    if isinstance(data, dict):
        if "error" in data:
            return ErrorArtifact(
                type="error",
                message=f"SQL error: {data['error']}",
            )
        # Single dict that's not an error - wrap in list
        data = [data]

    # Handle non-list data
    if not isinstance(data, list):
        return ErrorArtifact(
            type="error",
            message=f"Unexpected SQL result format: expected list, got {type(data).__name__}",
        )

    # Empty results
    if len(data) == 0:
        return [], [], 0

    # Extract columns from first row
    first_row = data[0]
    if not isinstance(first_row, dict):
        return ErrorArtifact(
            type="error",
            message=f"Unexpected row format: expected dict, got {type(first_row).__name__}",
        )

    columns = list(first_row.keys())
    row_count = len(data)

    # Convert dicts to lists of values, respecting column order
    rows = []
    for row_dict in data[:MAX_TABLE_ROWS]:
        row_values = [row_dict.get(col) for col in columns]
        rows.append(row_values)

    return columns, rows, row_count


def table_to_csv_tempfile(columns: list[str], rows: list[list]) -> str | None:
    """
    Write table data to a temporary CSV file.

    Args:
        columns: list of column names
        rows: list of row data (each row is a list)

    Returns:
        Path to the temporary CSV file, or None if data is empty.

    Note:
        Uses tempfile.NamedTemporaryFile with delete=False.
        Gradio's gr.File auto-cleans temp files after download.
    """
    if not columns and not rows:
        return None

    # Create unique temp file
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv",
        prefix=f"export_{uuid.uuid4().hex[:8]}_",
        delete=False,
        newline="",
    )

    try:
        writer = csv.writer(temp_file)
        writer.writerow(columns)
        writer.writerows(rows)
        temp_file.close()
        return temp_file.name
    except Exception:
        temp_file.close()
        return None


def png_bytes_to_base64(png_bytes: bytes) -> str:
    """
    Encode PNG bytes to base64 string.

    Args:
        png_bytes: Raw PNG image bytes

    Returns:
        Base64-encoded string
    """
    return base64.b64encode(png_bytes).decode("utf-8")


def base64_to_png_bytes(base64_str: str) -> bytes:
    """
    Decode base64 string to PNG bytes.

    Args:
        base64_str: Base64-encoded string

    Returns:
        Raw PNG image bytes
    """
    return base64.b64decode(base64_str)


def create_table_artifact(
    title: str,
    columns: list[str],
    rows: list[list],
    row_count: int,
) -> TableArtifact:
    """Create a table artifact."""
    return TableArtifact(
        type="table",
        title=title,
        columns=columns,
        rows=rows,
        row_count=row_count,
    )


def create_chart_artifact(
    title: str,
    png_bytes: bytes,
) -> ChartArtifact:
    """Create a chart artifact from PNG bytes."""
    return ChartArtifact(
        type="chart",
        title=title,
        mime="image/png",
        data_base64=png_bytes_to_base64(png_bytes),
    )


def create_details_artifact(
    sql: str,
    notes: str = "",
) -> DetailsArtifact:
    """Create a details artifact."""
    return DetailsArtifact(
        type="details",
        sql=sql,
        notes=notes,
    )


def create_error_artifact(message: str) -> ErrorArtifact:
    """Create an error artifact."""
    return ErrorArtifact(
        type="error",
        message=message,
    )


def generate_unique_chart_path() -> str:
    """
    Generate a unique path for chart temp file.

    Returns:
        Path like /tmp/chart_<uuid>.png
    """
    return f"{tempfile.gettempdir()}/chart_{uuid.uuid4().hex}.png"
