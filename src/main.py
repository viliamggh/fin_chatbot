"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 7: LangChain Introduction - Refactored to use LangChain framework
"""

from langchain_openai import AzureChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import db

load_dotenv()


@tool
def execute_sql(query: str) -> str:
    """Execute SQL query on the finance database to retrieve transaction data.

    Args:
        query: The SQL query to execute

    Returns:
        JSON string with query results or error message
    """
    return db.execute_sql_query(query)


def main():
    print("=" * 60)
    print("fin_chatbot - LangChain SQL Agent")
    print("=" * 60)
    print("Powered by LangChain framework")
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
    system_prompt = f"""You are a production-grade SQL agent that helps users query a finance database using the ReAct pattern.

Database Schema:
{schema_info}

{sample_data_info}

When answering questions, follow the ReAct cycle:
1. THINK: Reason about what SQL query would answer the user's question
2. ACT: Generate and execute the SQL query using the execute_sql tool
3. OBSERVE: Analyze the results from the database
4. RESPOND: Provide a clear, natural language answer to the user

Important guidelines:
- Always validate your SQL syntax before executing
- Use the schema and sample data above to write accurate queries
- Only SELECT queries are allowed (no INSERT, UPDATE, DELETE, DROP, etc.)
- Queries have a 30-second timeout
- Failed queries will be automatically retried up to 3 times
- If a query fails or returns unexpected results, refine your approach
- Break down complex questions into simpler queries if needed
- Explain your reasoning when helpful"""

    # Create agent with tools using LangChain's create_agent
    tools_list = [execute_sql]
    agent_graph = create_agent(
        model=llm,
        tools=tools_list,
        system_prompt=system_prompt,
        debug=False,
    )

    # Interactive chat loop
    messages = []
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

            # Add user message to messages
            messages.append({"role": "user", "content": user_input})

            # Execute agent
            try:
                # Use invoke for simpler response handling
                result = agent_graph.invoke({"messages": messages})

                # Extract the final AI message from the result
                response_content = None
                if "messages" in result:
                    # Get the last AI message
                    for msg in reversed(result["messages"]):
                        if hasattr(msg, "content") and hasattr(msg, "type") and msg.type == "ai":
                            # Skip tool call messages (they have tool_calls but empty content)
                            if msg.content:
                                response_content = msg.content
                                break

                if response_content:
                    # Display response
                    print(f"\nAssistant: {response_content}\n")

                    # Add assistant response to messages
                    messages.append({"role": "assistant", "content": response_content})
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
