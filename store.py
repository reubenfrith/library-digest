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


def get_or_create_collection(client: chromadb.PersistentClient, course: str):
    name = _slugify(course)
    return client.get_or_create_collection(
        name=name,
        metadata={"course_name": course, "hnsw:space": "cosine"},
        embedding_function=_embedding_fn(),
    )


def list_collections(client: chromadb.PersistentClient) -> list[dict]:
    cols = client.list_collections()
    result = []
    for col in cols:
        full = client.get_collection(col.name, embedding_function=_embedding_fn())
        display = (full.metadata or {}).get("course_name", col.name)
        result.append({
            "name": col.name,
            "display_name": display,
            "total_chunks": full.count(),
        })
    return result


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
    top_k: int = 5,
    module_filter: str = "",
) -> list[dict]:
    count = collection.count()
    if count == 0:
        return []

    n = min(top_k, count)
    kwargs: dict = {
        "query_texts": [query],
        "n_results": n,
        "include": ["documents", "metadatas", "distances"],
    }
    if module_filter:
        kwargs["where"] = {"module": module_filter}

    results = collection.query(**kwargs)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    return [
        {"text": doc, "metadata": meta, "distance": dist}
        for doc, meta, dist in zip(docs, metas, dists)
    ]


def list_sources(collection) -> list[dict]:
    result = collection.get(include=["metadatas"])
    sources: dict[str, dict] = {}

    for meta in result["metadatas"]:
        ref = meta.get("source_ref", "")
        if ref not in sources:
            sources[ref] = {
                "source_ref": ref,
                "source_title": meta.get("source_title", ""),
                "source_type": meta.get("source_type", ""),
                "module": meta.get("module", ""),
                "chunk_count": 0,
            }
        sources[ref]["chunk_count"] += 1

    return list(sources.values())


def delete_source(collection, source_ref: str) -> None:
    result = collection.get(where={"source_ref": source_ref})
    ids = result.get("ids", [])
    if ids:
        collection.delete(ids=ids)


def get_all_chunks_ordered(collection) -> list[dict]:
    result = collection.get(include=["documents", "metadatas"])
    pairs = [
        {"text": doc, "metadata": meta}
        for doc, meta in zip(result["documents"], result["metadatas"])
    ]
    pairs.sort(key=lambda x: (
        x["metadata"].get("chapter_index", 0),
        x["metadata"].get("chunk_index", 0),
    ))
    return pairs
