"""
fin_chatbot - Natural Language to SQL Chatbot

Phase 1: Basic Azure OpenAI connection
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

    # Simple chat completion
    response = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! Tell me a short joke."},
        ],
    )

    print("Response from Azure OpenAI:")
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
