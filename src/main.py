"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 4: Real Azure SQL Database connection and queries
"""

from openai import AzureOpenAI
from dotenv import load_dotenv
import os
import json
import db

load_dotenv()


# Define tool schema for OpenAI function calling
tools = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Execute SQL query on the finance database to retrieve transaction data",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


def main():
    # Initialize Azure OpenAI client
    client = AzureOpenAI(
        api_version="2024-02-01",
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
    )

    print("=" * 60)
    print("fin_chatbot - SQL Assistant (Azure SQL)")
    print("=" * 60)
    print("Ask questions about your transactions!")
    print("Type 'quit' or 'exit' to end the conversation")
    print("Press Ctrl+C to interrupt")
    print("=" * 60)
    print()

    # Get database schema for LLM context
    print("Loading database schema...")
    try:
        schema_info = db.get_table_schema()
        print("Schema loaded successfully.\n")
    except Exception as e:
        print(f"Warning: Could not load schema: {e}\n")
        schema_info = "Schema information unavailable"

    # Initialize conversation history with system message including schema
    system_prompt = f"""You are a helpful SQL assistant. You can query a finance database with transactions.

Database Schema:
{schema_info}

When the user asks about transactions, use the execute_sql tool to query the database.
Always write valid SQL queries based on the schema above."""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
    ]

    # Interactive chat loop
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

            # Add user message to history
            messages.append({"role": "user", "content": user_input})

            # Send full conversation history to Azure OpenAI with tools
            try:
                response = client.chat.completions.create(
                    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                    messages=messages,
                    tools=tools,
                )

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls

                # Check if the model wants to call a tool
                if tool_calls:
                    # Add assistant's tool call message to history
                    messages.append(response_message)

                    # Process each tool call
                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        print(f"\n[Tool Call] {function_name}")
                        print(f"[Query] {function_args.get('query', 'N/A')}")

                        # Execute the function
                        if function_name == "execute_sql":
                            function_response = db.execute_sql_query(
                                query=function_args.get("query")
                            )
                        else:
                            function_response = json.dumps({"error": "Unknown function"})

                        # Add tool response to messages
                        messages.append(
                            {
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": function_response,
                            }
                        )

                    # Get final response from the model after tool execution
                    second_response = client.chat.completions.create(
                        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                        messages=messages,
                    )

                    assistant_message = second_response.choices[0].message.content
                    messages.append({"role": "assistant", "content": assistant_message})

                    print(f"\nAssistant: {assistant_message}\n")

                else:
                    # No tool call - regular response
                    assistant_message = response_message.content
                    messages.append({"role": "assistant", "content": assistant_message})
                    print(f"\nAssistant: {assistant_message}\n")

            except Exception as e:
                # Remove last user message if there was an error
                messages.pop()
                print(f"\nError: {e}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    except Exception as e:
        print(f"\nUnexpected error: {e}")


if __name__ == "__main__":
    main()
