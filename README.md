# NexCode

> **An autonomous AI coding assistant for your terminal** — reads your codebase, searches the web, queries local documentation, and edits files using natural language.

---

## Features

- **Agentic loop** built with LangGraph ReAct
- **Multi-provider support** — Groq, Ollama, OpenAI, Anthropic
- **Filesystem MCP** — read, write, edit, list files
- **Tavily MCP** — live web search and URL extraction
- **RAG MCP** — local documentation search with HyDE retrieval and citations
- **Rich CLI** — streaming output, tool panels, session history
- **Confirm mode** — approve every tool call before execution
- **Auto mode** — fully autonomous execution

---

## Project Structure

```text
nexcode/
├── agent/
│   ├── __init__.py
│   ├── loop.py           # Agentic loop, tool routing, streaming
│   └── providers.py      # LLM provider setup
├── config/
│   ├── __init__.py
│   └── settings.py       # Environment variables and constants
├── docs_source/          # Place your .txt and .md docs here
├── mcp_client/
│   ├── __init__.py
│   └── client.py         # MultiServerMCPClient configuration
├── rag_server/
│   ├── __init__.py
│   ├── ingest.py         # Ingest docs into ChromaDB
│   ├── retriever.py      # HyDE retrieval + citations
│   └── server.py         # FastMCP RAG server (SSE)
├── planning/
│   └── architecture.md
├── .env
├── .gitignore
├── main.py               # CLI entry point
├── README.md
└── requirements.txt
```

---

## Requirements

| Requirement       | Notes                                                |
| ----------------- | ---------------------------------------------------- |
| Python 3.11       | Required                                             |
| Node.js + npm     | Required for MCP servers                             |
| Groq API key      | Free at [console.groq.com](https://console.groq.com) |
| Tavily API key    | Free at [tavily.com](https://tavily.com)             |
| Ollama            | Optional — for local models                          |
| OpenAI API key    | Optional                                             |
| Anthropic API key | Optional                                             |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/nexcode.git
cd nexcode
```

### 2. Create a Python environment

```bash
# Using conda (recommended)
conda create -n nexcode python=3.11 -y
conda activate nexcode

# Or using venv
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate  # macOS/Linux
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install MCP packages

```bash
npm install -g @modelcontextprotocol/server-filesystem
npm install -g tavily-mcp
```

### 5. Configure environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
OPENAI_API_KEY=your_openai_api_key_here       # optional
ANTHROPIC_API_KEY=your_anthropic_api_key_here  # optional
```

### 6. Add documentation for RAG

Place `.txt` or `.md` files inside `docs_source/`, then run:

```bash
python rag_server/ingest.py
```

This builds the local ChromaDB vector database used by the RAG server.

---

## Running NexCode

NexCode uses three MCP servers. The Filesystem and Tavily servers start automatically, but the **RAG server must be started manually** in a separate terminal.

### Terminal 1 — Start the RAG Server

```bash
conda activate nexcode
python rag_server/server.py
```

Expected output:

```
INFO:     Started server process
INFO:     Uvicorn running on http://127.0.0.1:8001 (Press CTRL+C to quit)
```

> ⚠️ Keep this terminal open. The RAG server must be running **before** starting the main app.

### Terminal 2 — Start NexCode

```bash
conda activate nexcode
python main.py
```

---

## 🖥️ Startup Flow

At startup, NexCode will prompt you for configuration. Press **Enter** to accept defaults:

```text
Provider [groq/ollama/openai/anthropic] (groq):
Model (openai/gpt-oss-120b):
Mode [auto/confirm] (confirm):
Resume previous session? [y/n] (n):
Workspace path (\...\nexcode):
```

### Recommended model

```text
openai/gpt-oss-120b
```

---

## Example Prompts

```text
Read main.py and summarize what it does
```

```text
Find errors in merge_sort.py and fix them
```

```text
Create a Python file called calculator.py with add, subtract, multiply, and divide functions
```

```text
Search the web for LangGraph latest features
```

```text
Fetch and summarize the content from https://pypi.org/project/langgraph/
```

```text
Summarize what the local documentation says about LangChain agents
```

```text
Search the web for LangChain ReAct best practices and write the result to research.md
```

---

## MCP Servers

| Server         | Transport | Port     | Started by | Used for                             |
| -------------- | --------- | -------- | ---------- | ------------------------------------ |
| Filesystem MCP | stdio     | —        | Auto       | Read, write, edit, list files        |
| Tavily MCP     | stdio     | —        | Auto       | Web search, URL extraction           |
| RAG MCP        | SSE       | **8001** | **Manual** | Local documentation + HyDE retrieval |

### Changing the RAG server port

If port `8001` is already in use, update it in two places:

**`rag_server/server.py`**:

```python
mcp.run(transport="sse", host="127.0.0.1", port=8002)
```

**`mcp_client/client.py`**:

```python
"url": "http://127.0.0.1:8002/sse",
```

---

## RAG — How It Works

```
User query
    │
    ▼
HyDE rewrite (Groq llama-3.1-8b-instant)
    │
    ▼
ChromaDB vector search
(original query + rewritten query)
    │
    ▼
Top-K chunks retrieved with metadata
    │
    ▼
Final answer with inline citations [filename, chunk_id]
```

---

## Execution Modes

| Mode      | Behavior                                                         |
| --------- | ---------------------------------------------------------------- |
| `confirm` | Asks **y/n** before every tool call — safe for reviewing changes |
| `auto`    | Executes all tools automatically — faster, no interruptions      |

---

## Session Persistence

Conversation history is saved to:

```text
.nexcode_session.json
```

Type `clear` at the prompt to reset it, or select **n** when asked to resume at startup.

---

## Troubleshooting

| Issue                                    | Fix                                                                     |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `query_documentation` missing from tools | RAG server is not running — start it with `python rag_server/server.py` |
| Connection refused on port 8001          | Port is in use — change it in `server.py` and `client.py`               |
| Agent freezes on `query_documentation`   | You are using an old stdio version of `server.py` — switch to SSE       |
| `npx` not found                          | Install Node.js and restart your terminal                               |
| Token limit exceeded (413 error)         | Type `clear` to reset session history, or shorten your prompt           |
| Vector DB not found                      | Run `python rag_server/ingest.py` first                                 |
| `conda` not recognized                   | Run `conda init` and restart your terminal                              |
| Missing Python modules                   | Activate your environment and run `pip install -r requirements.txt`     |
| Model tries to call `open_file`          | Switch to `llama-3.3-70b-versatile` for better tool-call compliance     |

---

## Providers

| Provider    | Example Model                | Notes                      |
| ----------- | ---------------------------- | -------------------------- |
| `groq`      | `llama-3.3-70b-versatile`    | Free API key — recommended |
| `ollama`    | `qwen2.5:7b`                 | Fully local, no key needed |
| `openai`    | `gpt-4o`, `gpt-4o-mini`      | Paid API key required      |
| `anthropic` | `claude-3-5-sonnet-20241022` | Paid API key required      |

---
