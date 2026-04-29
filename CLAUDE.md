# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MyAgent** is a LangGraph-based conversational agent that intelligently routes user queries to specialized tools. It uses a router-based architecture with Corrective RAG (Retrieval Augmented Generation), web search capabilities, and local file operations. The system supports multimodal input (text, images, audio, video) and offers both CLI and Gradio UI interfaces.

## Architecture Overview

The agent follows a **router pattern** with conditional routing and relevance checking:

```
User Input → Router (Intent Analysis) → 4 Node Paths
    ├─ rag_node: Local document search with relevance evaluation
    ├─ web_search_node: Internet search for current information
    ├─ other_tools_node: File operations and tool execution
    └─ direct_chat_node: Simple conversation without tools
         ↓
    generate_node: Synthesize final response
```

### Key Architectural Components

1. **Router Node** (`agent.py:route_query`): Uses LLM to classify user intent into one of four categories
2. **RAG System** (`tools/rag.py`): 
   - Vectorizes PDFs in `Docs/` folder using HuggingFace embeddings (`jhgan/ko-sroberta-multitask`)
   - Stores embeddings in FAISS index with automatic hash-based invalidation
   - Relevance filtering via LLM evaluation before passing to generate node
   - Auto-detects file changes and rebuilds index if needed
3. **LLM Factory** (`llm_factory.py`): Abstracts LLM provider switching (Ollama, OpenAI, Gemini, vLLM) via `.env` config
4. **Search Tools** (`tools/search.py`): Multi-provider web search (DuckDuckGo, Tavily, Google)
5. **File Operations** (`tools/file_ops.py`): Read/write local files

### Configuration

All configuration is environment-based via `.env` file (copy from `.env.example`):

- **LLM_PROVIDER**: `ollama` (default), `openai`, `gemini`, or `vllm`
- **OLLAMA_MODEL**, **OPENAI_API_KEY**, **GOOGLE_API_KEY**: Provider-specific credentials
- **VLLM_MODEL**, **VLLM_BASE_URL**: vLLM server settings (e.g., `gemma4-26B-A4B-it`, `http://10.158.2.58:18901/v1`)
- **SEARCH_PROVIDER**: `duckduckgo`, `tavily`, or `google` (web search backend)
- **USE_STREAMING**: `true` for real-time output, `false` for buffered
- **LANGSMITH_***: Optional debugging/tracing configuration

## Development Setup

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your LLM provider and API keys
```

## Running the Agent

### CLI Interface
```bash
python main_agent_cli.py
```
Features:
- Interactive terminal interface with streaming output
- Shows node execution status (🔍 RAG search, 🌐 Web search, etc.)
- Type `quit`, `exit`, or `q` to terminate
- Uses recursion limit of 5 to prevent infinite loops

### Gradio UI Interface
```bash
python main_agent_ui.py
```
Features:
- Web-based chat interface at `http://localhost:7860`
- File upload support (PDFs, images, audio, video)
- Text display limit (4000 chars) for UI performance
- Automatic file classification and multimodal processing
- Dynamic Docs folder refresh button

## Key Files & Their Responsibilities

| File | Purpose |
|------|---------|
| `agent.py` | Core LangGraph workflow definition, routing logic, and node implementations |
| `main_agent_cli.py` | CLI entry point with streaming event handling |
| `main_agent_ui.py` | Gradio UI implementation with file upload and multimodal support |
| `llm_factory.py` | LLM provider abstraction (Ollama/OpenAI/Gemini) |
| `tools/rag.py` | FAISS vectorstore management, PDF loading, hash-based cache invalidation |
| `tools/search.py` | Web search tool with provider switching |
| `tools/file_ops.py` | File read/write operations |
| `.env` | Runtime configuration (LLM choice, API keys, search provider) |
| `Docs/` | Local PDF documents indexed for RAG |
| `workspace/` | Temporary file storage for UI uploads |
| `.faiss_index/` | Cached FAISS vectorstore (auto-regenerated if docs change) |

## Common Development Tasks

### Test the Router Classification
The router uses strict LLM evaluation to choose between `rag`, `web_search`, `other_tools`, or `direct_chat`. To debug routing:
1. Check `agent.py:route_query` for the routing prompt logic
2. Test routing with simple queries that clearly map to each category
3. Monitor streaming output in CLI to see which node was selected

### Add a New Tool
1. Create tool function in appropriate `tools/` file
2. Export via `langchain_core.tools.tool` decorator
3. Import and wire into `other_tools_node` in `agent.py`
4. Update router prompt in `route_query` if routing behavior should change

### Modify RAG Behavior
- **Change embedding model**: Update `tools/rag.py` → `HuggingFaceEmbeddings(model_name="...")`
- **Change text chunk size**: Adjust `RecursiveCharacterTextSplitter` parameters in `_build_vectorstore`
- **Add file type support**: Modify `tools/rag.py` document loader (currently PDF-only)

### Switch LLM Providers
Edit `.env`:
```bash
# Use Ollama (local)
LLM_PROVIDER=ollama
OLLAMA_MODEL=gemma4:e4b

# Use OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Use Gemini
LLM_PROVIDER=gemini
GOOGLE_API_KEY=...
```

### Debug Agent Behavior
1. **Enable LangSmith tracing**: Set `LANGCHAIN_TRACING_V2=true` and API key in `.env`
2. **Check streaming output**: CLI shows which node is executing
3. **Monitor RAG cache**: Delete `.faiss_index/` to force index rebuild
4. **Test recursion limit**: Intentionally create loops to verify `recursion_limit: 5` protection

## Important Implementation Details

### Multimodal Support (UI)
- Images, audio, and video are passed as base64-encoded data structures to LLM
- Text files are truncated to 4000 chars to prevent UI overflow
- PDF text is extracted before upload (not passed raw)

### Input Sanitization
- User input capped at 2000 chars in `agent.py:_sanitize`
- Prompt delimiters (`<|`, `|>`) are escaped to prevent prompt injection
- Multimodal content (images, audio) is validated before processing

### FAISS Index Auto-Invalidation
- On startup, computes MD5 hash of all PDF filenames and modification times
- Compares with saved hash in `.faiss_index/docs_hash.txt`
- If files added/modified/deleted, index is automatically rebuilt
- Prevents stale search results after doc updates

### Fallback Strategy
If RAG finds documents but LLM deems them irrelevant (Relevance Check fails), the agent **automatically falls back to web search** instead of using potentially wrong information.

## Notes for Future Development

- **Thread safety**: RAG vectorstore uses locks (`threading.Lock`) for concurrent access
- **Session isolation**: CLI uses `thread_id: "1"`, UI generates unique UUID per session
- **Error handling**: `GraphRecursionError` is caught and user receives graceful message instead of crash
- **Performance**: HuggingFace embedding model chosen for speed over maximum accuracy (suitable for local deployment)
