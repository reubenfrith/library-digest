# Library Digest — Implementation Spec

## What we're building

A personal research environment. You pull in sources on a topic (articles, PDFs, videos, EPUBs), then have iterative conversations with Claude to build understanding — the way Jeremy Howard's Solveit platform works, but for your own reading list. Claude is the primary interface. The browser is a management console.

The system compounds over time: notes you take or Claude drafts get embedded alongside source chunks, so every future session on a topic starts with your prior thinking already available.

---

## Core concepts

| Concept | What it is |
|---------|-----------|
| **Topic** | A named research area, e.g. "Embedding Models for RAG". First-class entity, persisted on creation. |
| **Source** | A URL or file path ingested into a topic. Has a title, type, ingest status, chunk count. |
| **Tag** | A label applied to one or more sources within a topic, e.g. `week-1`, `project-rag`. First-class entity — not a freeform string. |
| **Chunk** | The atomic unit stored in ChromaDB. A source produces many chunks. |
| **Note** | Your own writing: observations, Claude-drafted summaries, things to follow up. Embedded into ChromaDB so they're searchable in future sessions. |

---

## Data model

### SQLite (`digest.db`)

```sql
CREATE TABLE topics (
    id          INTEGER PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,   -- "embedding-models-for-rag"
    name        TEXT NOT NULL,          -- "Embedding Models for RAG"
    description TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE sources (
    id            INTEGER PRIMARY KEY,
    topic_id      INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    source_ref    TEXT NOT NULL,        -- original path or URL (dedup key)
    source_title  TEXT DEFAULT '',
    source_type   TEXT DEFAULT '',      -- pdf | epub | web | video | text
    ingest_status TEXT DEFAULT 'pending', -- pending | done | error
    error_message TEXT DEFAULT '',
    ingested_at   TEXT,
    chunk_count   INTEGER DEFAULT 0,
    UNIQUE(topic_id, source_ref)
);

CREATE TABLE tags (
    id       INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    UNIQUE(topic_id, name)
);

CREATE TABLE source_tags (
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (source_id, tag_id)
);

CREATE TABLE notes (
    id          INTEGER PRIMARY KEY,
    topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    source_id   INTEGER REFERENCES sources(id) ON DELETE SET NULL,  -- nullable
    body        TEXT NOT NULL,
    chroma_id   TEXT,                   -- ID of the embedded chunk in ChromaDB
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

### ChromaDB

One collection per topic (slug = collection name). Stores chunks and notes together.

Each document's metadata:
```python
{
    "topic":           str,   # topic slug
    "source_id":       int,   # SQLite sources.id (0 for notes)
    "source_ref":      str,   # original URL or path
    "source_type":     str,   # pdf | epub | web | video | text | note
    "kind":            str,   # "chunk" or "note"
    "chapter":         str,
    "chapter_index":   int,
    "chunk_index":     int,
    "page":            int,
    "timestamp_seconds": int,
}
```

Notes use `kind="note"`, `source_type="note"`, `source_id=0`, `source_ref=""`.

---

## File layout

```
library-digest/
  db.py           # NEW — SQLite DAO
  store.py        # KEEP + extend — ChromaDB layer
  ingest.py       # KEEP — extractors + chunker, untouched
  server.py       # REWRITE — new MCP tools
  api.py          # UPDATE — new routes matching new model
  ui/index.html   # UPDATE — topic/tag/note UI
  configure_mcp.py
  setup.sh
  start.sh
  pyproject.toml
  digest.db       # auto-created on first run
  .chroma/        # auto-created on first run
```

---

## `db.py` — SQLite DAO

Handles all structured data. `store.py` handles all vector operations. They never call each other — `server.py` and `api.py` coordinate between them.

```python
# Key functions to implement:

# Schema
def init_db(db_path: str) -> sqlite3.Connection

# Topics
def create_topic(conn, name, description="") -> dict
def get_topic(conn, slug) -> dict | None
def list_topics(conn) -> list[dict]
def delete_topic(conn, slug) -> None          # caller must also drop ChromaDB collection

# Sources
def register_source(conn, topic_id, source_ref, source_type="") -> dict
def update_source_done(conn, source_id, title, source_type, chunk_count) -> None
def update_source_error(conn, source_id, error_message) -> None
def get_source(conn, topic_id, source_ref) -> dict | None
def list_sources(conn, topic_id, tag_name="") -> list[dict]
def delete_source_record(conn, source_id) -> None

# Tags
def get_or_create_tag(conn, topic_id, name) -> dict
def list_tags(conn, topic_id) -> list[dict]
def set_source_tags(conn, source_id, tag_ids: list[int]) -> None
def rename_tag(conn, tag_id, new_name) -> None
def merge_tags(conn, topic_id, source_tag_name, target_tag_name) -> None
def delete_tag(conn, tag_id) -> None

# Notes
def create_note(conn, topic_id, body, source_id=None) -> dict
def update_note(conn, note_id, body) -> dict
def set_note_chroma_id(conn, note_id, chroma_id) -> None
def list_notes(conn, topic_id) -> list[dict]
def get_note(conn, note_id) -> dict | None
def delete_note(conn, note_id) -> None
```

---

## `store.py` — changes

Add these to the existing file (keep everything else):

```python
def delete_collection(client, topic_slug: str) -> None
    # client.delete_collection(topic_slug)

def get_chunks_for_source(collection, source_id: int) -> list[dict]
    # where filter on source_id, ordered by chapter_index/chunk_index

def delete_chunks_for_source(collection, source_id: int) -> None
    # get IDs via where filter, then collection.delete(ids=...)
    # NOTE: replaces the current source_ref-based delete

def get_chunks_ordered(collection, source_id: int, chapter: str = "") -> list[dict]
    # for get_source_outline and get_source_text
    # optional chapter filter

def search_collection(collection, query, top_k=8, tag_names: list[str] = []) -> list[dict]
    # same as current search() but returns kind + source_id in results
```

The current `delete_source` (by `source_ref`) becomes `delete_chunks_for_source` (by `source_id`). The `source_id` is stored in chunk metadata, making deletes exact and fast.

---

## MCP tools (`server.py`)

These are the primary interface. Design principle: give Claude everything it needs to be a useful research partner without round-tripping back to the user for basic orientation.

### Topic tools

```python
list_topics() -> str
"""List all topics with name, slug, source count, chunk count, created date."""

create_topic(name: str, description: str = "") -> str
"""Create a new topic. Persists immediately — no need to ingest first."""

delete_topic(topic: str) -> str
"""Delete a topic and all its sources, notes, and embeddings. Irreversible."""

get_topic_digest(topic: str) -> str
"""
Full orientation dump for a topic. Returns:
- Topic name and description
- All sources (type, tags, title, chunk count, status)
- All notes (created_at, body preview, source association)
- All tags and how many sources use each
- Total chunk count
Call this at the start of a research session to orient yourself.
"""
```

### Source tools

```python
ingest_source(path_or_url: str, topic: str, tags: list[str] = []) -> str
"""
Ingest a source into a topic.
- Registers source in SQLite with status=pending
- Runs extractor + chunker
- Deletes any existing chunks for this source_ref (safe re-ingest)
- Writes chunks to ChromaDB
- Updates SQLite with status=done, chunk_count, source_title
- Creates any new tags, associates them with the source
Returns: source title and chunk count.
"""

list_sources(topic: str, tag: str = "") -> str
"""List sources in a topic, optionally filtered by tag. Reads from SQLite."""

delete_source(topic: str, source_ref: str) -> str
"""Remove a source and all its chunks from a topic."""

get_source_outline(topic: str, source_ref: str) -> str
"""
Chapter/section outline of a single source.
Returns chapter names with word counts and first-sentence previews.
Useful for deciding which part of a source to read.
"""

get_source_text(topic: str, source_ref: str, chapter: str = "") -> str
"""
Return the full text of a source, or a single chapter if specified.
Concatenates chunks in chapter_index/chunk_index order.
Use this to read a full article or section — not just search snippets.
Cap at ~8000 words; return a truncation notice if longer.
"""
```

### Search tools

```python
search_topic(query: str, topic: str, tags: list[str] = [], top_k: int = 8) -> str
"""
Semantic search within a topic.
Optional tag filter — pass one or more tags to scope to those sources.
Returns chunks and notes together, labelled by kind.
Format: [N] Title — location (tag) \\n text
"""

search_all(query: str, top_k_per_topic: int = 3) -> str
"""
Search across all topics. Use for cross-topic discovery and rabbit holes.
Returns results grouped by topic, sorted by score within each group.
top_k_per_topic capped at 5.
"""
```

### Tag tools

```python
list_tags(topic: str) -> str
"""List all tags in a topic with source counts."""

tag_source(topic: str, source_ref: str, tags: list[str]) -> str
"""Add tags to a source. Creates tags if they don't exist."""

untag_source(topic: str, source_ref: str, tags: list[str]) -> str
"""Remove tags from a source."""

rename_tag(topic: str, old_name: str, new_name: str) -> str
"""Rename a tag across all sources in the topic."""

merge_tags(topic: str, source_tag: str, target_tag: str) -> str
"""Move all sources from source_tag to target_tag, then delete source_tag."""
```

### Note tools

```python
save_note(topic: str, body: str, source_ref: str = "") -> str
"""
Save a note to a topic (optionally associated with a specific source).
Embeds the note into ChromaDB so it's searchable in future sessions.
Use this to capture insights, questions, summaries, and connections.
Returns note ID.
"""

list_notes(topic: str) -> str
"""List all notes for a topic, most recent first. Shows ID, created_at, source association, body preview."""

get_note(note_id: int) -> str
"""Return the full text of a note."""

edit_note(note_id: int, body: str) -> str
"""Update a note. Re-embeds the new content into ChromaDB."""

delete_note(note_id: int) -> str
```

---

## REST API (`api.py`)

Mirrors the MCP tools but as HTTP endpoints for the browser. No logic lives here — all calls delegate to `db.py` and `store.py`.

```
GET  /topics
POST /topics                        body: {name, description}
DELETE /topics/{slug}

GET  /topics/{slug}/digest
GET  /topics/{slug}/sources         ?tag=
POST /topics/{slug}/ingest          body: {path_or_url, tags}
DELETE /topics/{slug}/sources       body: {source_ref}
GET  /topics/{slug}/sources/{id}/outline

GET  /topics/{slug}/tags
POST /topics/{slug}/tags/add        body: {source_ref, tags}
POST /topics/{slug}/tags/remove     body: {source_ref, tags}
POST /topics/{slug}/tags/rename     body: {old_name, new_name}
POST /topics/{slug}/tags/merge      body: {source_tag, target_tag}
DELETE /topics/{slug}/tags          body: {name}

GET  /topics/{slug}/notes
POST /topics/{slug}/notes           body: {body, source_ref}
PUT  /topics/{slug}/notes/{id}      body: {body}
DELETE /topics/{slug}/notes/{id}

POST /search                        body: {query, topic, tags, top_k}
POST /search-all                    body: {query, top_k_per_topic}
```

---

## Browser UI (`ui/index.html`)

Management console. Single-page app with a persistent sidebar.

**Sidebar** — always visible
- Topic list with source count per topic
- Global search input → fires `/search-all`, results in a modal
- "New topic" button → modal form (name + description)

**Topic view** — two-column layout within the main area
- Sub-header: topic name, description, in-topic search input, Delete button
- Tag filter bar (shown when topic has tags): click a tag to filter sources to that tag; multiple tags use OR logic
- In-topic search panel: appears below the filter bar when a query is typed, fires `/search`, shows results with source title, chapter, and score
- Left column — sources:
  - Each source row: type icon, title, status badge, chunk count, tag pills
  - Click row → expands to show chapter outline (fetched from `/sources/{id}/outline`)
  - Expand footer: "Add linked note" button pre-fills the note source dropdown
  - Delete button (×) per source row
  - "Add" button → inline form with URL/path input + tag chip input
- Right column — notes:
  - New note form: textarea + source dropdown (links note to a source) + Save
  - Notes list, most recent first, with source association label
  - Click note → expand to inline editor (textarea + Save/Delete)

---

## Build order

Build in this sequence — each phase is independently runnable.

### Phase 1 — SQLite foundation
- Write `db.py` with full schema and all DAO functions
- Update `setup.sh` to call `db.init_db()` on first run
- No user-facing changes yet

### Phase 2 — Ingest pipeline
- Update `store.py` with new functions (`delete_chunks_for_source`, `get_chunks_ordered`)
- Rewrite ingest flow in `server.py`: register source → extract → chunk → embed → update status
- Update `ingest_source` MCP tool signature: `tags: list[str]` replaces `module: str`
- Fix the re-ingest bug (delete before add, matching MCP tool order)

### Phase 3 — Core MCP tools
- `list_topics`, `create_topic`, `delete_topic`, `get_topic_digest`
- `list_sources`, `delete_source`
- `search_topic` (update existing `search_library`)
- `get_source_outline`, `get_source_text` (new)

### Phase 4 — Notes
- `save_note`, `list_notes`, `get_note`, `edit_note`, `delete_note`
- Embed notes into ChromaDB on save; re-embed on edit; delete on remove
- `search_topic` already returns notes via `kind` metadata

### Phase 5 — Tag management
- `list_tags`, `tag_source`, `untag_source`, `rename_tag`, `merge_tags`
- `search_topic` tag filter

### Phase 6 — Cross-topic search
- `search_all` — iterate collections, fan out queries, merge by score

### Phase 7 — REST API + UI
- Update `api.py` with new routes
- Update `ui/index.html` with topic/tag/note UI

---

## What to keep unchanged

- All of `ingest.py` — extractors and chunker are solid
- `store.py` core: `_embedding_fn`, `_slugify`, `add_chunks`, `search`, `get_or_create_collection`, `list_collections`
- FastMCP server structure in `server.py`
- FastAPI + CORS setup in `api.py`
- `configure_mcp.py`
- `setup.sh` / `start.sh` structure

---

## Key decisions

**SQLite is the system of record, ChromaDB is the index.** Never query ChromaDB to answer "what sources do I have?" — that's a SQLite question. ChromaDB answers "what chunks are semantically similar to this query?"

**Notes are embedded.** Your thinking becomes searchable alongside source text. The `kind` field distinguishes them in results.

**Tags live in SQLite, not chunk metadata.** Renaming or merging a tag is a single SQL update, not a re-ingest. ChromaDB chunk metadata does not need to stay in sync with tag names.

**One ChromaDB collection per topic.** Makes topic-level delete, backup, and scoping trivial. Cross-topic search fans out across collections at query time.

**No conversation history.** When a session produces something worth keeping, Claude calls `save_note`. Transcripts pollute search. Rule: persist derived artifacts (notes, outlines), not conversation mechanics.
