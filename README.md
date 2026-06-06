# Library Digest

Index PDFs, EPUBs, web pages, and YouTube videos into named topics, then
research them through Claude or a local browser dashboard.

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
./start.sh            # opens http://localhost:8000
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
> in a clean shell where `python` may not have the project dependencies.

You can also re-run the config step standalone:

```bash
.venv/bin/python configure_mcp.py /absolute/path/to/library-digest
```

---

## MCP tools

After restarting Claude Code, the following tools are available:

### Topics
| Tool | What it does |
|------|-------------|
| `list_topics` | List all topics with source count, chunk count, and created date |
| `create_topic` | Create a new named topic |
| `delete_topic` | Delete a topic and all its sources, notes, and embeddings |
| `get_topic_digest` | Full orientation dump for a topic — sources, notes, tags, chunk count |

### Sources
| Tool | What it does |
|------|-------------|
| `ingest_source` | Index a file or URL into a topic, with optional tags |
| `list_sources` | List sources in a topic, optionally filtered by tag |
| `delete_source` | Remove a source and all its chunks |
| `get_source_outline` | Chapter/section outline of a source with word counts |
| `get_source_text` | Full text of a source or a single chapter |

### Search
| Tool | What it does |
|------|-------------|
| `search_topic` | Semantic search within a topic, with optional tag filter |
| `search_all` | Semantic search across all topics |

### Tags
| Tool | What it does |
|------|-------------|
| `list_tags` | List all tags in a topic with source counts |
| `tag_source` | Add tags to a source |
| `untag_source` | Remove tags from a source |
| `rename_tag` | Rename a tag across all sources in a topic |
| `merge_tags` | Move all sources from one tag to another |

### Notes
| Tool | What it does |
|------|-------------|
| `save_note` | Save a note to a topic (optionally linked to a source), embeds it for future search |
| `list_notes` | List all notes for a topic |
| `get_note` | Get the full text of a note |
| `edit_note` | Update a note and re-embed it |
| `delete_note` | Delete a note |

---

## Supported sources

| Type | How to ingest |
|------|--------------|
| PDF | Absolute file path ending in `.pdf` |
| EPUB | Absolute file path ending in `.epub` |
| Plain text / Markdown | Absolute file path (any other extension) |
| Web page / article | Any `https://` URL |
| YouTube video | `https://www.youtube.com/watch?v=…` or `https://youtu.be/…` |

YouTube ingestion fetches the video transcript. The video must have captions
enabled (auto-generated captions work).

---

## File layout

```
library-digest/
  db.py              # SQLite data access (topics, sources, tags, notes)
  store.py           # ChromaDB read/write (chunks + note embeddings)
  ingest.py          # extraction + chunking (pdf, epub, web, video, text)
  server.py          # MCP server — Claude's interface, runs over stdio
  api.py             # FastAPI REST server — browser dashboard's interface
  ui/index.html      # browser dashboard, single file, no build step
  pyproject.toml
  setup.sh           # one-shot setup: deps, embedding model, MCP config
  start.sh           # start the dashboard at http://localhost:8000
  configure_mcp.py   # safely writes the MCP entry to ~/.claude/settings.json
  digest.db          # SQLite database (auto-created, gitignored)
  .chroma/           # vector database (auto-created, gitignored)
```

---

## Example Claude session

```
You: create a topic called "Transformers"

Claude: [calls create_topic] Created topic "Transformers".

You: ingest https://www.youtube.com/watch?v=... into Transformers, tag it week-1

Claude: [calls ingest_source] Ingested "Attention Is All You Need (Explained)"
        — 12 chunks added.

You: what does the video say about positional encoding?

Claude: [calls search_topic] …synthesised answer with inline citations…

You: save a note with my key takeaways

Claude: [calls save_note] Note saved — it's now searchable in future sessions.
```
