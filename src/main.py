"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 8: LangGraph Basics - Explicit state graph with nodes, edges, and conditional routing
"""

from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
import os
import json
import db

load_dotenv()


# Define the agent state using TypedDict
class AgentState(TypedDict):
    """State that flows through the graph nodes.

    messages: Conversation history with add_messages reducer
    """

    messages: Annotated[list[BaseMessage], add_messages]


@tool
def execute_sql(query: str) -> str:
    """Execute SQL query on the finance database to retrieve transaction data.

    Args:
        query: The SQL query to execute

    Returns:
        JSON string with query results or error message
    """
    return db.execute_sql_query(query)


# Tool mapping for execution
TOOLS = {"execute_sql": execute_sql}


def create_agent_graph(llm: AzureChatOpenAI, system_prompt: str):
    """Create a LangGraph agent with explicit nodes and edges.

    This demonstrates:
    - StateGraph construction
    - Node functions
    - Conditional routing
    - Tool execution flow
    """
    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools([execute_sql])

    # Node: Call the LLM
    def call_model(state: AgentState) -> dict:
        """Node that calls the LLM with current messages."""
        messages = state["messages"]

        # Add system prompt as first message if not present
        if not messages or not hasattr(messages[0], "content") or "SQL agent" not in str(messages[0].content):
            from langchain_core.messages import SystemMessage

            messages = [SystemMessage(content=system_prompt)] + list(messages)

        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    # Node: Execute tools
    def execute_tools(state: AgentState) -> dict:
        """Node that executes tool calls from the LLM response."""
        messages = state["messages"]
        last_message = messages[-1]

        tool_results = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            # Execute the tool
            if tool_name in TOOLS:
                result = TOOLS[tool_name].invoke(tool_args)
            else:
                result = json.dumps({"error": f"Unknown tool: {tool_name}"})

            tool_results.append(
                ToolMessage(content=result, tool_call_id=tool_call["id"])
            )

        return {"messages": tool_results}

    # Conditional edge: Should we continue to tools or end?
    def should_continue(state: AgentState) -> Literal["tools", "end"]:
        """Determine if we should execute tools or finish."""
        messages = state["messages"]
        last_message = messages[-1]

        # If LLM made tool calls, execute them
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # Otherwise, we're done
        return "end"

    # Build the graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", call_model)
    graph.add_node("tools", execute_tools)

    # Add edges
    graph.add_edge(START, "agent")  # Start with agent
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",  # If tools needed, go to tools node
            "end": END,  # If no tools, end
        },
    )
    graph.add_edge("tools", "agent")  # After tools, back to agent

    # Compile and return
    return graph.compile()


def main():
    print("=" * 60)
    print("fin_chatbot - LangGraph SQL Agent")
    print("=" * 60)
    print("Powered by LangGraph state machine")
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

    # System prompt for the agent
    system_prompt = f"""You are a production-grade SQL agent that helps users query a finance database.

Database Schema:
{schema_info}

{sample_data_info}

When answering questions, follow this pattern:
1. Understand the user's question
2. Generate an appropriate SQL query using the execute_sql tool
3. Analyze the results from the database
4. Provide a clear, natural language answer to the user

Important guidelines:
- Always validate your SQL syntax before executing
- Use the schema and sample data above to write accurate queries
- Only SELECT queries are allowed (no INSERT, UPDATE, DELETE, DROP, etc.)
- Queries have a 30-second timeout
- Failed queries will be automatically retried up to 3 times
- If a query fails or returns unexpected results, refine your approach
- Break down complex questions into simpler queries if needed
- Explain your reasoning when helpful"""

    # Create the agent graph
    agent_graph = create_agent_graph(llm, system_prompt)

    # Display the graph structure
    print("Agent Graph Structure:")
    print("-" * 40)
    print("  START")
    print("    │")
    print("    ▼")
    print("  ┌───────┐")
    print("  │ agent │◄─────┐")
    print("  └───┬───┘      │")
    print("      │          │")
    print("   tools?        │")
    print("    / \\         │")
    print("  yes  no        │")
    print("   │    │        │")
    print("   ▼    ▼        │")
    print("┌─────┐ END      │")
    print("│tools│──────────┘")
    print("└─────┘")
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
                result = agent_graph.invoke({"messages": messages})

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
