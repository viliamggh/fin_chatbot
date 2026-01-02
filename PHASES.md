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

### Phase 5: ReAct Agent Pattern ✅
**Tag**: `phase-05-react-agent`
**Date**: 2026-01-01
**Key Concepts**:
- ReAct pattern (Reason-Act-Observe)
- Explicit reasoning instructions
- Iterative query refinement
- Error recovery through prompting
- Breaking complex questions into steps

**Key Files**:
- `src/main.py` - Updated system prompt with ReAct instructions

**What You'll Learn**:
- How prompting technique affects agent behavior
- The ReAct cycle: THINK → ACT → OBSERVE → RESPOND
- Encouraging LLMs to reason explicitly
- Using existing infrastructure with better prompts
- Difference between structural vs. prompting improvements

**Implementation Notes**:
- Primary change is the system prompt (prompting technique)
- Leverages existing tool calling loop from Phase 3-4
- No new code infrastructure needed
- ReAct is fundamentally about **how** you prompt the model

**Test Command**:
```bash
cd src && uv run python main.py
# Try: "What's the total of my expenses last month?"
# Try: "Which merchant did I spend the most at?"
# Observe how the agent reasons through queries
```

---

### Phase 6: Schema-Aware Production Agent ✅
**Tag**: `phase-06-production-agent`
**Date**: 2026-01-01
**Key Concepts**:
- SQL query validation
- Timeout handling
- Retry logic with exponential backoff
- Error logging and recovery
- Sample data for context enrichment
- Production-grade error handling

**Key Files**:
- `src/db.py` - Enhanced with validation, timeouts, retry logic, sample data
- `src/main.py` - Updated to use sample data in context

**What You'll Learn**:
- Production-grade database operations
- Query validation before execution (SELECT-only enforcement)
- Timeout configuration and handling
- Exponential backoff retry patterns
- Comprehensive error logging
- Enriching LLM context with sample data
- Transient error detection and recovery

**Implementation Details**:
- `validate_sql_query()` - Checks for SELECT queries, blocks dangerous keywords
- 30-second query timeout (configurable)
- Up to 3 retry attempts with exponential backoff (1s, 2s, 4s)
- Python logging for all database operations
- `get_sample_data()` - Retrieves sample rows for context
- Enhanced error messages with attempt count

**Test Command**:
```bash
cd src && uv run python main.py
# The agent now has sample data in context for better queries
# Try: "What transactions do I have?"
# Observe: Schema + sample data loaded at startup
```

---

### Phase 7: LangChain Introduction ✅
**Tag**: `phase-07-langchain`
**Date**: 2026-01-02
**Key Concepts**:
- LangChain framework abstraction
- Tool decorator pattern
- Agent creation API (LangChain 1.x)
- LangGraph compiled state graphs
- Streaming agent responses

**Key Files**:
- `src/main.py` - Complete refactor to use LangChain
- `src/pyproject.toml` - Added LangChain dependencies

**What You'll Learn**:
- Using LangChain's `AzureChatOpenAI` wrapper
- Creating tools with `@tool` decorator
- Using `create_agent()` API (new in LangChain 1.x)
- Working with LangGraph's compiled state graphs
- Streaming agent responses
- Framework abstractions vs manual implementation

**Implementation Details**:
- Replaced raw OpenAI client with `AzureChatOpenAI`
- Converted `execute_sql` function to LangChain tool
- Used `create_agent()` instead of manual tool calling loop
- Leveraged LangGraph for state management
- All Phase 6 features preserved (validation, timeouts, retry)

**Test Command**:
```bash
cd src && uv run python main.py
# Same functionality as Phase 6, now using LangChain
# Try: "What transactions do I have?"
```

---

### Phase 8: LangGraph Basics ✅
**Tag**: `phase-08-langgraph-basics`
**Date**: 2026-01-02
**Key Concepts**:
- StateGraph construction
- TypedDict state definition
- Node functions (agent, tools)
- Conditional routing (should_continue)
- add_messages reducer
- Explicit graph compilation

**Key Files**:
- `src/main.py` - Complete refactor to explicit LangGraph StateGraph
- `src/pyproject.toml` - Added langgraph dependency

**What You'll Learn**:
- Defining state with `TypedDict` and `Annotated`
- Using `add_messages` reducer for message history
- Creating node functions that modify state
- Building graphs with `StateGraph`, `add_node`, `add_edge`
- Conditional routing with `add_conditional_edges`
- Graph compilation with `graph.compile()`

**Implementation Details**:
- `AgentState(TypedDict)` - State container with messages
- `call_model` node - Invokes LLM with tools bound
- `execute_tools` node - Runs tool calls from LLM
- `should_continue` - Routes to tools or end
- Graph flow: START → agent → (tools → agent)* → END

**Graph Structure**:
```
     ┌──────────────┐
     │    START     │
     └──────┬───────┘
            │
            ▼
     ┌──────────────┐
     │    agent     │◄──────┐
     └──────┬───────┘       │
            │               │
      ┌─────┴─────┐         │
      │ tool_calls?│         │
      └─────┬─────┘         │
       yes/ \no             │
          /   \             │
         ▼     ▼            │
   ┌──────┐  ┌─────┐        │
   │tools │  │ END │        │
   └──┬───┘  └─────┘        │
      │                     │
      └─────────────────────┘
```

**Test Command**:
```bash
cd src && uv run python main.py
# Same functionality as Phase 7, now with explicit StateGraph
# Try: "What transactions do I have?"
```

---

## Upcoming Phases

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
