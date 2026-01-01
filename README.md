# fin_chatbot

Natural Language to SQL chatbot for querying finance data.

## Overview

This service accepts natural language questions and:
1. Generates SQL queries using Azure OpenAI
2. Executes queries on Azure SQL Database
3. Returns augmented responses with query results

## Architecture

Part of the FinanceAssistant microservices ecosystem:
- Uses shared infrastructure from `fin_az_core`
- Connects to Azure OpenAI (Sweden Central)
- Queries Azure SQL Database

## Development

### Prerequisites
- Python 3.11+
- [UV](https://docs.astral.sh/uv/) for package management

### Setup
```bash
cd src

# Copy environment template
cp .env.example .env

# Get API key from Key Vault
az keyvault secret show --vault-name kv-finazcore251027-dev --name openai-api-key --query value -o tsv

# Edit .env with your API key

# Install dependencies and run
uv run python main.py
```

## Project Structure
```
fin_chatbot/
├── src/
│   ├── main.py           # Entry point
│   ├── pyproject.toml    # UV project config
│   └── .env.example      # Environment template
├── terraform/            # (later phases)
├── .github/workflows/    # (later phases)
├── .gitignore
├── .infra-refs.yaml      # Core infrastructure references
└── README.md
```

## Roadmap

See `tasks/003_fin_chatbot_nl2sql.md` for the full implementation roadmap.
