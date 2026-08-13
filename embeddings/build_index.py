"""
One-time (or re-run-on-data-change) script: reads every course from the
courses table, builds the embedding text per the decided strategy
(title + syllabus_text, falling back to title alone when syllabus_text is
'N/A'), embeds it, and writes it into a Chroma collection.

Run this after loading/updating the courses table, before starting the app:

    python -m embeddings.build_index
"""

import chromadb

from config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME
from db.connection import get_connection
from embeddings.embedder import embed_text


def build_embedding_text(title: str, syllabus_text: str) -> str:
    """Course-level embedding text: title + syllabus, or title alone when
    syllabus_text is missing ('N/A') -- degraded signal beats no signal."""
    if not syllabus_text or syllabus_text.strip().upper() == "N/A":
        return title
    return f"{title}. {syllabus_text}"


def build_index() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT course_code, title, department, semester, credits, level, syllabus_text
        FROM courses
    """)
    courses = cur.fetchall()
    conn.close()

    print(f"Loaded {len(courses)} courses from the database.")

    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    # Fresh build each run -- delete-and-recreate keeps this idempotent,
    # so re-running after a course-data update doesn't leave stale vectors.
    try:
        client.delete_collection(CHROMA_COLLECTION_NAME)
    except Exception:
        pass  # collection didn't exist yet -- fine
    collection = client.create_collection(CHROMA_COLLECTION_NAME)

    ids, embeddings, documents, metadatas = [], [], [], []

    for course in courses:
        text_to_embed = build_embedding_text(course["title"], course["syllabus_text"])
        vector = embed_text(text_to_embed)

        ids.append(course["course_code"])
        embeddings.append(vector)
        documents.append(text_to_embed)
        metadatas.append({
            "course_code": course["course_code"],
            "title": course["title"],
            "department": course["department"] or "",
            "semester": course["semester"] or "",
            "credits": course["credits"] if course["credits"] is not None else 0,
            "level": course["level"] or "",
        })

    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    print(f"Indexed {len(ids)} courses into Chroma at {CHROMA_PERSIST_DIR}")


if __name__ == "__main__":
    build_index()
