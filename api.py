import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import db
import store
import ingest as ingest_mod

app = FastAPI(title="Library Digest API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UI_PATH = Path(__file__).parent / "ui" / "index.html"

db.init_db()


def _topic_or_404(slug: str) -> dict:
    t = db.get_topic(slug)
    if not t:
        raise HTTPException(status_code=404, detail=f"Topic '{slug}' not found")
    return t


# ── UI ────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    if not UI_PATH.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return HTMLResponse(content=UI_PATH.read_text(encoding="utf-8"))


# ── Topics ────────────────────────────────────────────────────────────────────

@app.get("/topics")
def get_topics():
    return db.list_topics()


class CreateTopicRequest(BaseModel):
    name: str
    description: str = ""


@app.post("/topics", status_code=201)
def create_topic(req: CreateTopicRequest):
    try:
        return db.create_topic(req.name, req.description)
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/topics/{slug}")
def delete_topic(slug: str):
    t = _topic_or_404(slug)
    client = store.get_client()
    store.delete_collection(client, t["slug"])
    db.delete_topic(t["slug"])
    return {"deleted": True}


@app.get("/topics/{slug}/digest")
def get_digest(slug: str):
    t = _topic_or_404(slug)
    return {
        "topic": t,
        "sources": db.list_sources(t["id"]),
        "notes": db.list_notes(t["id"]),
        "tags": db.list_tags(t["id"]),
    }


# ── Sources ───────────────────────────────────────────────────────────────────

@app.get("/topics/{slug}/sources")
def get_sources(slug: str, tag: str = ""):
    t = _topic_or_404(slug)
    return db.list_sources(t["id"], tag_name=tag)


class IngestRequest(BaseModel):
    path_or_url: str
    tags: list[str] = []


@app.post("/topics/{slug}/ingest")
def ingest_source_endpoint(slug: str, req: IngestRequest):
    t = _topic_or_404(slug)
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])

    source_row = db.register_source(t["id"], req.path_or_url)

    try:
        source_title, chunks = ingest_mod.ingest_source(req.path_or_url, t["slug"], source_row["id"])
    except Exception as e:
        db.update_source_error(source_row["id"], str(e))
        raise HTTPException(status_code=422, detail=str(e))

    store.delete_chunks_for_source(collection, source_row["id"])
    store.add_chunks(collection, chunks)

    source_type = chunks[0]["metadata"]["source_type"] if chunks else ""
    db.update_source_done(source_row["id"], source_title, source_type, len(chunks))

    if req.tags:
        db.add_source_tags(source_row["id"], t["id"], req.tags)

    return db.get_source(t["id"], req.path_or_url)


@app.get("/topics/{slug}/sources/{source_id}/outline")
def get_source_outline(slug: str, source_id: int):
    t = _topic_or_404(slug)
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    chunks = store.get_chunks_ordered(collection, source_id)

    seen: dict[str, dict] = {}
    order: list[str] = []
    for chunk in chunks:
        ch = chunk["metadata"].get("chapter", "") or "—"
        if ch not in seen:
            seen[ch] = {"name": ch, "word_count": 0}
            order.append(ch)
        seen[ch]["word_count"] += len(chunk["text"].split())

    return {"chapters": [seen[c] for c in order]}


class DeleteSourceRequest(BaseModel):
    source_ref: str


@app.delete("/topics/{slug}/sources")
def delete_source_endpoint(slug: str, req: DeleteSourceRequest):
    t = _topic_or_404(slug)
    source_row = db.get_source(t["id"], req.source_ref)
    if not source_row:
        raise HTTPException(status_code=404, detail="Source not found")
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    store.delete_chunks_for_source(collection, source_row["id"])
    db.delete_source_record(source_row["id"])
    return {"deleted": True}


class OpenRequest(BaseModel):
    path: str


@app.post("/open")
def open_local_file(req: OpenRequest):
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    subprocess.Popen(["open", str(p)])
    return {"ok": True}


# ── Tags ──────────────────────────────────────────────────────────────────────

@app.get("/topics/{slug}/tags")
def get_tags(slug: str):
    t = _topic_or_404(slug)
    return db.list_tags(t["id"])


class TagSourceRequest(BaseModel):
    source_ref: str
    tags: list[str]


@app.post("/topics/{slug}/tags/add")
def add_source_tags(slug: str, req: TagSourceRequest):
    t = _topic_or_404(slug)
    source_row = db.get_source(t["id"], req.source_ref)
    if not source_row:
        raise HTTPException(status_code=404, detail="Source not found")
    db.add_source_tags(source_row["id"], t["id"], req.tags)
    return {"ok": True}


@app.post("/topics/{slug}/tags/remove")
def remove_source_tags(slug: str, req: TagSourceRequest):
    t = _topic_or_404(slug)
    source_row = db.get_source(t["id"], req.source_ref)
    if not source_row:
        raise HTTPException(status_code=404, detail="Source not found")
    db.remove_source_tags(source_row["id"], t["id"], req.tags)
    return {"ok": True}


class RenameTagRequest(BaseModel):
    old_name: str
    new_name: str


@app.post("/topics/{slug}/tags/rename")
def rename_tag(slug: str, req: RenameTagRequest):
    t = _topic_or_404(slug)
    db.rename_tag(t["id"], req.old_name, req.new_name)
    return {"ok": True}


class MergeTagRequest(BaseModel):
    source_tag: str
    target_tag: str


@app.post("/topics/{slug}/tags/merge")
def merge_tags(slug: str, req: MergeTagRequest):
    t = _topic_or_404(slug)
    db.merge_tags(t["id"], req.source_tag, req.target_tag)
    return {"ok": True}


class DeleteTagRequest(BaseModel):
    name: str


@app.delete("/topics/{slug}/tags")
def delete_tag(slug: str, req: DeleteTagRequest):
    t = _topic_or_404(slug)
    db.delete_tag(t["id"], req.name)
    return {"deleted": True}


# ── Notes ─────────────────────────────────────────────────────────────────────

@app.get("/topics/{slug}/notes")
def get_notes(slug: str):
    t = _topic_or_404(slug)
    return db.list_notes(t["id"])


class CreateNoteRequest(BaseModel):
    body: str
    source_ref: str = ""


@app.post("/topics/{slug}/notes", status_code=201)
def create_note(slug: str, req: CreateNoteRequest):
    t = _topic_or_404(slug)
    source_id = None
    if req.source_ref:
        src = db.get_source(t["id"], req.source_ref)
        if src:
            source_id = src["id"]
    note = db.create_note(t["id"], req.body, source_id)
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    chroma_id = store.embed_note(collection, note["id"], req.body, t["slug"])
    db.set_note_chroma_id(note["id"], chroma_id)
    return db.get_note(note["id"])


class UpdateNoteRequest(BaseModel):
    body: str


@app.put("/topics/{slug}/notes/{note_id}")
def update_note(slug: str, note_id: int, req: UpdateNoteRequest):
    t = _topic_or_404(slug)
    note = db.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    if note.get("chroma_id"):
        store.delete_note_embedding(collection, note["chroma_id"])
    db.update_note(note_id, req.body)
    chroma_id = store.embed_note(collection, note_id, req.body, t["slug"])
    db.set_note_chroma_id(note_id, chroma_id)
    return db.get_note(note_id)


@app.delete("/topics/{slug}/notes/{note_id}")
def delete_note(slug: str, note_id: int):
    t = _topic_or_404(slug)
    note = db.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])
    if note.get("chroma_id"):
        store.delete_note_embedding(collection, note["chroma_id"])
    db.delete_note(note_id)
    return {"deleted": True}


# ── Search ────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    topic: str
    tags: list[str] = []
    top_k: int = 8


@app.post("/search")
def search_endpoint(req: SearchRequest):
    t = db.get_topic(req.topic)
    if not t:
        raise HTTPException(status_code=404, detail="Topic not found")
    client = store.get_client()
    collection = store.get_or_create_collection(client, t["slug"])

    source_ids = None
    if req.tags:
        source_ids = [
            s["id"] for s in db.list_sources(t["id"])
            if any(tag in s.get("tags", []) for tag in req.tags)
        ]

    raw = store.search(collection, req.query, top_k=req.top_k, source_ids=source_ids)
    results = []
    for r in raw:
        meta = r["metadata"]
        results.append({
            "text": r["text"],
            "score": round(1 - (r["distance"] / 2), 4),
            "kind": meta.get("kind", "chunk"),
            "source_title": meta.get("source_title", ""),
            "source_type": meta.get("source_type", ""),
            "source_ref": meta.get("source_ref", ""),
            "chapter": meta.get("chapter", ""),
            "page": meta.get("page", 0),
            "timestamp_seconds": meta.get("timestamp_seconds", 0),
        })
    return {"results": results}


class SearchAllRequest(BaseModel):
    query: str
    top_k_per_topic: int = 3


@app.post("/search-all")
def search_all_endpoint(req: SearchAllRequest):
    top_k = min(req.top_k_per_topic, 5)
    topics = db.list_topics()
    client = store.get_client()
    grouped = []
    for t in topics:
        try:
            collection = store.get_or_create_collection(client, t["slug"])
            results = store.search(collection, req.query, top_k=top_k)
            if results:
                grouped.append({
                    "topic": t,
                    "results": [{
                        "text": r["text"],
                        "score": round(1 - (r["distance"] / 2), 4),
                        "kind": r["metadata"].get("kind", "chunk"),
                        "source_title": r["metadata"].get("source_title", ""),
                        "source_ref": r["metadata"].get("source_ref", ""),
                    } for r in results],
                })
        except Exception:
            continue
    return {"groups": grouped}
