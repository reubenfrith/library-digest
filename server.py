import sys
import os
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
import ingest
import store

mcp = FastMCP("course-explorer")


@mcp.tool()
def ingest_source(
    path_or_url: str,
    course: str,
    module: str = "",
) -> str:
    """Ingest a source (file path or URL) into a course collection.

    Supported: PDF files, EPUB files, .txt/.md files, web pages, YouTube videos.
    Re-ingesting the same source_ref replaces the previous version cleanly.
    """
    client = store.get_client()
    collection = store.get_or_create_collection(client, course)
    store.delete_source(collection, path_or_url)

    source_title, chunks = ingest.ingest_source(path_or_url, course, module)
    store.add_chunks(collection, chunks)

    return f"Ingested '{source_title}' — {len(chunks)} chunks added to course '{course}'."


@mcp.tool()
def search_course(
    query: str,
    course: str,
    module: str = "",
    top_k: int = 5,
) -> str:
    """Search course materials for passages relevant to a query.

    Returns the top matching text chunks with source and location metadata.
    top_k is capped at 10.
    """
    top_k = min(top_k, 10)
    client = store.get_client()
    collection = store.get_or_create_collection(client, course)
    results = store.search(collection, query, top_k=top_k, module_filter=module)

    if not results:
        return f"No results found in course '{course}'."

    blocks = []
    for i, r in enumerate(results, start=1):
        meta = r["metadata"]
        source_type = meta.get("source_type", "")
        title = meta.get("source_title", meta.get("source_ref", "unknown"))
        chapter = meta.get("chapter", "")
        page = meta.get("page", 0)
        ts = meta.get("timestamp_seconds", 0)
        mod = meta.get("module", "")

        location_parts = []
        if chapter:
            location_parts.append(f"§ {chapter}")
        if source_type == "pdf" and page:
            location_parts.append(f"p.{page}")
        if source_type == "video" and ts:
            mins, secs = divmod(ts, 60)
            location_parts.append(f"{mins:02d}:{secs:02d}")
        location = " · ".join(location_parts) if location_parts else ""

        header = f"[{i}] {title}"
        if location:
            header += f" — {location}"
        if mod:
            header += f" ({mod})"

        blocks.append(f"{header}\n{r['text']}")

    return "\n\n---\n\n".join(blocks)


@mcp.tool()
def list_courses() -> str:
    """List all courses in the knowledge base with their chunk counts."""
    client = store.get_client()
    courses = store.list_collections(client)

    if not courses:
        return "No courses indexed yet. Use ingest_source to add materials."

    lines = [f"• {c['display_name']} ({c['name']}) — {c['total_chunks']:,} chunks" for c in courses]
    return "\n".join(lines)


@mcp.tool()
def list_sources(course: str) -> str:
    """List all sources indexed for a given course."""
    client = store.get_client()
    collection = store.get_or_create_collection(client, course)
    sources = store.list_sources(collection)

    if not sources:
        return f"No sources indexed for course '{course}'."

    lines = []
    for s in sources:
        mod = f" [{s['module']}]" if s["module"] else ""
        lines.append(
            f"• [{s['source_type']}]{mod} {s['source_title']} — {s['chunk_count']} chunks\n"
            f"  {s['source_ref']}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_module_map(course: str, module: str = "") -> str:
    """Show the chapter/section structure of a course (or a single module).

    Returns an outline of chapters with word counts and text previews.
    """
    client = store.get_client()
    collection = store.get_or_create_collection(client, course)
    chunks = store.get_all_chunks_ordered(collection)

    if module:
        chunks = [c for c in chunks if c["metadata"].get("module") == module]

    if not chunks:
        label = f"module '{module}' of " if module else ""
        return f"No content found in {label}course '{course}'."

    # Group by chapter
    chapters: dict[str, list[dict]] = {}
    for chunk in chunks:
        ch = chunk["metadata"].get("chapter") or "(untitled)"
        chapters.setdefault(ch, []).append(chunk)

    lines = []
    for ch_name, ch_chunks in chapters.items():
        word_count = sum(len(c["text"].split()) for c in ch_chunks)
        preview = ch_chunks[0]["text"][:120].replace("\n", " ") + "…"
        lines.append(f"### {ch_name}")
        lines.append(f"  {word_count:,} words · {len(ch_chunks)} chunks")
        lines.append(f'  "{preview}"')

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
