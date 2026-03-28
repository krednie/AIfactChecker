"""
config.py — Single source of truth for all runtime settings.
All modules should import from here rather than calling os.getenv directly.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from /backend)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


class Settings:
    # ── API Keys ──────────────────────────────────────────────────────────
    GROQ_API_KEY: str = os.environ["GROQ_API_KEY"]
    SARVAM_API_KEY: str = os.environ["SARVAM_API_KEY"]
    GOOGLE_FACT_CHECK_API_KEY: str = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "")

    # ── GDELT live search (free, no key required) ───────────────────────
    GDELT_SEARCH_RESULTS: int = int(os.getenv("GDELT_SEARCH_RESULTS", "25"))
    GDELT_TIMESPAN: str = os.getenv("GDELT_TIMESPAN", "6months")

    # ── BM25 pre-filter ───────────────────────────────────────────────────
    # Keyword candidates passed from BM25 → FAISS re-rank
    BM25_CANDIDATES: int = int(os.getenv("BM25_CANDIDATES", "512"))

    # ── Models ────────────────────────────────────────────────────────────
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # ── RAG / FAISS ───────────────────────────────────────────────────────
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "384"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "64"))
    TOP_K: int = int(os.getenv("TOP_K", "8"))
    FAISS_INDEX_PATH: Path = _ROOT / os.getenv("FAISS_INDEX_PATH", "data/faiss.index")
    CHUNK_META_PATH: Path = _ROOT / os.getenv("CHUNK_META_PATH", "data/chunk_meta.pkl")

    # ── Corpus gap threshold (below this → Uncertain) ─────────────────────
    CORPUS_MISS_THRESHOLD: float = float(os.getenv("CORPUS_MISS_THRESHOLD", "0.45"))

    # ── Scraper ───────────────────────────────────────────────────────────
    SCRAPER_RATE_LIMIT: float = float(os.getenv("SCRAPER_RATE_LIMIT_SECONDS", "1.5"))
    CORPUS_JSONL_PATH: Path = _ROOT / os.getenv("CORPUS_JSONL_PATH", "data/scraped_corpus.jsonl")

    # ── Server ────────────────────────────────────────────────────────────
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # ── Trust tiers for re-ranking ────────────────────────────────────────
    TRUST_TIERS: dict = {
        "govt": 1.5,       # PIB, government advisories
        "verified": 1.2,   # WHO, CDC, verified org
        "portal": 1.0,     # AltNews, BOOM, Reuters, AFP
    }


cfg = Settings()
