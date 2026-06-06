import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import ingest
import store

app = FastAPI(title="Course Explorer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UI_PATH = Path(__file__).parent / "ui" / "index.html"


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    if not UI_PATH.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return HTMLResponse(content=UI_PATH.read_text(encoding="utf-8"))


@app.get("/courses")
def get_courses():
    client = store.get_client()
    return store.list_collections(client)


@app.get("/courses/{course}/sources")
def get_sources(course: str):
    client = store.get_client()
    collection = store.get_or_create_collection(client, course)
    return store.list_sources(collection)


@app.get("/courses/{course}/modules")
def get_modules(course: str):
    client = store.get_client()
    collection = store.get_or_create_collection(client, course)
    result = collection.get(include=["metadatas"])
    modules = sorted({
        m.get("module", "")
        for m in result["metadatas"]
        if m.get("module")
    })
    return modules


class IngestRequest(BaseModel):
    path_or_url: str
    course: str
    module: str = ""


@app.post("/ingest")
def ingest_source_endpoint(req: IngestRequest):
    try:
        source_title, chunks = ingest.ingest_source(req.path_or_url, req.course, req.module)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    client = store.get_client()
    collection = store.get_or_create_collection(client, req.course)
    store.delete_source(collection, req.path_or_url)
    store.add_chunks(collection, chunks)

    return {"source_title": source_title, "chunks_added": len(chunks)}


class DeleteSourceRequest(BaseModel):
    source_ref: str


@app.delete("/courses/{course}/sources")
def delete_source_endpoint(course: str, req: DeleteSourceRequest):
    client = store.get_client()
    collection = store.get_or_create_collection(client, course)
    store.delete_source(collection, req.source_ref)
    return {"deleted": True}


class SearchRequest(BaseModel):
    query: str
    course: str
    module: Optional[str] = ""
    top_k: int = 5


@app.post("/search")
def search_endpoint(req: SearchRequest):
    client = store.get_client()
    collection = store.get_or_create_collection(client, req.course)
    raw = store.search(collection, req.query, top_k=req.top_k, module_filter=req.module or "")

    results = []
    for r in raw:
        meta = r["metadata"]
        score = round(1 - (r["distance"] / 2), 4)
        results.append({
            "text": r["text"],
            "score": score,
            "source_title": meta.get("source_title", ""),
            "source_type": meta.get("source_type", ""),
            "source_ref": meta.get("source_ref", ""),
            "chapter": meta.get("chapter", ""),
            "page": meta.get("page", 0),
            "timestamp_seconds": meta.get("timestamp_seconds", 0),
            "module": meta.get("module", ""),
        })

    return {"results": results}
