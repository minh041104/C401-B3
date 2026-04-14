"""
build_index.py — Build ChromaDB index from data/docs/
Uses OpenAI text-embedding-3-small (no local model download needed).
Run once: python build_index.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import chromadb
from openai import OpenAI

DOCS_DIR = Path("data/docs")
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "day09_docs"
CHUNK_SIZE = 500   # words per chunk
CHUNK_OVERLAP = 50
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

client_oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i+size])
        chunks.append(chunk)
        i += size - overlap
    return chunks


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embedding API in batch (max 2048 texts per call)."""
    response = client_oai.embeddings.create(input=texts, model=EMBED_MODEL)
    return [item.embedding for item in response.data]


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env or environment.")
        sys.exit(1)

    print(f"Using OpenAI embeddings ({EMBED_MODEL}) — no local model download needed.")
    print(f"Connecting to ChromaDB at {CHROMA_PATH}...")

    client_db = chromadb.PersistentClient(path=CHROMA_PATH)

    # Recreate collection
    try:
        client_db.delete_collection(COLLECTION_NAME)
        print(f"Deleted old collection '{COLLECTION_NAME}'")
    except Exception:
        pass

    collection = client_db.create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"Created collection '{COLLECTION_NAME}'")

    docs = list(DOCS_DIR.glob("*.txt"))
    if not docs:
        print(f"ERROR: No .txt files found in {DOCS_DIR}")
        sys.exit(1)

    all_ids = []
    all_documents = []
    all_metadatas = []

    for doc_path in docs:
        text = doc_path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        print(f"  {doc_path.name}: {len(text)} chars → {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            all_ids.append(f"{doc_path.stem}_{i:04d}")
            all_documents.append(chunk)
            all_metadatas.append({"source": doc_path.name, "chunk_index": i})

    print(f"\nEmbedding {len(all_ids)} chunks via OpenAI API...")
    # Batch in groups of 100 to avoid hitting token limits
    BATCH = 100
    all_embeddings = []
    for start in range(0, len(all_documents), BATCH):
        batch = all_documents[start:start+BATCH]
        embeddings = embed_batch(batch)
        all_embeddings.extend(embeddings)
        print(f"  Embedded {min(start+BATCH, len(all_documents))}/{len(all_documents)} chunks...")

    collection.add(
        ids=all_ids,
        embeddings=all_embeddings,
        documents=all_documents,
        metadatas=all_metadatas,
    )
    print(f"\n✅ Index built: {len(all_ids)} chunks in '{COLLECTION_NAME}'")

if __name__ == "__main__":
    main()
