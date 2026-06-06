import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
import db
import store
import ingest

db.init_db()
mcp = FastMCP("library-digest")

_ICONS = {"pdf": "📄", "epub": "📄", "web": "🌐", "video": "🎬", "text": "📝", "note": "📝"}


def _topic_or_err(slug: str) -> dict:
    t = db.get_topic(slug)
    if not t:
        raise ValueError(f"Topic '{slug}' not found. Use list_topics to see available topics.")
    return t


def _score(distance: float) -> float:
    return round(1 - (distance / 2), 3)


def _fmt_sources(sources: list[dict]) -> str:
    if not sources:
        return "  (none)"
    lines = []
    for s in sources:
        icon = _ICONS.get(s["source_type"], "📎")
        tags = f"  [{', '.join(s['tags'])}]" if s.get("tags") else ""
        status = s["ingest_status"]
        status_marker = {"done": "✓", "pending": "⏳", "error": "✗"}.get(status, "?")
        line = f"  {status_marker} {icon} {s['source_title'] or s['source_ref']}{tags} — {s['chunk_count']} chunks"
        if status == "error":
            line += f"\n     ⚠ {s['error_message']}"
        line += f"\n     {s['source_ref']}"
        lines.append(line)
    return "\n".join(lines)


# ── Topic tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def list_topics() -> str:
    """List all topics with name, source count, chunk count, and created date."""
    topics = db.list_topics()
    if not topics:
        return "No topics yet. Use create_topic to get started."
    lines = []
    for t in topics:
        lines.append(
            f"• {t['name']} ({t['slug']})\n"
            f"  {t['source_count']} sources · {t['total_chunks']:,} chunks · created {t['created_at'][:10]}"
        )
        if t.get("description"):
            lines.append(f"  {t['description']}")
    return "\n\n".join(lines)


@mcp.tool()
def create_topic(name: str, description: str = "") -> str:
    """Create a new research topic. Persists immediately — no need to ingest first."""
    t = db.create_topic(name, description)
    return f"Created topic '{t['name']}' (slug: {t['slug']})."


@mcp.tool()
def delete_topic(topic: str) -> str:
    """Delete a topic and all its sources, notes, and embeddings. Irreversible."""
    t = _topic_or_err(topic)
    db.delete_topic(t["slug"])
    client = store.get_client()
    store.delete_collection(client, t["slug"])
    return f"Deleted topic '{t['name']}' and all its data."


@mcp.tool()
def get_topic_digest(topic: str) -> str:
    """
    Full orientation dump for a topic: sources, notes, tags, and chunk count.
    Call this at the start of a research session to orient yourself.
    """
    t = _topic_or_err(topic)
    sources = db.list_sources(t["id"])
    notes = db.list_notes(t["id"])
    tags = db.list_tags(t["id"])

    lines = [f"# {t['name']}"]
    if t.get("description"):
        lines.append(t["description"])

    total_chunks = sum(s["chunk_count"] for s in sources)
    lines.append(f"\n{len(sources)} sources · {total_chunks:,} chunks · {len(notes)} notes\n")

    lines.append("## Sources")
    lines.append(_fmt_sources(sources))

    lines.append("\n## Tags")
    if tags:
        lines.append("  " + ", ".join(f"{tg['name']} ({tg['source_count']})" for tg in tags))
    else:
        lines.append("  (none)")

    lines.append("\n## Notes (most recent 20)")
    if notes:
        for n in notes[:20]:
            src_label = ""
            if n.get("source_id"):
                src = next((s for s in sources if s["id"] == n["source_id"]), None)
                if src:
                    src_label = f" [from: {src['source_title'] or src['source_ref']}]"
            preview = n["body"][:120].replace("\n", " ")
            if len(n["body"]) > 120:
                preview += "…"
            lines.append(f"  #{n['id']} ({n['created_at'][:10]}){src_label}\n  {preview}")
        if len(notes) > 20:
            lines.append(f"  … and {len(notes) - 20} more. Use list_notes to see all.")
    else:
        lines.append("  (none yet)")

    return "\n".join(lines)


# ── Source tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def ingest_source(path_or_url: str, topic: str, tags: list[str] = []) -> str:
    """
    Ingest a source (file path or URL) into a topic.
    Supported: PDF, EPUB, .txt/.md, web pages, YouTube videos.
    Re-ingesting the same URL/path replaces the previous version cleanly.
    tags: optional list of labels, e.g. ["week-1", "intro"]
    """
    t = _topic_or_err(topic)
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])

    source_row = db.register_source(t["id"], path_or_url)

    try:
        source_title, chunks = ingest.ingest_source(path_or_url, t["slug"], source_row["id"])
    except Exception as e:
        db.update_source_error(source_row["id"], str(e))
        return f"Error ingesting '{path_or_url}': {e}"

    if not chunks:
        msg = "Source produced no extractable text"
        db.update_source_error(source_row["id"], msg)
        return f"Error ingesting '{path_or_url}': {msg}"

    store.delete_chunks_for_source(collection, source_row["id"])
    store.add_chunks(collection, chunks)

    source_type = chunks[0]["metadata"]["source_type"]
    db.update_source_done(source_row["id"], source_title, source_type, len(chunks))

    if tags:
        db.add_source_tags(source_row["id"], t["id"], tags)

    tag_str = f" — tags: {', '.join(tags)}" if tags else ""
    return f"Ingested '{source_title}' — {len(chunks)} chunks added to '{topic}'{tag_str}."


@mcp.tool()
def list_sources(topic: str, tag: str = "") -> str:
    """List sources in a topic, optionally filtered by tag."""
    t = _topic_or_err(topic)
    sources = db.list_sources(t["id"], tag_name=tag)
    if not sources:
        qualifier = f" with tag '{tag}'" if tag else ""
        return f"No sources{qualifier} in '{topic}'."
    return _fmt_sources(sources)


@mcp.tool()
def delete_source(topic: str, source_ref: str) -> str:
    """Remove a source and all its chunks from a topic."""
    t = _topic_or_err(topic)
    source_row = db.get_source(t["id"], source_ref)
    if not source_row:
        return f"Source '{source_ref}' not found in '{topic}'."
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    store.delete_chunks_for_source(collection, source_row["id"])
    db.delete_source_record(source_row["id"])
    return f"Deleted '{source_ref}' from '{topic}'."


@mcp.tool()
def get_source_outline(topic: str, source_ref: str) -> str:
    """
    Chapter/section outline of a single source with word counts and previews.
    Use this to orient yourself before deciding which part to read.
    """
    t = _topic_or_err(topic)
    source_row = db.get_source(t["id"], source_ref)
    if not source_row:
        return f"Source '{source_ref}' not found in '{topic}'."
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    chunks = store.get_chunks_ordered(collection, source_row["id"])
    if not chunks:
        return f"No chunks found for '{source_ref}'. It may still be ingesting."

    chapters: dict[str, list[dict]] = {}
    for c in chunks:
        ch = c["metadata"].get("chapter") or "(untitled)"
        chapters.setdefault(ch, []).append(c)

    lines = [f"# {source_row['source_title'] or source_ref}"]
    for ch_name, ch_chunks in chapters.items():
        word_count = sum(len(c["text"].split()) for c in ch_chunks)
        preview = ch_chunks[0]["text"][:100].replace("\n", " ") + "…"
        lines.append(f"\n### {ch_name}")
        lines.append(f"  {word_count:,} words · {len(ch_chunks)} chunks")
        lines.append(f'  "{preview}"')
    return "\n".join(lines)


@mcp.tool()
def get_source_text(topic: str, source_ref: str, chapter: str = "") -> str:
    """
    Return the full text of a source, or a single chapter if specified.
    Use this to read a full article or section rather than relying on search snippets.
    Capped at ~8,000 words; a truncation notice is shown if longer.
    """
    t = _topic_or_err(topic)
    source_row = db.get_source(t["id"], source_ref)
    if not source_row:
        return f"Source '{source_ref}' not found in '{topic}'."
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    chunks = store.get_chunks_ordered(collection, source_row["id"], chapter=chapter)
    if not chunks:
        qualifier = f" chapter '{chapter}'" if chapter else ""
        return f"No content found for{qualifier} '{source_ref}'."

    parts = []
    word_count = 0
    truncated = False
    for c in chunks:
        words = c["text"].split()
        if word_count + len(words) > 8000:
            truncated = True
            break
        parts.append(c["text"])
        word_count += len(words)

    text = "\n\n".join(parts)
    if truncated:
        text += f"\n\n[Truncated at 8,000 words. Use chapter filter to read a specific section.]"
    return text


# ── Search tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def search_topic(query: str, topic: str, tags: list[str] = [], top_k: int = 8) -> str:
    """
    Semantic search within a topic. Returns source chunks and notes together.
    tags: optional list — results are scoped to sources that have ANY of these tags.
    top_k capped at 15.
    """
    top_k = min(top_k, 15)
    t = _topic_or_err(topic)
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])

    source_ids = None
    if tags:
        all_sources = db.list_sources(t["id"])
        source_ids = [
            s["id"] for s in all_sources
            if any(tag in s.get("tags", []) for tag in tags)
        ]

    results = store.search(collection, query, top_k=top_k, source_ids=source_ids)
    if not results:
        return f"No results found in '{topic}'."

    blocks = []
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        kind = meta.get("kind", "chunk")
        title = meta.get("source_title") or meta.get("source_ref", "unknown")
        chapter = meta.get("chapter", "")
        page = meta.get("page", 0)
        ts = meta.get("timestamp_seconds", 0)
        source_type = meta.get("source_type", "")

        loc_parts = []
        if chapter:
            loc_parts.append(f"§ {chapter}")
        if source_type == "pdf" and page:
            loc_parts.append(f"p.{page}")
        if source_type == "video" and ts:
            m, s = divmod(ts, 60)
            loc_parts.append(f"{m:02d}:{s:02d}")
        location = " · ".join(loc_parts)

        label = "[note]" if kind == "note" else f"[{i}]"
        header = f"{label} {title}"
        if location:
            header += f" — {location}"
        header += f"  (score {_score(r['distance']):.0%})"
        blocks.append(f"{header}\n{r['text']}")

    return "\n\n---\n\n".join(blocks)


@mcp.tool()
def search_all(query: str, top_k_per_topic: int = 3) -> str:
    """
    Search across all topics. Use for cross-topic discovery and rabbit holes.
    Returns results grouped by topic, sorted by score.
    top_k_per_topic capped at 5.
    """
    top_k_per_topic = min(top_k_per_topic, 5)
    topics = db.list_topics()
    if not topics:
        return "No topics indexed yet."

    client = store.get_client()
    all_results: list[dict] = []

    for t in topics:
        try:
            collection = store.get_or_create_collection(client, t["slug"])
            results = store.search(collection, query, top_k=top_k_per_topic)
            for r in results:
                r["_topic_name"] = t["name"]
                r["_topic_slug"] = t["slug"]
            all_results.extend(results)
        except Exception:
            continue

    if not all_results:
        return "No results found across any topic."

    all_results.sort(key=lambda r: r["distance"])

    by_topic: dict[str, list[dict]] = {}
    for r in all_results:
        by_topic.setdefault(r["_topic_slug"], []).append(r)

    sections = []
    for slug, results in by_topic.items():
        topic_name = results[0]["_topic_name"]
        blocks = []
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            title = meta.get("source_title") or meta.get("source_ref", "unknown")
            header = f"  [{i}] {title}  (score {_score(r['distance']):.0%})"
            preview = r["text"][:200].replace("\n", " ")
            if len(r["text"]) > 200:
                preview += "…"
            blocks.append(f"{header}\n  {preview}")
        sections.append(f"### {topic_name}\n" + "\n\n".join(blocks))

    return "\n\n".join(sections)


# ── Tag tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def list_tags(topic: str) -> str:
    """List all tags in a topic with source counts."""
    t = _topic_or_err(topic)
    tags = db.list_tags(t["id"])
    if not tags:
        return f"No tags in '{topic}' yet."
    return "\n".join(f"• {tg['name']} — {tg['source_count']} source(s)" for tg in tags)


@mcp.tool()
def tag_source(topic: str, source_ref: str, tags: list[str]) -> str:
    """Add tags to a source. Creates tags if they don't exist."""
    t = _topic_or_err(topic)
    source_row = db.get_source(t["id"], source_ref)
    if not source_row:
        return f"Source '{source_ref}' not found in '{topic}'."
    db.add_source_tags(source_row["id"], t["id"], tags)
    return f"Added tags {tags} to '{source_row['source_title'] or source_ref}'."


@mcp.tool()
def untag_source(topic: str, source_ref: str, tags: list[str]) -> str:
    """Remove tags from a source."""
    t = _topic_or_err(topic)
    source_row = db.get_source(t["id"], source_ref)
    if not source_row:
        return f"Source '{source_ref}' not found in '{topic}'."
    db.remove_source_tags(source_row["id"], t["id"], tags)
    return f"Removed tags {tags} from '{source_row['source_title'] or source_ref}'."


@mcp.tool()
def rename_tag(topic: str, old_name: str, new_name: str) -> str:
    """Rename a tag across all sources in the topic."""
    t = _topic_or_err(topic)
    db.rename_tag(t["id"], old_name, new_name)
    return f"Renamed tag '{old_name}' → '{new_name}' in '{topic}'."


@mcp.tool()
def merge_tags(topic: str, source_tag: str, target_tag: str) -> str:
    """Move all sources from source_tag into target_tag, then delete source_tag."""
    t = _topic_or_err(topic)
    db.merge_tags(t["id"], source_tag, target_tag)
    return f"Merged tag '{source_tag}' into '{target_tag}' in '{topic}'."


# ── Note tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def save_note(topic: str, body: str, source_ref: str = "") -> str:
    """
    Save a note to a topic (optionally associated with a specific source).
    Notes are embedded into the topic's vector store, so they appear in
    future search_topic results labelled [note].
    Use this to capture insights, questions, summaries, and connections.
    """
    t = _topic_or_err(topic)
    source_id = None
    if source_ref:
        source_row = db.get_source(t["id"], source_ref)
        if source_row:
            source_id = source_row["id"]

    note = db.create_note(t["id"], body, source_id)

    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    chroma_id = store.embed_note(collection, note["id"], body, t["slug"])
    db.set_note_chroma_id(note["id"], chroma_id)

    return f"Saved note #{note['id']} to '{topic}'."


@mcp.tool()
def list_notes(topic: str) -> str:
    """List all notes for a topic, most recent first."""
    t = _topic_or_err(topic)
    notes = db.list_notes(t["id"])
    if not notes:
        return f"No notes in '{topic}' yet."
    sources = {s["id"]: s for s in db.list_sources(t["id"])}
    lines = []
    for n in notes:
        src_label = ""
        if n.get("source_id") and n["source_id"] in sources:
            src = sources[n["source_id"]]
            src_label = f" [from: {src['source_title'] or src['source_ref']}]"
        preview = n["body"][:120].replace("\n", " ")
        if len(n["body"]) > 120:
            preview += "…"
        lines.append(f"#{n['id']} ({n['created_at'][:10]}){src_label}\n  {preview}")
    return "\n\n".join(lines)


@mcp.tool()
def get_note(note_id: int) -> str:
    """Return the full text of a note."""
    note = db.get_note(note_id)
    if not note:
        return f"Note #{note_id} not found."
    return note["body"]


@mcp.tool()
def edit_note(note_id: int, body: str) -> str:
    """Update a note and re-embed it so future searches reflect the new content."""
    note = db.get_note(note_id)
    if not note:
        return f"Note #{note_id} not found."

    t = db.get_topic_by_id(note["topic_id"])
    if not t:
        return f"Topic for note #{note_id} not found."

    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])

    if note.get("chroma_id"):
        store.delete_note_embedding(collection, note["chroma_id"])

    updated = db.update_note(note_id, body)
    chroma_id = store.embed_note(collection, note_id, body, t["slug"])
    db.set_note_chroma_id(note_id, chroma_id)

    return f"Updated note #{note_id}."


@mcp.tool()
def delete_note(note_id: int) -> str:
    """Delete a note and remove its embedding."""
    note = db.get_note(note_id)
    if not note:
        return f"Note #{note_id} not found."

    t = db.get_topic_by_id(note["topic_id"])
    if t and note.get("chroma_id"):
        client = store.get_client()
        collection = store.get_or_create_collection(client, t["slug"])
        store.delete_note_embedding(collection, note["chroma_id"])

    db.delete_note(note_id)
    return f"Deleted note #{note_id}."


if __name__ == "__main__":
    mcp.run(transport="stdio")
