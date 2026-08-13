"""
The search_syllabi tool's implementation. Embeds the incoming query,
searches the Chroma collection built by embeddings/build_index.py, and
applies the similarity-threshold guardrail from router_spec.md -- weak
matches get filtered out rather than handed to the LLM as if they were
confident results.
"""

import chromadb

from config import (
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    VECTOR_SEARCH_DEFAULT_TOP_K,
    VECTOR_SEARCH_MIN_SIMILARITY,
)
from embeddings.embedder import embed_text

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
        _collection = _client.get_collection(CHROMA_COLLECTION_NAME)
    return _collection


def _distance_to_similarity(distance: float) -> float:
    """Chroma's default distance metric is L2 (squared euclidean) for
    sentence-transformers vectors, not cosine similarity directly. Convert
    to a 0-1-ish similarity score: closer to 1 = more similar, closer to 0
    = less similar. This is an approximation, not a true cosine score --
    fine for a relative threshold cutoff, not meant as a precise metric."""
    return 1.0 / (1.0 + distance)


def search_syllabi(query: str, top_k: int = VECTOR_SEARCH_DEFAULT_TOP_K) -> dict:
    """
    Search course syllabi semantically. Returns a dict suitable for handing
    back to the LLM as a tool result. Never raises -- errors and "nothing
    relevant found" both come back as structured dicts, not exceptions.
    """
    if not query or not query.strip():
        return {"error": "Empty search query provided."}

    try:
        collection = _get_collection()
        query_vector = embed_text(query)
        results = collection.query(query_embeddings=[query_vector], n_results=top_k)
    except Exception as e:
        return {"error": f"Vector search failed: {e}"}

    matches = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    for course_id, distance, metadata in zip(ids, distances, metadatas):
        similarity = _distance_to_similarity(distance)
        if similarity < VECTOR_SEARCH_MIN_SIMILARITY:
            continue
        matches.append({
            "course_code": course_id,
            "title": metadata.get("title", ""),
            "department": metadata.get("department", ""),
            "semester": metadata.get("semester", ""),
            "level": metadata.get("level", ""),
            "similarity": round(similarity, 3),
        })

    if not matches:
        return {"matches": [], "message": "No relevant syllabus content found for this query."}

    return {"matches": matches}