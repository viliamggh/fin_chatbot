"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 2: Chat history and context management
"""

from openai import AzureOpenAI
from dotenv import load_dotenv
import os

load_dotenv()


def main():
    # Initialize Azure OpenAI client
    client = AzureOpenAI(
        api_version="2024-02-01",
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
    )

    print("=" * 60)
    print("fin_chatbot - Interactive Chat with History")
    print("=" * 60)
    print("Type 'quit' or 'exit' to end the conversation")
    print("Press Ctrl+C to interrupt")
    print("=" * 60)
    print()

    # Initialize conversation history with system message
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
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

            # Send full conversation history to Azure OpenAI
            try:
                response = client.chat.completions.create(
                    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                    messages=messages,
                )

                # Get assistant's response
                assistant_message = response.choices[0].message.content

                # Add assistant's response to history
                messages.append({"role": "assistant", "content": assistant_message})

                # Display response
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
