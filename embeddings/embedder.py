"""
Thin wrapper around sentence-transformers. The model is loaded once at
module import time and reused -- loading it per-call would be needlessly
slow (it's a real neural net, not a lookup table).
"""

from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL_NAME

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float]:
    """Embed a single string, returning a plain Python list of floats
    (Chroma expects list-of-floats, not a numpy array)."""
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")
    model = _get_model()
    vector = model.encode(text, convert_to_numpy=True)
    return vector.tolist()
