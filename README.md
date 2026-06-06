# Library Digest

Index PDFs, EPUBs, web pages, and YouTube videos, then query them through
Claude or a local browser dashboard.

## Quick start

```bash
git clone <this-repo>
cd library-digest
./setup.sh
```

`setup.sh` will:
1. Install all Python dependencies via `uv sync`
2. Pre-download the embedding model (~80 MB, cached after first run)
3. Offer to register the MCP server in `~/.claude/settings.json`

Then start the browser dashboard:

```bash
./start.sh          # opens http://localhost:8000
PORT=9000 ./start.sh  # custom port
```

---

## Claude Code integration (MCP)

`setup.sh` handles this automatically, but if you prefer to do it manually,
add the following to `~/.claude/settings.json` and restart Claude Code:

```json
"mcpServers": {
  "library-digest": {
    "command": "/absolute/path/to/library-digest/.venv/bin/python",
    "args": ["/absolute/path/to/library-digest/server.py"]
  }
}
```

> Use the absolute `.venv/bin/python` path — Claude Code starts MCP servers
> in a clean shell where `python` may not have the dependencies installed.

You can also re-run the config step standalone:

```bash
python configure_mcp.py /absolute/path/to/library-digest
```

After restarting Claude Code, five tools become available:

| Tool | What it does |
|------|-------------|
| `ingest_source` | Index a file or URL into a library |
| `search_library` | Semantic search across library materials |
| `list_libraries` | Show all indexed libraries |
| `list_sources` | Show all sources in a library |
| `get_module_map` | Outline a library's chapter structure |

---

## Supported sources

| Type | Example |
|------|---------|
| PDF | `/path/to/notes.pdf` |
| EPUB | `/path/to/book.epub` |
| Plain text / Markdown | `/path/to/notes.md` |
| Web page | `https://example.com/article` |
| YouTube video | `https://www.youtube.com/watch?v=…` |

YouTube ingestion requires a public video with captions enabled.

---

## File layout

```
library-digest/
  ingest.py          # extraction + chunking (pdf, epub, web, video, text)
  store.py           # ChromaDB read/write
  server.py          # MCP server (Claude's interface, stdio)
  api.py             # FastAPI REST server (browser's interface)
  ui/index.html      # browser dashboard, no build step
  pyproject.toml
  setup.sh           # one-shot setup script
  start.sh           # start the dashboard
  configure_mcp.py   # safely writes ~/.claude/settings.json
  .chroma/           # vector database (auto-created, gitignored)
```

---

## Example Claude conversation

```
You: ingest https://example.com/gradient-descent into "ML Notes" module week-4
Claude: [calls ingest_source] Ingested 'Gradient Descent Notes' — 89 chunks added.

You: explain gradient descent using my week-4 materials
Claude: [calls search_library] …synthesised answer with inline citations…
```
