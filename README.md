# Library Digest

A personal research environment. Ingest PDFs, EPUBs, web pages, and YouTube videos into named topics, then have iterative conversations with Claude to build understanding. Claude is the primary interface — the browser dashboard is a management console.

The system compounds over time: notes you save (or Claude drafts) get embedded alongside source chunks, so every future session starts with your prior thinking already in scope.

---

## How it works

Everything lives in two stores:

- **SQLite (`digest.db`)** — structured data: topics, sources, tags, notes, ingest status
- **ChromaDB (`.chroma/`)** — vector index: text chunks and note embeddings, one collection per topic

Claude interacts via MCP tools. The browser dashboard talks to a FastAPI REST layer. Neither the MCP server nor the API contain business logic — both delegate to `db.py` and `store.py`.

```
You (in Claude)
    │
    ▼
server.py  (MCP — Claude's interface, runs over stdio)
    │
    ├── db.py      (SQLite: topics, sources, tags, notes)
    └── store.py   (ChromaDB: chunks + note embeddings)

Browser (http://localhost:8000)
    │
    ▼
api.py     (FastAPI REST — same db/store calls, different transport)
    │
    └── ui/index.html  (single-file SPA, no build step)

ingest.py  (PDF / EPUB / web / YouTube extractors + chunker)
```

**Key design decision:** SQLite is the system of record. Never ask ChromaDB "what sources do I have?" — that is a SQLite question. ChromaDB answers "what chunks are semantically similar to this query?"

---

## Quick start

**Prerequisites:**
- [`uv`](https://docs.astral.sh/uv/) — Python package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- The CLI of whichever AI client you want to register with must be on `PATH`. Currently only **Claude Code** uses its CLI (`claude mcp add`); the other clients (Cursor, Zed, opencode, Copilot CLI, Amp, Goose, Continue) are registered by writing their config files directly, so no CLI is required for them.

```bash
git clone <this-repo>
cd library-digest
./setup.sh
```

`setup.sh` will:
1. Install all Python dependencies via `uv sync`
2. Pre-download the embedding model (~80 MB, cached after first run)
3. Offer to register the MCP server with one or more AI clients (Claude Code, Cursor, Zed, …)

Then start the browser dashboard:

```bash
./start.sh            # opens http://localhost:8000
PORT=9000 ./start.sh  # custom port
```

---

## Core concepts

| Concept | What it is |
|---------|-----------|
| **Topic** | A named research area — e.g. `"Transformers"`, `"RAG Patterns"`. First-class entity, created before ingesting anything. |
| **Source** | A URL or file path ingested into a topic. Has a title, type, status, and chunk count. |
| **Tag** | A label applied to sources within a topic — e.g. `week-1`, `project-rag`. Tags live in SQLite so renaming/merging is instant. |
| **Chunk** | The atomic unit stored in ChromaDB. A source produces many chunks. |
| **Note** | Your own writing: observations, Claude-drafted summaries, follow-up questions. Notes are embedded into ChromaDB so they're searchable in future sessions alongside source text. |

---

## AI client integration (MCP)

`setup.sh` will present an interactive menu to register the MCP server across any combination of supported clients. To re-run it standalone:

```bash
.venv/bin/python configure_clients.py /absolute/path/to/library-digest
```

Supported clients and where their config is written:

| Client | Config file |
|--------|-------------|
| Claude Code | `~/.claude.json` (user scope, via `claude mcp add -s user` — requires the `claude` CLI on PATH) |
| GitHub Copilot CLI | `~/.copilot/mcp-config.json` |
| opencode | `~/.config/opencode/opencode.json` |
| Cursor | `~/.cursor/mcp.json` |
| Zed | `~/.config/zed/settings.json` |
| Goose | `~/.config/goose/config.yaml` |
| Amp | `~/.config/amp/settings.json` |
| Continue | `.continue/mcpServers/library-digest.json` (project-local, commit to share) |

> All clients require the absolute `.venv/bin/python` path — they start MCP servers in a clean shell where `python` may not resolve to the right environment.

### Client-specific notes

- **opencode** — uses `"type": "local"` and a combined `command` array; do not copy configs from other tools directly
- **Zed** — uses `context_servers` (not `mcpServers`); the `"source": "custom"` field is required or Zed silently ignores the entry
- **Goose** — YAML-based config; requires PyYAML (usually available transitively); uses `cmd` not `command`
- **Continue** — MCP only works in **agent mode**, not plain chat mode
- **Cursor / Amp** — both support a workspace-scoped config file (`.cursor/mcp.json` / `.amp/settings.json`) if you prefer project-local over global

---

## MCP tools

### Topics
| Tool | What it does |
|------|-------------|
| `list_topics` | List all topics with source count, chunk count, and created date |
| `create_topic` | Create a new named topic |
| `delete_topic` | Delete a topic and all its sources, notes, and embeddings |
| `get_topic_digest` | Full orientation dump — sources, notes, tags, chunk count. Call this at the start of a session. |

### Sources
| Tool | What it does |
|------|-------------|
| `ingest_source` | Index a file or URL into a topic, with optional tags |
| `list_sources` | List sources in a topic, optionally filtered by tag |
| `delete_source` | Remove a source and all its chunks |
| `get_source_outline` | Chapter/section outline with word counts |
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
| `save_note` | Save a note (optionally linked to a source), embeds it for future search |
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

YouTube ingestion fetches the video transcript. The video must have captions enabled (auto-generated captions work).

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
  visualize.py       # 3D embedding visualiser — run with `uv run visualize.py`
  configure_mcp.py   # registers the MCP server with Claude Code (user scope)
  digest.db          # SQLite database (auto-created, gitignored)
  .chroma/           # vector database (auto-created, gitignored)
```

---

## Inspecting the data

Neither `digest.db` nor `.chroma/` are readable as plain files. These tools let you browse both in a browser.

### SQLite — `digest.db`

**[sqlite-web](https://github.com/coleifer/sqlite-web)** — table browser, SQL runner, CSV/JSON import-export (4.1k stars, actively maintained)

```bash
pip install sqlite-web
sqlite_web digest.db
# → http://localhost:8080
```

**[Datasette](https://github.com/simonw/datasette)** — more powerful: filtering, full-text search, REST API, 300+ plugins (11k+ stars)

```bash
pip install datasette
datasette digest.db
# → http://localhost:8001
```

### ChromaDB — `.chroma/`

ChromaDB must be running as an HTTP server before any UI can connect to it:

```bash
chroma run --path ./.chroma
# → http://localhost:8000
```

> Note: this conflicts with the dashboard port. Stop `start.sh` first, or run ChromaDB on a different port with `--port 8001`.

**[chromadb-admin](https://github.com/flanker/chromadb-admin)** — browse collections and documents, run queries (283 stars, Docker is the easiest install)

```bash
docker run -p 3001:3001 fengzhichao/chromadb-admin
# → http://localhost:3001
# Connect to: http://host.docker.internal:8000
```

**[chromadb-ui](https://github.com/BlackyDrum/chromadb-ui)** — more feature-rich: CSV export, bulk operations, semantic search with Ollama/OpenAI, embedding stats (requires ChromaDB v2 API)

```bash
git clone https://github.com/BlackyDrum/chromadb-ui
docker compose up -d --build
# → http://localhost:8090
```

**Built-in: `visualize.py`** — interactive 3D scatter plot of a topic's embeddings, colour-coded by source. Uses t-SNE + PCA for dimensionality reduction and opens in the browser as a self-contained HTML file. No extra setup required — dependencies (`plotly`, `scikit-learn`) are already in `pyproject.toml`.

```bash
uv run visualize.py                  # prompts for topic if more than one
uv run visualize.py <topic-slug>     # jump straight to a topic
```

Hover over any point to see the chunk text, source, and location. Useful for spotting how chunks cluster, finding outliers, and checking whether sources from different topics overlap.

### Running both at once

```bash
# Tab 1 — SQLite
sqlite_web digest.db                  # → http://localhost:8080

# Tab 2 — ChromaDB HTTP server
chroma run --path ./.chroma --port 8001

# Tab 3 — ChromaDB UI (Docker)
docker run -p 3001:3001 fengzhichao/chromadb-admin
# connect to http://host.docker.internal:8001
```
