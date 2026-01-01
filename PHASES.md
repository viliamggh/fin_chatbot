# Phase Reference Guide

This document tracks all completed phases with git tags for easy navigation between implementations.

## How to Use

### List all phases
```bash
git tag -l "phase-*"
```

### View phase details
```bash
git show phase-01-foundation
```

### Switch to a specific phase
```bash
git checkout phase-01-foundation
```

### Return to current development
```bash
git checkout main
```

### View differences between phases
```bash
git diff phase-01-foundation..phase-02-chat-history
```

---

## Completed Phases

### Phase 1: Foundation - Basic LLM API Calls ✅
**Tag**: `phase-01-foundation`
**Date**: 2026-01-01
**Key Concepts**:
- Azure OpenAI client setup
- Chat completions API
- Interactive terminal loop
- Error handling

**Key Files**:
- `src/main.py` - Interactive chat application

**What You'll Learn**:
- Connecting to Azure OpenAI
- Sending messages and receiving responses
- Building a simple interactive chat interface

**Test Command**:
```bash
cd src && uv run python main.py
```

---

### Phase 2: Chat History & Context ✅
**Tag**: `phase-02-chat-history`
**Date**: 2026-01-01
**Key Concepts**:
- Message history management
- Context-aware conversations
- Multi-turn dialogue
- Stateful vs stateless design

**Key Files**:
- `src/main.py` - Chat with conversation history

**What You'll Learn**:
- Maintaining conversation state across turns
- Building message history lists
- Sending full context with each API call
- Preserving history integrity during errors

**Test Command**:
```bash
cd src && uv run python main.py
# Try: "My name is John" followed by "What's my name?"
```

---

### Phase 3: Tool Calling (Function Calling) ✅
**Tag**: `phase-03-tool-calling`
**Date**: 2026-01-01
**Key Concepts**:
- Function calling / tool use
- Tool schema definition (JSON Schema)
- Tool call detection
- Execution loop (call → execute → return → respond)
- Mock data simulation

**Key Files**:
- `src/main.py` - Tool calling implementation with execute_sql

**What You'll Learn**:
- Defining tools with JSON Schema format
- Detecting when LLM wants to call a function
- Executing functions and parsing arguments
- Multi-step conversation: user → tool call → tool result → final response
- Message roles including "tool" role

**Test Command**:
```bash
cd src && uv run python main.py
# Try: "What transactions do I have?"
# Try: "Show me my recent purchases"
```

---

### Phase 4: Database Connection - Azure SQL ✅
**Tag**: `phase-04-azure-sql`
**Date**: 2026-01-01
**Key Concepts**:
- Azure SQL Database connection with pyodbc
- Schema discovery and introspection
- Safe SQL query execution (SELECT only)
- JSON result formatting
- Credential management via Key Vault

**Key Files**:
- `src/db.py` - Database operations module (NEW)
- `src/main.py` - Updated to use real database
- `src/.env.example` - Added SQL credentials template
- `src/pyproject.toml` - Added pyodbc dependency

**What You'll Learn**:
- Connecting to Azure SQL with ODBC
- Querying database schema (INFORMATION_SCHEMA)
- Executing parameterized queries safely
- Handling database errors gracefully
- Converting query results to JSON
- Injecting schema context into LLM prompts

**Test Command**:
```bash
cd src && uv run python main.py
# Try: "What are my recent transactions?"
# Try: "Show me all transactions from last week"
# Try: "What's my biggest expense?"
```

---

## Upcoming Phases

### Phase 5: ReAct Agent Pattern
**Tag**: `phase-05-react-agent` (pending)
**Key Concepts**: Reason-Act-Observe cycle, agent loops

### Phase 6: Schema-Aware Production Agent
**Tag**: `phase-06-production-agent` (pending)
**Key Concepts**: Query validation, error recovery, production patterns

### Phase 7: LangChain Introduction
**Tag**: `phase-07-langchain` (pending)
**Key Concepts**: LangChain framework, custom tools

### Phase 8: LangGraph Basics
**Tag**: `phase-08-langgraph-basics` (pending)
**Key Concepts**: State management, graph execution

### Phase 9: LangGraph SQL Agent
**Tag**: `phase-09-langgraph-agent` (pending)
**Key Concepts**: Full SQL agent, node structure, routing

### Phase 10: Multi-Agent System
**Tag**: `phase-10-multi-agent` (pending)
**Key Concepts**: Agent orchestration, specialized agents

### Phase 11: Deployment & GUI
**Tag**: `phase-11-deployment` (pending)
**Key Concepts**: Containerization, FastAPI, GUI, Azure deployment

---

## Quick Reference Commands

```bash
# Create a new phase tag (for future phases)
git tag -a phase-XX-name -m "Phase description"

# Push tags to remote
git push origin --tags

# Delete a tag (if needed)
git tag -d phase-XX-name
git push origin :refs/tags/phase-XX-name

# List tags with messages
git tag -l "phase-*" -n5
```

---

*This file is updated as each phase is completed*
