"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 11: Multi-Agent System with CLI interface.
For web interface, run: uv run python app.py

Usage:
    uv run python main.py              # Normal mode
    uv run python main.py --verbose    # Audit mode (shows SQL + results)
"""

import argparse
from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langfuse.callback import CallbackHandler
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib
import os
import json
import uuid
import db
import artifacts

# Use non-interactive backend for matplotlib
matplotlib.use("Agg")

load_dotenv()


# Multi-agent state definition
class MultiAgentState(TypedDict):
    """State shared across all agents in the multi-agent system.

    messages: Conversation history
    user_question: Current user question
    needs_sql: Whether SQL query is needed
    needs_viz: Whether visualization is needed
    sql_query: Generated SQL query
    sql_results: Query results (JSON string) - for LLM context
    chart_type: Type of chart to generate (bar, line, pie, etc.)
    chart_path: Path to generated chart image (UUID-based)
    final_response: Synthesized response for user
    error: Error message if any

    # Structured artifact fields (Phase A2)
    table_columns: Column names from SQL result
    table_rows: Row data (capped at 50 rows for UI)
    row_count: Actual row count before truncation
    show_table: Progressive disclosure flag
    """

    messages: Annotated[list[BaseMessage], add_messages]
    user_question: str
    needs_sql: bool
    needs_viz: bool
    sql_query: str | None
    sql_results: str | None
    chart_type: str | None
    chart_path: str | None
    final_response: str | None
    error: str | None
    # Structured artifact fields
    table_columns: list[str] | None
    table_rows: list[list] | None
    row_count: int | None
    show_table: bool


def create_multi_agent_system(llm: AzureChatOpenAI, schema_info: str, sample_data_info: str):
    """Create a multi-agent system with Supervisor, SQL, Viz, and Response agents.

    Architecture:
    - Supervisor: Analyzes user intent, decides which agents to invoke
    - SQL Agent: Generates and executes SQL queries
    - Viz Agent: Creates visualizations with matplotlib
    - Response Agent: Synthesizes final response
    """

    # =========================================================================
    # SUPERVISOR AGENT - Routes to other agents
    # =========================================================================
    def supervisor(state: MultiAgentState) -> dict:
        """Analyze user question and decide which agents to invoke."""
        messages = state["messages"]
        user_question = messages[-1].content if messages else ""

        system_prompt = """You are a routing supervisor for a finance assistant.
Analyze the user's question and decide what's needed.

Respond with a JSON object (no markdown, just raw JSON):
{
    "needs_sql": true/false,
    "needs_viz": true/false,
    "chart_type": "bar" | "line" | "pie" | null,
    "reasoning": "brief explanation"
}

Guidelines:
- needs_sql: true for any data question (amounts, counts, lists, totals)
- needs_viz: true ONLY for aggregated data with trends/comparisons/distributions
- needs_viz: FALSE for listing individual transactions or showing raw data
- chart_type:
  - "bar" for category comparisons (by merchant, by type)
  - "line" for time series (by month, by week, trends)
  - "pie" for proportions (percentage breakdown)
  - null if no visualization needed

Examples:
- "What's my total spend?" → {"needs_sql": true, "needs_viz": false, "chart_type": null}
- "Show expenses by category" → {"needs_sql": true, "needs_viz": true, "chart_type": "bar"}
- "How has spending changed over time?" → {"needs_sql": true, "needs_viz": true, "chart_type": "line"}
- "Show me all transactions" → {"needs_sql": true, "needs_viz": false, "chart_type": null}
- "List transactions from December" → {"needs_sql": true, "needs_viz": false, "chart_type": null}
"""

        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"User question: {user_question}"),
            ])

            # Parse JSON response
            content = response.content.strip()
            # Clean up markdown if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            routing = json.loads(content)

            return {
                "user_question": user_question,
                "needs_sql": routing.get("needs_sql", True),
                "needs_viz": routing.get("needs_viz", False),
                "chart_type": routing.get("chart_type"),
                "sql_query": None,
                "sql_results": None,
                "chart_path": None,
                "final_response": None,
                "error": None,
                # Reset artifact fields
                "table_columns": None,
                "table_rows": None,
                "row_count": None,
                "show_table": False,
            }

        except Exception:
            # Default to SQL only on parsing errors
            return {
                "user_question": user_question,
                "needs_sql": True,
                "needs_viz": False,
                "chart_type": None,
                "error": None,
                # Reset artifact fields
                "table_columns": None,
                "table_rows": None,
                "row_count": None,
                "show_table": False,
            }

    # =========================================================================
    # SQL AGENT - Generates and executes queries
    # =========================================================================
    def sql_agent(state: MultiAgentState) -> dict:
        """Generate and execute SQL query."""
        user_question = state["user_question"]
        messages = state.get("messages", [])
        needs_viz = state.get("needs_viz", False)

        # Build conversation context from recent messages (last 3 turns = 6 messages)
        conversation_context = ""
        recent_messages = messages[-7:-1] if len(messages) > 1 else []  # Exclude current question
        if recent_messages:
            context_parts = []
            for msg in recent_messages:
                role = "User" if isinstance(msg, HumanMessage) else "Assistant"
                # Truncate long responses to avoid prompt bloat
                content = msg.content[:300] if len(msg.content) > 300 else msg.content
                context_parts.append(f"{role}: {content}")
            conversation_context = f"""
=== CONVERSATION CONTEXT (CRITICAL - READ CAREFULLY) ===
{chr(10).join(context_parts)}

CONTEXT CARRYOVER RULES:
1. If user previously asked about a specific time period (e.g., "December 2025"), ALWAYS include that date filter in the new query
2. If user says "these transactions", "those", "the same ones" - they mean the SAME data from the previous query
3. When user adds a new filter (like "only spending account"), ADD it to existing filters, don't replace them
4. Example: Previous query was for "December 2025", user now says "show only spending account" → keep BOTH the December 2025 AND spending account filters
=== END CONTEXT ===
"""

        # Adjust prompt based on whether we need viz data
        viz_hint = ""
        if needs_viz:
            chart_type = state.get("chart_type", "bar")
            viz_hint = f"""
IMPORTANT: The results will be used for a {chart_type} chart.
- For bar/pie charts: Include a category column and a value column
- For line charts: Include a date/time column and a value column
- Keep the result set reasonable (max 10-15 rows for readability)
- Use GROUP BY and ORDER BY appropriately
"""
        else:
            # For raw list queries (no visualization), limit rows for UI safety
            viz_hint = """
ROW LIMIT: For queries that list individual transactions (not aggregates),
use TOP 50 to limit results. This keeps the UI responsive.
Example: SELECT TOP 50 * FROM Transactions WHERE ...
"""

        system_prompt = f"""You are a SQL expert for a finance database.

Database Schema:
{schema_info}

{sample_data_info}

Generate a SQL query to answer the user's question.
Return ONLY the SQL query, nothing else.
{viz_hint}
Rules:
- Only SELECT queries allowed
- Use proper SQL Server syntax
- Keep queries efficient

Date handling (CRITICAL):
- When user mentions a month AND year (e.g., "December 2025"), prefer an indexed date range filter:
  WHERE TransactionDate >= '2025-12-01' AND TransactionDate < '2026-01-01'
- If YearMonth exists, you MAY use: WHERE YearMonth = 202512
- NEVER filter by month alone without year (avoid MONTH(TransactionDate)=12 without YEAR())
- Prefer avoiding MONTH()/YEAR() filters when possible (they can prevent index usage)
- For relative dates like "last month", "this year", use GETDATE() for calculations

Cashflow handling (CRITICAL):
- If available, prefer these helper columns for reliability:
  - CashflowDirection: 'income' | 'spend' | 'neutral'
  - SpendAmount: positive amount for spend rows (0 otherwise)
  - IncomeAmount: positive amount for income rows (0 otherwise)
- For "total spending": SUM(SpendAmount)
- For "total income": SUM(IncomeAmount)
- For "largest expense": MAX(SpendAmount) WHERE SpendAmount > 0
- For "smallest expense": MIN(SpendAmount) WHERE SpendAmount > 0
- For "largest income": MAX(IncomeAmount) WHERE IncomeAmount > 0
- For "smallest income": MIN(IncomeAmount) WHERE IncomeAmount > 0
- If helper columns are NOT available, fall back to Amount sign:
  - spend: Amount < 0 (use ABS() when presenting spending totals if needed)
  - income: Amount > 0

Important aggregation patterns:
- Use aggregates (MIN/MAX/SUM/AVG) for single-value questions
- Use TOP 1 with ORDER BY only when you need multiple columns (like transaction details)

AccountID mapping (user terms to database values):
- "spending account" or "spending" → WHERE AccountID = 'spending'
- "invoices account" or "invoices" → WHERE AccountID = 'invoices'
- If user doesn't specify account, query ALL accounts (no WHERE AccountID filter)

Example: "What was my largest expense?" → SELECT MAX(SpendAmount) as largest_expense FROM Transactions WHERE SpendAmount > 0
Example: "Show spending account transactions" → SELECT * FROM Transactions WHERE AccountID = 'spending'
Example: "December 2025 transactions" → SELECT * FROM Transactions WHERE TransactionDate >= '2025-12-01' AND TransactionDate < '2026-01-01'
{conversation_context}"""

        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Generate SQL for: {user_question}"),
            ])

            sql_query = response.content.strip()
            # Clean markdown
            if sql_query.startswith("```sql"):
                sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
            elif sql_query.startswith("```"):
                sql_query = sql_query.replace("```", "").strip()

            # Execute query
            results = db.execute_sql_query(sql_query)

            # Check for errors in results
            try:
                results_json = json.loads(results)
                if isinstance(results_json, dict) and "error" in results_json:
                    return {
                        "sql_query": sql_query,
                        "sql_results": None,
                        "error": f"SQL Error: {results_json['error']}",
                    }
            except json.JSONDecodeError:
                pass

            # Parse results into table artifact fields
            table_result = artifacts.results_json_to_table(results)

            if isinstance(table_result, dict) and table_result.get("type") == "error":
                # SQL returned an error
                return {
                    "sql_query": sql_query,
                    "sql_results": results,
                    "error": table_result["message"],
                    "table_columns": None,
                    "table_rows": None,
                    "row_count": None,
                }

            columns, rows, row_count = table_result
            return {
                "sql_query": sql_query,
                "sql_results": results,
                "error": None,
                "table_columns": columns,
                "table_rows": rows,
                "row_count": row_count,
            }

        except Exception as e:
            return {
                "sql_query": None,
                "sql_results": None,
                "error": f"SQL Agent error: {str(e)}",
                "table_columns": None,
                "table_rows": None,
                "row_count": None,
            }

    # =========================================================================
    # VISUALIZATION AGENT - Creates charts
    # =========================================================================
    def _is_numeric(value) -> bool:
        """Check if a value is numeric (int, float, or convertible)."""
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return True
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    def _is_date_like(value) -> bool:
        """Check if a value looks like a date (ISO format string)."""
        if value is None:
            return False
        if isinstance(value, str):
            # Check for ISO date patterns: YYYY-MM-DD or YYYY-MM
            if len(value) >= 7 and value[4] == '-':
                return True
        return False

    def _find_numeric_column(data: list, columns: list) -> str | None:
        """Find the first column with numeric values."""
        for col in columns:
            # Sample first few rows to check if column is numeric
            sample_values = [row.get(col) for row in data[:5] if row.get(col) is not None]
            if sample_values and all(_is_numeric(v) for v in sample_values):
                return col
        return None

    def _find_date_column(data: list, columns: list) -> str | None:
        """Find the first column with date-like values."""
        for col in columns:
            sample_values = [row.get(col) for row in data[:5] if row.get(col) is not None]
            if sample_values and all(_is_date_like(v) for v in sample_values):
                return col
        return None

    def viz_agent(state: MultiAgentState) -> dict:
        """Create visualization from SQL results."""
        sql_results = state.get("sql_results")
        chart_type = state.get("chart_type", "bar")
        user_question = state.get("user_question", "")

        if not sql_results:
            return {"chart_path": None, "error": "No data to visualize"}

        try:
            data = json.loads(sql_results)
            if not data or not isinstance(data, list):
                return {"chart_path": None, "error": "No data to visualize"}

            # Get column names from first row
            columns = list(data[0].keys())

            if len(columns) < 2:
                return {
                    "chart_path": None,
                    "error": "Need at least 2 columns for visualization (category + value)."
                }

            # Smart column detection
            # 1. Find numeric column for y-axis (required)
            y_col = _find_numeric_column(data, columns)
            if not y_col:
                return {
                    "chart_path": None,
                    "error": "Cannot chart: no numeric column found. Try asking for aggregated data (counts, sums, averages) instead of listing raw transactions."
                }

            # 2. Find x-axis column
            # For line charts, prefer date columns
            if chart_type == "line":
                date_col = _find_date_column(data, columns)
                if date_col:
                    x_col = date_col
                else:
                    # Use first non-numeric column, or first column
                    x_col = next((c for c in columns if c != y_col), columns[0])
            else:
                # For bar/pie: use first column that's not the y column
                x_col = next((c for c in columns if c != y_col), columns[0])

            # Extract data
            x_values = [str(row.get(x_col, ""))[:20] for row in data]  # Truncate long labels

            # Convert y_values to float (we already verified they're numeric)
            y_values = []
            for row in data:
                val = row.get(y_col, 0)
                try:
                    y_values.append(float(val) if val is not None else 0.0)
                except (ValueError, TypeError):
                    y_values.append(0.0)

            # Create figure
            fig, ax = plt.subplots(figsize=(10, 6))

            if chart_type == "pie":
                # Pie chart - use absolute values (can't show negatives)
                y_abs = [abs(v) for v in y_values]
                if sum(y_abs) == 0:
                    return {"chart_path": None, "error": "No non-zero data to visualize"}
                ax.pie(y_abs, labels=x_values, autopct="%1.1f%%", startangle=90)
                ax.set_title(f"Distribution: {user_question[:50]}")
            elif chart_type == "line":
                # Line chart
                ax.plot(x_values, y_values, marker="o", linewidth=2, markersize=8)
                ax.set_xlabel(x_col)
                ax.set_ylabel(y_col)
                ax.set_title(f"Trend: {user_question[:50]}")
                plt.xticks(rotation=45, ha="right")
            else:
                # Bar chart (default)
                bars = ax.bar(x_values, y_values, color="steelblue")
                ax.set_xlabel(x_col)
                ax.set_ylabel(y_col)
                ax.set_title(f"Comparison: {user_question[:50]}")
                plt.xticks(rotation=45, ha="right")

                # Add value labels on bars
                for bar, val in zip(bars, y_values):
                    height = bar.get_height()
                    ax.text(
                        bar.get_x() + bar.get_width() / 2.0,
                        height,
                        f"{val:,.0f}",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                    )

            plt.tight_layout()

            # Save to system temp directory with UUID (no collisions)
            chart_path = artifacts.generate_unique_chart_path()
            plt.savefig(chart_path, dpi=100, bbox_inches="tight")
            plt.close(fig)

            return {"chart_path": chart_path, "error": None}

        except Exception as e:
            return {"chart_path": None, "error": f"Visualization error: {str(e)}"}

    # =========================================================================
    # RESPONSE AGENT - Synthesizes final response
    # =========================================================================
    def response_agent(state: MultiAgentState) -> dict:
        """Synthesize final response from all agent outputs."""
        user_question = state.get("user_question", "")
        sql_query = state.get("sql_query")
        sql_results = state.get("sql_results")
        chart_path = state.get("chart_path")
        error = state.get("error")
        row_count = state.get("row_count", 0) or 0

        # Progressive disclosure: determine if table should be shown
        # Show table if:
        # 1. User explicitly asks for data/table/list
        # 2. Row count is small (<=10)
        show_table = False
        if row_count > 0:
            # Check for explicit data request keywords
            question_lower = user_question.lower()
            explicit_data_keywords = ["show", "list", "display", "table", "data", "transactions"]
            has_explicit_request = any(kw in question_lower for kw in explicit_data_keywords)

            if has_explicit_request or row_count <= 10:
                show_table = True

        # Handle error case
        if error:
            system_prompt = f"""The user asked: "{user_question}"
An error occurred: {error}

Explain the error briefly and suggest what might help."""

            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content="Explain the error to the user."),
            ])
            return {
                "final_response": response.content,
                "messages": [AIMessage(content=response.content)],
                "show_table": False,
            }

        # Build context for response
        context_parts = [f'User asked: "{user_question}"']

        if sql_query:
            context_parts.append(f"SQL query executed: {sql_query}")

        if sql_results:
            context_parts.append(f"Query results: {sql_results}")

        # Note: We no longer tell the LLM about chart paths - UI handles that
        has_chart = bool(chart_path and chart_path.strip())
        if has_chart:
            context_parts.append("A chart has been generated for this data.")

        context = "\n".join(context_parts)

        system_prompt = f"""You are a helpful finance assistant presenting results.

{context}

Provide a clear, natural language summary of the results.
- Be concise but informative
- Highlight key numbers or insights
- Format numbers nicely (use commas for thousands)
- Always use 'CZK' as the currency when presenting monetary amounts (Czech Koruna), never '$'. Example: '4,604.81 CZK'
- If a chart was generated, you can briefly mention it exists (e.g., "see the chart for visual breakdown")
- Do NOT mention file paths or where charts are saved"""

        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content="Summarize the results for the user."),
            ])

            final_response = response.content

            # No longer append chart path - UI handles chart display
            return {
                "final_response": final_response,
                "messages": [AIMessage(content=final_response)],
                "show_table": show_table,
            }

        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            return {
                "final_response": error_msg,
                "messages": [AIMessage(content=error_msg)],
                "show_table": False,
            }

    # =========================================================================
    # ROUTING FUNCTIONS
    # =========================================================================
    def route_after_supervisor(state: MultiAgentState) -> Literal["sql_agent", "response_agent"]:
        """Route after supervisor - always go to SQL if needed."""
        if state.get("needs_sql", True):
            return "sql_agent"
        return "response_agent"

    def route_after_sql(state: MultiAgentState) -> Literal["viz_agent", "response_agent"]:
        """Route after SQL - go to viz if needed and no error."""
        if state.get("error"):
            return "response_agent"
        if state.get("needs_viz", False):
            return "viz_agent"
        return "response_agent"

    def route_after_viz(_state: MultiAgentState) -> Literal["response_agent"]:
        """Always go to response after viz."""
        return "response_agent"

    # =========================================================================
    # BUILD THE GRAPH
    # =========================================================================
    graph = StateGraph(MultiAgentState)

    # Add agent nodes
    graph.add_node("supervisor", supervisor)
    graph.add_node("sql_agent", sql_agent)
    graph.add_node("viz_agent", viz_agent)
    graph.add_node("response_agent", response_agent)

    # Add edges
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"sql_agent": "sql_agent", "response_agent": "response_agent"},
    )
    graph.add_conditional_edges(
        "sql_agent",
        route_after_sql,
        {"viz_agent": "viz_agent", "response_agent": "response_agent"},
    )
    graph.add_conditional_edges(
        "viz_agent",
        route_after_viz,
        {"response_agent": "response_agent"},
    )
    graph.add_edge("response_agent", END)

    return graph.compile()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="fin_chatbot - Natural Language to SQL Chatbot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python main.py              # Normal interactive mode
  uv run python main.py --verbose    # Audit mode with SQL/result logging
  echo "How many transactions?" | uv run python main.py --verbose
        """,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable audit mode: show generated SQL and results in parseable format",
    )
    return parser.parse_args()


def main():
    # Parse command line arguments
    args = parse_args()

    print("=" * 60)
    print("fin_chatbot - Multi-Agent System (CLI)")
    if args.verbose:
        print("AUDIT MODE ENABLED - SQL and results will be logged")
    print("=" * 60)
    print("Agents: Supervisor → SQL → Visualization → Response")
    print("Ask questions about your transactions!")
    print('Try: "Show my expenses by category" for a chart')
    print("Type 'quit' or 'exit' to end the conversation")
    print("For web interface: uv run python app.py")
    print("=" * 60)
    print()

    # Get database schema for LLM context
    print("Loading database schema and sample data...")
    try:
        schema_info = db.get_table_schema()
        print("✓ Schema loaded")

        # Get sample data to enrich context
        table_names = db.get_table_names()
        sample_data_parts = []
        for table_name in table_names:
            sample_data = db.get_sample_data(table_name, limit=2)
            sample_data_parts.append(sample_data)

        sample_data_info = "\n".join(sample_data_parts)
        print(f"✓ Sample data loaded from {len(table_names)} table(s)\n")

    except Exception as e:
        print(f"Warning: Could not load schema/sample data: {e}\n")
        schema_info = "Schema information unavailable"
        sample_data_info = ""

    # Initialize Azure OpenAI with LangChain
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        api_version="2024-02-01",
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        temperature=0,
    )

    # Create the multi-agent system
    agent_system = create_multi_agent_system(llm, schema_info, sample_data_info)

    # Initialize Langfuse callback for observability (optional)
    langfuse_handler = None
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            session_id = f"cli-session-{uuid.uuid4().hex[:8]}"
            langfuse_handler = CallbackHandler(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                session_id=session_id,
                user_id="cli-user",
            )
            print(f"✓ Langfuse tracing enabled (session: {session_id})\n")
        except Exception as e:
            print(f"⚠ Langfuse initialization failed: {e}\n")

    # Display the architecture
    print("Multi-Agent Architecture:")
    print("-" * 40)
    print("           ┌────────────┐")
    print("           │ SUPERVISOR │")
    print("           └─────┬──────┘")
    print("                 │")
    print("           ┌─────▼──────┐")
    print("           │ SQL_AGENT  │")
    print("           └─────┬──────┘")
    print("          needs_viz?")
    print("           yes/  \\no")
    print("             /    \\")
    print("   ┌─────────▼┐    │")
    print("   │VIZ_AGENT │    │")
    print("   └─────┬────┘    │")
    print("         │         │")
    print("         └────┬────┘")
    print("              ▼")
    print("      ┌──────────────┐")
    print("      │RESPONSE_AGENT│")
    print("      └──────┬───────┘")
    print("             ▼")
    print("            END")
    print("-" * 40)
    print()

    # Interactive chat loop
    messages: list[BaseMessage] = []
    try:
        while True:
            # Get user input
            user_input = input("You: ").strip()

            # Check for exit commands
            if user_input.lower() in ["quit", "exit"]:
                print("\nGoodbye!")
                break

            # Skip empty input
            if not user_input:
                continue

            # Add user message
            messages.append(HumanMessage(content=user_input))

            # Execute multi-agent system
            try:
                # Build config with optional Langfuse callback
                config = {}
                if langfuse_handler:
                    config["callbacks"] = [langfuse_handler]

                result = agent_system.invoke({
                    "messages": messages,
                    "user_question": "",
                    "needs_sql": False,
                    "needs_viz": False,
                    "sql_query": None,
                    "sql_results": None,
                    "chart_type": None,
                    "chart_path": None,
                    "final_response": None,
                    "error": None,
                    # Artifact fields
                    "table_columns": None,
                    "table_rows": None,
                    "row_count": None,
                    "show_table": False,
                }, config=config if config else None)

                # Get final response
                final_response = result.get("final_response", "")

                if final_response:
                    print(f"\nAssistant: {final_response}\n")
                    messages = list(result.get("messages", messages))
                else:
                    print("\nAssistant: [No response generated]\n")

                # Audit output (verbose mode) - structured for agent parsing
                if args.verbose and (result.get("sql_query") or result.get("sql_results")):
                    print("--- AUDIT START ---")
                    print(f"QUESTION: {user_input}")
                    print(f"SQL_GENERATED: {result.get('sql_query', 'N/A')}")

                    # Parse and display SQL results
                    sql_results_raw = result.get("sql_results", "[]")
                    try:
                        result_data = json.loads(sql_results_raw) if sql_results_raw else []
                        if isinstance(result_data, list):
                            print(f"RESULT_COUNT: {len(result_data)}")
                        else:
                            print("RESULT_COUNT: 1")
                        # Truncate for readability but keep parseable
                        truncated = sql_results_raw[:500] if len(sql_results_raw) > 500 else sql_results_raw
                        print(f"SQL_RESULT: {truncated}")
                    except json.JSONDecodeError:
                        print(f"SQL_RESULT: {sql_results_raw}")

                    print(f"FINAL_ANSWER: {result.get('final_response', 'N/A')}")
                    if result.get("error"):
                        print(f"ERROR: {result.get('error')}")
                    print("--- AUDIT END ---")
                    print()

                # Standard debug info (non-verbose mode)
                elif result.get("sql_query") or result.get("needs_viz"):
                    if result.get("sql_query"):
                        print(f"[SQL]: {result['sql_query']}")
                    if result.get("needs_viz"):
                        print(f"[Viz]: {result.get('chart_type', 'unknown')} chart")
                    print()

            except Exception as e:
                messages.pop()
                print(f"\nError: {e}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    except Exception as e:
        print(f"\nUnexpected error: {e}")


if __name__ == "__main__":
    main()
