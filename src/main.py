"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 6: Schema-Aware Production Agent with validation, timeouts, and retry logic
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
    print("fin_chatbot - Production SQL Agent")
    print("=" * 60)
    print("Features: Query validation, timeouts, retry logic")
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

    # Initialize conversation history with system message including schema
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
