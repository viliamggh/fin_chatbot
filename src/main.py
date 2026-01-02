"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 9: LangGraph SQL Agent - Specialized nodes for SQL workflow
"""

from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
import os
import json
import db

load_dotenv()


# Define the agent state with SQL-specific fields
class AgentState(TypedDict):
    """State that flows through the SQL agent graph.

    messages: Conversation history with add_messages reducer
    user_question: Current user question being processed
    sql_query: Generated SQL query
    results: Query execution results (JSON string)
    error: Error message if any step fails
    """

    messages: Annotated[list[BaseMessage], add_messages]
    user_question: str
    sql_query: str | None
    results: str | None
    error: str | None


def create_sql_agent_graph(llm: AzureChatOpenAI, schema_info: str, sample_data_info: str):
    """Create a LangGraph SQL agent with specialized nodes.

    This demonstrates:
    - Specialized nodes for each step of SQL workflow
    - State persistence across nodes
    - Error handling and conditional routing
    - Separation of concerns
    """

    # Node 1: Analyze user question
    def analyze(state: AgentState) -> dict:
        """Analyze the user question and extract intent."""
        messages = state["messages"]
        user_question = messages[-1].content if messages else ""

        return {
            "user_question": user_question,
            "sql_query": None,
            "results": None,
            "error": None,
        }

    # Node 2: Generate SQL query
    def generate_sql(state: AgentState) -> dict:
        """Generate SQL query based on user question."""
        user_question = state["user_question"]

        system_prompt = f"""You are a SQL query generator for a finance database.

Database Schema:
{schema_info}

{sample_data_info}

Generate a SQL query to answer the user's question. Return ONLY the SQL query, nothing else.

Important:
- Only generate SELECT queries
- Use the schema and sample data above for accuracy
- Ensure proper SQL syntax
- Keep queries simple and efficient"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Generate SQL query for: {user_question}"),
        ]

        try:
            response = llm.invoke(messages)
            sql_query = response.content.strip()

            # Clean up markdown code blocks if present
            if sql_query.startswith("```sql"):
                sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
            elif sql_query.startswith("```"):
                sql_query = sql_query.replace("```", "").strip()

            return {"sql_query": sql_query, "error": None}

        except Exception as e:
            return {"sql_query": None, "error": f"SQL generation failed: {str(e)}"}

    # Node 3: Execute SQL query
    def execute(state: AgentState) -> dict:
        """Execute the generated SQL query."""
        sql_query = state["sql_query"]

        if not sql_query:
            return {"results": None, "error": "No SQL query to execute"}

        try:
            results = db.execute_sql_query(sql_query)

            # Check if results contain an error
            try:
                results_json = json.loads(results)
                if isinstance(results_json, dict) and "error" in results_json:
                    return {
                        "results": None,
                        "error": f"Query execution failed: {results_json['error']}",
                    }
            except json.JSONDecodeError:
                pass

            return {"results": results, "error": None}

        except Exception as e:
            return {"results": None, "error": f"Execution error: {str(e)}"}

    # Node 4: Respond with natural language
    def respond(state: AgentState) -> dict:
        """Format results into natural language response."""
        user_question = state["user_question"]
        sql_query = state["sql_query"]
        results = state["results"]
        error = state["error"]

        # Handle error case
        if error:
            system_prompt = f"""You are a helpful assistant explaining why a database query failed.

User asked: {user_question}
Generated SQL: {sql_query or "None"}
Error: {error}

Explain the error in simple terms and suggest what might be wrong."""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content="Explain why this query failed and what could be done differently."
                ),
            ]

        else:
            # Success case
            system_prompt = f"""You are a helpful assistant presenting database query results.

User asked: {user_question}
SQL query used: {sql_query}
Results: {results}

Provide a clear, natural language answer to the user's question based on these results."""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content="Summarize the results for the user."),
            ]

        try:
            response = llm.invoke(messages)
            return {"messages": [AIMessage(content=response.content)]}

        except Exception as e:
            return {
                "messages": [
                    AIMessage(content=f"Sorry, I encountered an error: {str(e)}")
                ]
            }

    # Routing functions
    def should_generate_sql(state: AgentState) -> Literal["generate_sql", "end"]:
        """Route from analyze to generate_sql or end."""
        if state.get("user_question"):
            return "generate_sql"
        return "end"

    def should_execute(state: AgentState) -> Literal["execute", "respond"]:
        """Route from generate_sql to execute or respond (on error)."""
        if state.get("sql_query") and not state.get("error"):
            return "execute"
        return "respond"

    def should_respond(_state: AgentState) -> Literal["respond"]:
        """Always route to respond after execute."""
        return "respond"

    # Build the graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("analyze", analyze)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute", execute)
    graph.add_node("respond", respond)

    # Add edges
    graph.add_edge(START, "analyze")
    graph.add_conditional_edges(
        "analyze", should_generate_sql, {"generate_sql": "generate_sql", "end": END}
    )
    graph.add_conditional_edges(
        "generate_sql", should_execute, {"execute": "execute", "respond": "respond"}
    )
    graph.add_conditional_edges("execute", should_respond, {"respond": "respond"})
    graph.add_edge("respond", END)

    # Compile and return
    return graph.compile()


def main():
    print("=" * 60)
    print("fin_chatbot - LangGraph SQL Agent (Phase 9)")
    print("=" * 60)
    print("Powered by specialized SQL workflow nodes")
    print("Ask questions about your transactions!")
    print("Type 'quit' or 'exit' to end the conversation")
    print("Press Ctrl+C to interrupt")
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

    # Create the SQL agent graph
    agent_graph = create_sql_agent_graph(llm, schema_info, sample_data_info)

    # Display the graph structure
    print("SQL Agent Graph Structure:")
    print("-" * 40)
    print("  START")
    print("    │")
    print("    ▼")
    print("  ┌─────────┐")
    print("  │ analyze │")
    print("  └────┬────┘")
    print("       │")
    print("       ▼")
    print("  ┌──────────────┐")
    print("  │ generate_sql │")
    print("  └───────┬──────┘")
    print("      error│  ok")
    print("        ┌──┴───┐")
    print("        ▼      ▼")
    print("    ┌────────┐ ┌─────────┐")
    print("    │respond │ │ execute │")
    print("    └────┬───┘ └────┬────┘")
    print("         │          │")
    print("         │          ▼")
    print("         │     ┌────────┐")
    print("         └────►│respond │")
    print("               └───┬────┘")
    print("                   │")
    print("                   ▼")
    print("                  END")
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

            # Execute agent graph
            try:
                result = agent_graph.invoke(
                    {
                        "messages": messages,
                        "user_question": "",
                        "sql_query": None,
                        "results": None,
                        "error": None,
                    }
                )

                # Extract the final AI message
                response_content = None
                if "messages" in result:
                    for msg in reversed(result["messages"]):
                        if isinstance(msg, AIMessage) and msg.content:
                            response_content = msg.content
                            break

                if response_content:
                    print(f"\nAssistant: {response_content}\n")
                    # Update messages with full conversation
                    messages = list(result["messages"])
                else:
                    print("\nAssistant: [No response generated]\n")

                # Debug: Show SQL query if available
                if result.get("sql_query"):
                    print(f"[SQL Query]: {result['sql_query']}\n")

            except Exception as e:
                # Remove last user message on error
                messages.pop()
                print(f"\nError: {e}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    except Exception as e:
        print(f"\nUnexpected error: {e}")


if __name__ == "__main__":
    main()
