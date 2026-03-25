"""
backend/retriever.py — FAISS-backed semantic retriever with BM25 pre-filter and trust-tier re-ranking.

Pipeline:
  1. BM25 keyword scan (O(n)) → top BM25_CANDIDATES chunks as candidates
  2. FAISS inner-product search on those candidates → top fetch_k by cosine sim
  3. Trust-tier boost → sort → top_k returned

BM25 pre-filter dramatically improves FAISS precision: instead of comparing the
query embedding against ALL corpus vectors, we only embed-compare the top-512
most lexically relevant chunks. This is especially useful for claim verification
where exact keywords (drug names, politician names, dates) matter a lot.

Loads index once at startup. Thread-safe for async FastAPI use.
"""

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from loguru import logger
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg


# ── Chunk type (must match build_index.py) ───────────────────────────────── #

@dataclass
class Chunk:
    chunk_id: int
    text: str
    source: str
    source_tier: str
    url: str
    title: str


@dataclass
class RetrievedChunk:
    chunk: Chunk
    raw_score: float     # cosine similarity from FAISS
    boosted_score: float # after trust-tier multiplier


# ── Singleton loader ──────────────────────────────────────────────────────── #

class Retriever:
    _instance: Optional["Retriever"] = None

    def __init__(self):
        logger.info("Loading FAISS index…")
        self._index = faiss.read_index(str(cfg.FAISS_INDEX_PATH))

        logger.info("Loading chunk metadata…")
        with open(cfg.CHUNK_META_PATH, "rb") as f:
            self._chunks: list[Chunk] = pickle.load(f)

        logger.info(f"Loading embedding model: {cfg.EMBEDDING_MODEL}")
        self._model = SentenceTransformer(cfg.EMBEDDING_MODEL)

        # ── Build BM25 index over all chunk texts ─────────────────────────── #
        logger.info("Building BM25 index over {} chunks…", len(self._chunks))
        tokenized = [c.text.lower().split() for c in self._chunks]
        self._bm25 = BM25Okapi(tokenized)

        logger.success(
            f"Retriever ready — {self._index.ntotal} vectors, "
            f"{len(self._chunks)} chunks, BM25 index built"
        )

    @classmethod
    def get(cls) -> "Retriever":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def retrieve(self, query: str, top_k: int = cfg.TOP_K) -> list[RetrievedChunk]:
        """
        BM25 keyword pre-filter → FAISS semantic search → trust-tier boost → top_k.

        Stage 1 — BM25 keyword scan:
          Tokenise query, score all chunks with BM25Okapi, take top BM25_CANDIDATES
          indices as the candidate set. O(n) scan, no GPU required.

        Stage 2 — FAISS cosine search on candidates:
          Embed query once, build a sub-matrix of candidate vectors from the full
          FAISS flat index, run inner-product search on that sub-matrix.

        Stage 3 — Trust-tier re-rank:
          Multiply FAISS score by tier multiplier (govt > verified > portal),
          sort descending, return top_k.
        """
        query_tokens = query.lower().split()

        # ── Stage 1: BM25 keyword shortlist ──────────────────────────────── #
        bm25_scores = self._bm25.get_scores(query_tokens)
        n_candidates = min(cfg.BM25_CANDIDATES, len(self._chunks))
        candidate_indices = np.argsort(bm25_scores)[::-1][:n_candidates]

        logger.debug(
            "BM25 pre-filter: {}/{} candidates selected",
            len(candidate_indices), len(self._chunks),
        )

        if len(candidate_indices) == 0:
            return []

        # ── Stage 2: FAISS semantic search on sub-matrix ─────────────────── #
        # Reconstruct the candidate vectors from the flat FAISS index
        d = self._index.d  # embedding dimension
        sub_vectors = np.zeros((len(candidate_indices), d), dtype="float32")
        for i, idx in enumerate(candidate_indices):
            self._index.reconstruct(int(idx), sub_vectors[i])

        # Build a temporary flat inner-product index on just the candidates
        sub_index = faiss.IndexFlatIP(d)
        sub_index.add(sub_vectors)

        query_vec = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        ).astype("float32")

        # Over-fetch within candidates, then re-rank
        fetch_k = min(top_k * 4, len(candidate_indices))
        scores, sub_positions = sub_index.search(query_vec, fetch_k)

        # ── Stage 3: Trust-tier boost + sort ─────────────────────────────── #
        results: list[RetrievedChunk] = []
        for score, sub_pos in zip(scores[0], sub_positions[0]):
            if sub_pos < 0:
                continue
            orig_idx = candidate_indices[sub_pos]
            chunk = self._chunks[orig_idx]
            multiplier = cfg.TRUST_TIERS.get(chunk.source_tier, 1.0)
            boosted = float(score) * multiplier
            results.append(RetrievedChunk(
                chunk=chunk,
                raw_score=float(score),
                boosted_score=boosted,
            ))

        results.sort(key=lambda r: r.boosted_score, reverse=True)
        return results[:top_k]

    def is_corpus_miss(self, results: list[RetrievedChunk]) -> bool:
        """Returns True if best raw score is below CORPUS_MISS_THRESHOLD."""
        if not results:
            return True
        return results[0].raw_score < cfg.CORPUS_MISS_THRESHOLD


# ── Module-level convenience function ────────────────────────────────────── #

def retrieve(query: str, top_k: int = cfg.TOP_K) -> list[RetrievedChunk]:
    return Retriever.get().retrieve(query, top_k)
