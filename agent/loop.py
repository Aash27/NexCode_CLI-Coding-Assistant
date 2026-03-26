import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from langchain.agents import create_agent

from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.pretty import Pretty


console = Console()

MAX_TOOL_RESULT_CHARS = 1500


SYSTEM_PROMPT = """You are NexCode, an AI coding assistant.

You have access to the following tools only. Never call a tool not in this list:
- read_file: read a file inside the workspace
- write_file: write or create a file inside the workspace
- edit_file: edit an existing file inside the workspace
- list_directory: list files and folders in a directory inside the workspace
- create_directory: create a new directory inside the workspace
- search_files: search for files by pattern inside the workspace
- tavily-search: search the web for current information
- tavily-extract: fetch and extract content from a specific URL
- query_documentation: search local documentation using RAG

Rules:
- Never call tools not listed above (e.g., open_file, read_text_file, bash, terminal).
- Never read or write files outside the workspace directory.
- Never save web search results to temp files — always answer directly from tool output.
- For web search questions, call tavily-search ONCE and answer directly from those results.
- Do NOT call tavily-extract unless the user explicitly asks to fetch a specific URL.
- After successfully editing or writing a file, STOP immediately. Do not call any more tools.
- Never call list_directory on a file path — it only works on directories.
- Never chain tavily-search and tavily-extract together in the same turn.
- For local documentation questions, use query_documentation only.
- For file operations, use read_file, write_file, list_directory, etc.
- Be concise. Keep answers short. Do not make more than one tool call per question.
- IMPORTANT: Your total response must stay under 500 words to avoid token limits.
"""


def show_reasoning(text: str):
    if text and text.strip():
        console.print()
        console.print(
            Panel(
                escape(text),
                title="[bold magenta]Agent Reasoning[/bold magenta]",
                border_style="magenta",
                expand=False,
            )
        )


def show_tool_call(tool_name: str, tool_args):
    console.print()
    console.print(
        Panel(
            Pretty(tool_args),
            title=f"[bold yellow]⚙ Tool Call: {tool_name}[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
    )


def show_tool_result(tool_name: str, result):
    preview = str(result)
    if len(preview) > 800:
        preview = preview[:800] + "\n... [truncated]"
    console.print()
    console.print(
        Panel(
            escape(preview),
            title=f"[bold green]✓ Tool Result: {tool_name}[/bold green]",
            border_style="green",
            expand=False,
        )
    )


def truncate_messages(messages: list, max_chars: int = 6000) -> list:
    """
    Trim older messages to keep total context under the token limit.
    Always preserves the system prompt and last user message.
    """
    if not messages:
        return messages

    system = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"]
    non_system = [m for m in messages if not (isinstance(m, dict) and m.get("role") == "system")]

    total = sum(len(str(m.get("content", ""))) for m in non_system)

    while total > max_chars and len(non_system) > 1:
        removed = non_system.pop(0)
        total -= len(str(removed.get("content", "")))

    return system + non_system


def select_tools(task: str, tools: list) -> list:
    task_lower = task.lower()

    doc_keywords = [
        "local documentation",
        "documentation",
        "docs",
        "query_documentation",
        "langchain agents",
        "summarize what the local documentation",
    ]

    web_keywords = [
        "search the web",
        "latest version",
        "latest features",
        "current version",
        "what is the",
        "look up",
        "find online",
        "news about",
        "recent news",
        "search for",
    ]
    url_keywords = [
        "fetch",
        "extract",
        "http://",
        "https://",
        "from the url",
        "from this url",
        "from this link",
        "summarize the content from",
        "get content from",
    ]

    if any(k in task_lower for k in doc_keywords):
        selected = [t for t in tools if t.name == "query_documentation"]
        return selected if selected else tools

    if any(k in task_lower for k in web_keywords):
        # Only tavily-search, not tavily-extract — keeps response smaller
        selected = [t for t in tools if t.name == "tavily-search"]
        return selected if selected else tools
    
    if any(k in task_lower for k in url_keywords):
        selected = [t for t in tools if t.name in {"tavily-extract", "tavily-search"}]
        return selected if selected else tools
    
    priority_tool_names = {
        "read_file",
        "write_file",
        "edit_file",
        "list_directory",
        "create_directory",
        "search_files",
        "tavily-search",
        "query_documentation",
    }
    selected = [t for t in tools if t.name in priority_tool_names]
    return selected if selected else tools


def _apply_system_message(messages: list, dynamic_system_prompt: str) -> list:
    """Ensure a single fresh system prompt (correct workspace) when resuming saved sessions."""
    messages = [m for m in messages if isinstance(m, dict)]
    if not messages:
        return [{"role": "system", "content": dynamic_system_prompt}]
    if messages[0].get("role") == "system":
        out = list(messages)
        out[0] = {"role": "system", "content": dynamic_system_prompt}
        return out
    return [{"role": "system", "content": dynamic_system_prompt}] + messages


async def run_agent(
    task: str,
    llm,
    tools,
    auto_execute: bool = False,
    messages_history: list = None,
    workspace_path: str | None = None,
):
    """
    Core agentic loop. Streams LLM responses and displays reasoning and tool calls visibly.
    """
    import os

    messages = list(messages_history) if messages_history else []

    workspace_dir = os.path.abspath(workspace_path or os.getcwd())
    dynamic_system_prompt = SYSTEM_PROMPT + (
        f"\n\nIMPORTANT: Your current working directory is: {workspace_dir}. "
        "Always use absolute paths starting with this directory when creating or modifying files!"
    )

    messages = _apply_system_message(messages, dynamic_system_prompt)

    messages.append({"role": "user", "content": task})

    # Trim context to stay under token limits for openai/gpt-oss-120b on Groq (8k TPM)
    messages = truncate_messages(messages, max_chars=6000)

    filtered_tools = select_tools(task, tools)

    console.print(f"[dim]loop.py selected tools: {[t.name for t in filtered_tools]}[/dim]")

    agent = create_agent(
        model=llm,
        tools=filtered_tools,
    )

    console.print()
    console.rule("[bold cyan]NexCode Agent Running[/bold cyan]")
    console.print(f"[bold white]User Task:[/bold white] {task}")

    full_response = ""
    current_tool = None
    streamed_text_buffer = ""

    try:
        async for msg_chunk, metadata in agent.astream(
            {"messages": messages},
            stream_mode="messages",
        ):
            if hasattr(msg_chunk, "tool_call_chunks") and msg_chunk.tool_call_chunks:
                for tc in msg_chunk.tool_call_chunks:
                    tool_name = tc.get("name")
                    tool_args = tc.get("args", "")

                    if tool_name and tool_name != current_tool:
                        current_tool = tool_name
                        show_tool_call(tool_name, tool_args)

                        if not auto_execute:
                            confirm = console.input(
                                "[bold red]Run this tool? (y/n): [/bold red]"
                            ).strip().lower()
                            if confirm != "y":
                                console.print("[red]✗ Tool execution skipped by user.[/red]")
                                return messages

            if hasattr(msg_chunk, "content") and msg_chunk.content:
                if isinstance(msg_chunk.content, str):
                    console.print(msg_chunk.content, end="", highlight=False)
                    full_response += msg_chunk.content
                    streamed_text_buffer += msg_chunk.content

            if hasattr(msg_chunk, "type") and msg_chunk.type == "tool":
                result_preview = msg_chunk.content

                # Truncate tool result before it enters agent context
                if isinstance(result_preview, str) and len(result_preview) > MAX_TOOL_RESULT_CHARS:
                    result_preview = result_preview[:MAX_TOOL_RESULT_CHARS] + "\n... [truncated]"

                show_tool_result(current_tool or "tool", result_preview)
                current_tool = None

        if streamed_text_buffer.strip():
            show_reasoning(streamed_text_buffer.strip())

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    console.print()
    console.rule("[bold cyan]Done[/bold cyan]")

    if full_response:
        messages.append({"role": "assistant", "content": full_response})

    return messages
