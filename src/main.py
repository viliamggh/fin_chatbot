"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 1: Basic Azure OpenAI connection with interactive terminal chat
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
    print("fin_chatbot - Interactive Chat")
    print("=" * 60)
    print("Type 'quit' or 'exit' to end the conversation")
    print("Press Ctrl+C to interrupt")
    print("=" * 60)
    print()

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

            # Send message to Azure OpenAI
            try:
                response = client.chat.completions.create(
                    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": user_input},
                    ],
                )

                # Display response
                print(f"\nAssistant: {response.choices[0].message.content}\n")

            except Exception as e:
                print(f"\nError: {e}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    except Exception as e:
        print(f"\nUnexpected error: {e}")


if __name__ == "__main__":
    main()
