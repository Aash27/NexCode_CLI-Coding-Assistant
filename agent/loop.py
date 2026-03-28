import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from langgraph.prebuilt import create_react_agent

from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.pretty import Pretty

console = Console()

MAX_TOOL_RESULT_CHARS = 1500

SYSTEM_PROMPT = """You are NexCode, an AI coding assistant.

You have access to the following tools. Choose the RIGHT tool based on what the user is asking:

- read_file: Use when the user asks about a specific file (e.g. "what is in main.py", "summarize agent/loop.py", "show me config.py")
- write_file: Use to save any generated code or content to a file
- edit_file: Use to modify an existing file inside the workspace
- list_directory: Use when the user asks what files exist in a folder or directory
- create_directory: Use to create a new folder inside the workspace
- search_files: Use to find files by name or pattern inside the workspace
- tavily-search: Use ONLY when the user asks about something on the web, needs current information, or asks about latest versions/news
- tavily-extract: Use ONLY when the user explicitly provides a URL and wants its content fetched
- query_documentation: Use ONLY when the user explicitly says "documentation" or "docs" or asks about the local RAG knowledge base

Tool selection rules:
- Never call read_text_file, read_directory, open_file, or any other tool not listed above — they do not exist
- If the user mentions a filename (e.g. main.py, loop.py), ALWAYS use read_file first
- Never use query_documentation for questions about local project files — use read_file instead
- Never use query_documentation unless the user explicitly asks about "documentation" or "docs"
- When asked to summarize a project or explore the codebase, first call list_directory on the workspace to get file names, then read each file individually
- Never call read_file on a directory — it only works on individual file paths
- Never save web search results to files — answer directly from tool output
- Never chain tavily-search and tavily-extract in the same turn
- After writing or editing a file, STOP — do not call any more tools
- Never call list_directory on a file path — only use it on directories
- Be concise. Do not make more than one tool call per question unless absolutely necessary
- Your total response must stay under 500 words
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
    if not messages:
        return messages

    system = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"]
    non_system = [m for m in messages if not (isinstance(m, dict) and m.get("role") == "system")]

    total = sum(len(str(m.get("content", ""))) for m in non_system)

    while total > max_chars and len(non_system) > 1:
        removed = non_system.pop(0)
        total -= len(str(removed.get("content", "")))

    return system + non_system


def _apply_system_message(messages: list, dynamic_system_prompt: str) -> list:
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
    output_dir: str | None = None,
):
    messages = list(messages_history) if messages_history else []

    workspace_dir = os.path.abspath(workspace_path or os.getcwd())
    output_directory = output_dir or os.path.join(workspace_dir, "nexcode_output")
    os.makedirs(output_directory, exist_ok=True)

    dynamic_system_prompt = SYSTEM_PROMPT + (
        f"\n\nIMPORTANT: Your current working directory is: {workspace_dir}. "
        f"Save ALL generated files to: {output_directory}. "
        "Always use absolute paths starting with this directory when creating or modifying files!"
    )

    messages = _apply_system_message(messages, dynamic_system_prompt)
    messages.append({"role": "user", "content": task})
    messages = truncate_messages(messages, max_chars=6000)

    agent = create_react_agent(
        model=llm,
        tools=tools,  # pass ALL tools — LLM decides
    )

    console.print()
    console.rule("[bold cyan]NexCode Agent Running[/bold cyan]")
    console.print(f"[bold white]User Task:[/bold white] {task}")

    full_response = ""
    current_tool = None
    streamed_text_buffer = ""
    seen_tool_calls = set()

    try:
        async for msg_chunk, metadata in agent.astream(
            {"messages": messages},
            stream_mode="messages",
            config={"recursion_limit": 10},
        ):
            if hasattr(msg_chunk, "tool_call_chunks") and msg_chunk.tool_call_chunks:
                for tc in msg_chunk.tool_call_chunks:
                    tool_name = tc.get("name")
                    tool_args = tc.get("args", "")

                    if tool_name and tool_name != current_tool:
                        call_key = (tool_name, str(tool_args))
                        if call_key in seen_tool_calls:
                            console.print("[yellow]⚠ Duplicate tool call detected — stopping loop.[/yellow]")
                            break
                        seen_tool_calls.add(call_key)
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
