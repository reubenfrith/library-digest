import os
import re

import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chroma")

_ef = None


def _embedding_fn():
    global _ef
    if _ef is None:
        _ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _ef


def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]


def get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=CHROMA_DIR)


def get_or_create_collection(client: chromadb.PersistentClient, topic_slug: str):
    return client.get_or_create_collection(
        name=topic_slug,
        metadata={"hnsw:space": "cosine"},
        embedding_function=_embedding_fn(),
    )


def delete_collection(client: chromadb.PersistentClient, topic_slug: str) -> None:
    try:
        client.delete_collection(topic_slug)
    except Exception:
        pass


def add_chunks(collection, chunks: list[dict], batch_size: int = 100) -> None:
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )


def search(
    collection,
    query: str,
    top_k: int = 8,
    source_ids: list[int] | None = None,
) -> list[dict]:
    count = collection.count()
    if count == 0:
        return []
    if source_ids is not None and not source_ids:
        return []

    n = min(top_k, count)
    kwargs: dict = {
        "query_texts": [query],
        "n_results": n,
        "include": ["documents", "metadatas", "distances"],
    }
    if source_ids is not None:
        kwargs["where"] = {"source_id": {"$in": source_ids}}

    results = collection.query(**kwargs)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    return [
        {"text": doc, "metadata": meta, "distance": dist}
        for doc, meta, dist in zip(docs, metas, dists)
    ]


def delete_chunks_for_source(collection, source_id: int) -> None:
    result = collection.get(where={"source_id": source_id})
    ids = result.get("ids", [])
    if ids:
        collection.delete(ids=ids)


def get_chunks_ordered(collection, source_id: int, chapter: str = "") -> list[dict]:
    where: dict = {"source_id": source_id}
    if chapter:
        where = {"$and": [{"source_id": source_id}, {"chapter": chapter}]}
    result = collection.get(where=where, include=["documents", "metadatas"])
    pairs = [
        {"text": doc, "metadata": meta}
        for doc, meta in zip(result["documents"], result["metadatas"])
    ]
    pairs.sort(key=lambda x: (
        x["metadata"].get("chapter_index", 0),
        x["metadata"].get("chunk_index", 0),
    ))
    return pairs


def embed_note(collection, note_id: int, body: str, topic_slug: str) -> str:
    import uuid
    chroma_id = f"note-{note_id}-{uuid.uuid4().hex[:8]}"
    collection.add(
        ids=[chroma_id],
        documents=[body],
        metadatas=[{
            "topic": topic_slug,
            "source_id": 0,
            "source_ref": "",
            "source_title": "",
            "source_type": "note",
            "kind": "note",
            "chapter": "",
            "chapter_index": 0,
            "chunk_index": 0,
            "page": 0,
            "timestamp_seconds": 0,
        }],
    )
    return chroma_id


def delete_note_embedding(collection, chroma_id: str) -> None:
    try:
        collection.delete(ids=[chroma_id])
    except Exception:
        pass
