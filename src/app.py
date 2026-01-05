"""
fin_chatbot - Web Interface

Phase 12: Gradio web interface with structured artifacts UI.
- Chat panel on the left
- Tabbed artifacts panel on the right (Data, Chart, Details)
"""

import gradio as gr
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langfuse.callback import CallbackHandler
from dotenv import load_dotenv
import os
import uuid

import db
import artifacts

# Import the multi-agent system from main
from main import create_multi_agent_system

load_dotenv()

# Global state for the agent
agent_system = None
schema_info = ""
sample_data_info = ""
langfuse_handler = None


def initialize_agent():
    """Initialize the multi-agent system."""
    global agent_system, schema_info, sample_data_info, langfuse_handler

    # Load schema
    try:
        schema_info = db.get_table_schema()
        table_names = db.get_table_names()
        sample_data_parts = []
        for table_name in table_names:
            sample_data = db.get_sample_data(table_name, limit=2)
            sample_data_parts.append(sample_data)
        sample_data_info = "\n".join(sample_data_parts)
    except Exception as e:
        print(f"Warning: Could not load schema: {e}")
        schema_info = "Schema unavailable"
        sample_data_info = ""

    # Initialize LLM
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        api_version="2024-02-01",
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        temperature=0,
    )

    # Create agent
    agent_system = create_multi_agent_system(llm, schema_info, sample_data_info)

    # Initialize Langfuse callback (optional)
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            session_id = f"gradio-{uuid.uuid4().hex[:8]}"
            langfuse_handler = CallbackHandler(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                session_id=session_id,
                user_id="gradio-user",
                metadata={"interface": "gradio"},
            )
            print(f"✓ Langfuse tracing enabled (session: {session_id})")
        except Exception as e:
            print(f"⚠ Langfuse initialization failed: {e}")

    print("Agent initialized successfully!")


def chat(message: str, history: list) -> tuple:
    """Process a chat message and return updated history with artifacts.

    Args:
        message: User's message
        history: Chat history (list of message dicts with 'role' and 'content')

    Returns:
        Tuple of (history, table_data, chart_path, sql_code, details_info, csv_path)
    """
    global agent_system

    # Default empty table for error cases
    empty_table = {"headers": [], "data": []}

    if agent_system is None:
        history.append({"role": "assistant", "content": "Error: Agent not initialized."})
        return (history, empty_table, None, "", "", None)

    # Build LangChain messages from history
    messages: list[BaseMessage] = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    # Add current message
    messages.append(HumanMessage(content=message))

    try:
        # Build config with optional Langfuse callback
        config = {}
        if langfuse_handler:
            config["callbacks"] = [langfuse_handler]

        # Run the multi-agent system
        result = agent_system.invoke({
            "messages": messages,
            "user_question": "",
            "needs_sql": False,
            "needs_viz": False,
            "sql_query": None,
            "sql_results": None,
            "chart_type": None,
            "chart_path": None,
            "final_response": None,
            "error": None,
            # Artifact fields
            "table_columns": None,
            "table_rows": None,
            "row_count": None,
            "show_table": False,
        }, config=config if config else None)

        # Extract results
        response = result.get("final_response", "No response generated.")
        chart_path = result.get("chart_path")
        sql_query = result.get("sql_query") or ""
        table_columns = result.get("table_columns") or []
        table_rows = result.get("table_rows") or []
        row_count = result.get("row_count") or 0
        show_table = result.get("show_table", False)

        # Update history with new messages
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})

        # Prepare table data for gr.Dataframe
        if table_columns and table_rows:
            table_data = {"headers": table_columns, "data": table_rows}
        else:
            table_data = {"headers": [], "data": []}

        # Prepare details info
        details_parts = []
        if row_count > 0:
            if row_count > len(table_rows):
                details_parts.append(f"**Rows:** {len(table_rows)} of {row_count} (truncated)")
            else:
                details_parts.append(f"**Rows:** {row_count}")
        if show_table:
            details_parts.append("**Table visible:** Yes")
        details_info = "\n\n".join(details_parts)

        # Create CSV temp file for download
        csv_path = None
        if table_columns and table_rows:
            csv_path = artifacts.table_to_csv_tempfile(table_columns, table_rows)

        return (history, table_data, chart_path, sql_query, details_info, csv_path)

    except Exception as e:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": f"Error: {str(e)}"})
        return (history, empty_table, None, "", f"**Error:** {str(e)}", None)


# Create Gradio interface
with gr.Blocks(title="Finance Assistant") as demo:
    gr.Markdown(
        """
        # Finance Assistant

        Ask questions about your financial transactions. I can:
        - Query your transaction data
        - Generate visualizations (charts)
        - Provide insights and summaries

        **Examples:**
        - "What's my total spending?"
        - "Show my expenses by category"
        - "List last 10 transactions"
        """
    )

    with gr.Row():
        # Left column: Chat
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                label="Chat",
                height=450,
            )
            msg = gr.Textbox(
                label="Your question",
                placeholder="Ask about your transactions...",
                lines=1,
            )
            with gr.Row():
                submit_btn = gr.Button("Send", variant="primary")
                clear_btn = gr.Button("Clear")

        # Right column: Tabbed artifacts
        with gr.Column(scale=1):
            with gr.Tabs():
                with gr.TabItem("Data"):
                    data_table = gr.Dataframe(
                        label="Query Results",
                        interactive=False,
                        wrap=True,
                    )
                    csv_download = gr.File(
                        label="Download CSV",
                        visible=True,
                    )

                with gr.TabItem("Chart"):
                    chart_output = gr.Image(
                        label="Visualization",
                        height=400,
                    )

                with gr.TabItem("Details"):
                    sql_code = gr.Code(
                        label="SQL Query",
                        language="sql",
                        lines=8,
                    )
                    details_info = gr.Markdown(
                        label="Info",
                        value="",
                    )

    def user_submit(user_message, history):
        """Handle user message submission."""
        if not user_message.strip():
            # Return current state unchanged
            empty_table = {"headers": [], "data": []}
            return "", history, empty_table, None, "", "", None

        # Get response with all artifacts
        result = chat(user_message, history)
        updated_history, table_data, chart_path, sql_query, details, csv_path = result

        return "", updated_history, table_data, chart_path, sql_query, details, csv_path

    def clear_all():
        """Clear all outputs."""
        empty_table = {"headers": [], "data": []}
        return [], empty_table, None, "", "", None

    # Connect events
    msg.submit(
        user_submit,
        inputs=[msg, chatbot],
        outputs=[msg, chatbot, data_table, chart_output, sql_code, details_info, csv_download],
    )

    submit_btn.click(
        user_submit,
        inputs=[msg, chatbot],
        outputs=[msg, chatbot, data_table, chart_output, sql_code, details_info, csv_download],
    )

    clear_btn.click(
        clear_all,
        outputs=[chatbot, data_table, chart_output, sql_code, details_info, csv_download],
    )


def main():
    """Launch the Gradio web interface."""
    print("=" * 60)
    print("fin_chatbot - Web Interface (Phase 12: Artifacts UI)")
    print("=" * 60)
    print("Initializing multi-agent system...")

    initialize_agent()

    # Get authentication credentials from environment
    auth_user = os.getenv("GRADIO_AUTH_USER")
    auth_pass = os.getenv("GRADIO_AUTH_PASS")

    # Configure auth tuple (or None if not set)
    auth = (auth_user, auth_pass) if auth_user and auth_pass else None

    print("\nStarting web server...")
    if auth:
        print("Authentication enabled")
    print("Open http://localhost:7860 in your browser")
    print("=" * 60)

    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        auth=auth,
    )


if __name__ == "__main__":
    main()
