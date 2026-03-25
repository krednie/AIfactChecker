"""
scripts/build_index.py — Build FAISS index from scraped corpus.

Usage:
    python scripts/build_index.py
    python scripts/build_index.py --corpus data/scraped_corpus.jsonl --batch 32
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from loguru import logger
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg

# ── Types ──────────────────────────────────────────────────────────────────── #

from backend.retriever import Chunk  # single source of truth for pickling


# ── Text splitter ──────────────────────────────────────────────────────────── #

def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Simple recursive character text splitter."""
    separators = ["\n\n", "\n", ". ", " "]
    if len(text) <= chunk_size:
        return [text]

    for sep in separators:
        parts = text.split(sep)
        if len(parts) > 1:
            chunks = []
            current = ""
            for part in parts:
                piece = part + sep
                if len(current) + len(piece) <= chunk_size:
                    current += piece
                else:
                    if current:
                        chunks.append(current.strip())
                    # start new chunk with overlap
                    current = current[-overlap:] + piece if overlap else piece
            if current:
                chunks.append(current.strip())
            return [c for c in chunks if c]

    # fallback: hard split
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size - overlap)]


# ── Main pipeline ──────────────────────────────────────────────────────────── #

def load_corpus(corpus_path: Path) -> list[dict]:
    articles = []
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                articles.append(json.loads(line))
    logger.info(f"Loaded {len(articles)} articles from {corpus_path}")
    return articles


def chunk_corpus(articles: list[dict]) -> list[Chunk]:
    chunks = []
    chunk_id = 0
    for article in articles:
        combined = f"{article['title']}. {article['body']}"
        parts = _split_text(combined, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)
        for part in parts:
            if len(part.split()) < 10:  # skip tiny fragments
                continue
            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=part,
                source=article["source"],
                source_tier=article["source_tier"],
                url=article["url"],
                title=article["title"],
            ))
            chunk_id += 1
    logger.info(f"Created {len(chunks)} chunks")
    return chunks


def embed_chunks(chunks: list[Chunk], batch_size: int = 64) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading embedding model: {cfg.EMBEDDING_MODEL}")
    model = SentenceTransformer(cfg.EMBEDDING_MODEL)

    texts = [c.text for c in chunks]
    embeddings = []
    for i in tqdm(range(0, len(texts), batch_size), desc="Embedding"):
        batch = texts[i:i + batch_size]
        batch_emb = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        embeddings.append(batch_emb)

    matrix = np.vstack(embeddings).astype("float32")
    logger.info(f"Embedding matrix shape: {matrix.shape}")
    return matrix


def build_faiss_index(embeddings: np.ndarray, chunks: list[Chunk]) -> None:
    import faiss

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner product (cosine for normalized vectors)
    index.add(embeddings)

    # Save FAISS index
    cfg.FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(cfg.FAISS_INDEX_PATH))
    logger.success(f"FAISS index saved → {cfg.FAISS_INDEX_PATH} ({index.ntotal} vectors)")

    # Save chunk metadata
    with open(cfg.CHUNK_META_PATH, "wb") as f:
        pickle.dump(chunks, f)
    logger.success(f"Chunk metadata saved → {cfg.CHUNK_META_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=cfg.CORPUS_JSONL_PATH)
    parser.add_argument("--batch", type=int, default=64)
    args = parser.parse_args()

    if not args.corpus.exists():
        logger.error(f"Corpus not found: {args.corpus}. Run scraper first.")
        sys.exit(1)

    articles = load_corpus(args.corpus)
    chunks = chunk_corpus(articles)
    embeddings = embed_chunks(chunks, args.batch)
    build_faiss_index(embeddings, chunks)
    logger.success("Index build complete!")
