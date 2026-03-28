"""
backend/gdelt_search.py — Live GDELT DOC 2.0 evidence search.

GDELT (Global Database of Events, Language and Tone) monitors global news
in real-time and provides a free, no-key REST API over its article index.

API: https://api.gdeltproject.org/api/v2/doc/doc
  - No API key required
  - Up to 250 results per call
  - Covers news from last 3 months by default (or specify timespan)
  - Returns: title, URL, domain, language, seendate

How we use it:
  When FAISS has a corpus miss, query GDELT with the claim text.
  Article titles + domains become evidence passages for the Groq stance LLM.
  This gives us fresh, global news coverage for claims not in our local corpus.

Graceful degradation:
  - Any network/parse error → returns [] silently
  - Never raises — callers always get a list (possibly empty)
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

import httpx
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg
from backend.retriever import Chunk, RetrievedChunk


# ── Constants ─────────────────────────────────────────────────────────────── #

_GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = 12.0
_DEFAULT_RECORDS = 25
_DEFAULT_SCORE   = 0.55     # synthetic score — title-only evidence, be conservative
_TIMESPAN        = "3months"  # rolling window GDELT searches within
_MAX_RETRIES     = 1
_RETRY_WAIT      = 0        # no retry
_GDELT_SEMAPHORE: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _GDELT_SEMAPHORE
    # Late init so it attaches to the correct running event loop
    if _GDELT_SEMAPHORE is None:
        _GDELT_SEMAPHORE = asyncio.Semaphore(5)  # allow parallel GDELT searches
    return _GDELT_SEMAPHORE


# Domains known to publish credible fact-checks / authoritative news
_VERIFIED_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "factcheck.org", "snopes.com", "politifact.com", "fullfact.org",
    "who.int", "cdc.gov", "pib.gov.in",
    "thehindu.com", "ndtv.com", "indiatoday.in",
    "altnews.in", "boomlive.in", "afp.com", "factcheck.afp.com",
}

_GOVT_DOMAINS = {
    "pib.gov.in", "moh.gov.in", "who.int", "cdc.gov",
    "mohfw.gov.in", "rbi.org.in", "meity.gov.in",
}

_GOVT_TLDS = (".gov", ".gov.in", ".nic.in", ".mil", ".edu")


# ── Public API ────────────────────────────────────────────────────────────── #

async def gdelt_search(
    query: str,
    n: int = cfg.GDELT_SEARCH_RESULTS,
    timespan: str = _TIMESPAN,
) -> list[RetrievedChunk]:
    """
    Search GDELT DOC 2.0 for `query` and return results as RetrievedChunks.
    Uses an asyncio.Semaphore (limit=1) to avoid HTTP 429 when called in parallel.

    Args:
        query:    Claim text to search for.
        n:        Max number of results (1–250).
        timespan: Rolling time window, e.g. '1month', '6months', '1year'.

    Returns:
        List of RetrievedChunk objects — may be empty on error.
    """
    if not query:
        return []

    n = min(max(1, n), 250)

    params = {
        "query": query[:500],
        "mode": "artlist",
        "maxrecords": n,
        "format": "json",
        "timespan": timespan,
        "sort": "hybridrel",   # hybrid relevance (keyword + recency)
    }

    data = None
    sem = _get_semaphore()
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with sem:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.get(_GDELT_ENDPOINT, params=params)
                    if resp.status_code == 429:
                        logger.warning("GDELT rate-limited (429), attempt {}/{} — waiting {}s", attempt, _MAX_RETRIES, _RETRY_WAIT)
                        await asyncio.sleep(_RETRY_WAIT)
                        continue  # actually retry the loop
                    resp.raise_for_status()
                    # Guard against non-JSON responses
                    ct = resp.headers.get("content-type", "")
                    if "json" not in ct:
                        logger.warning("GDELT returned non-JSON ({}), treating as empty", ct)
                        return []
                    data = resp.json()
                    break  # success
        except httpx.TimeoutException:
            logger.warning("GDELT search timed out (attempt {}), query: {:.60s}…", attempt, query)
            continue
        except httpx.HTTPStatusError as e:
            logger.warning("GDELT HTTP {}: {:.60s}", e.response.status_code, str(e))
            return []
        except Exception as e:
            logger.warning("GDELT unexpected error: {}", e)
            return []

    if data is None:
        logger.warning("GDELT exhausted all {} retries for: {:.60s}…", _MAX_RETRIES, query)
        return []

    articles = data.get("articles", [])
    if not articles:
        logger.debug("GDELT returned 0 results for: {:.60s}…", query)
        return []

    chunks = _parse_articles(articles)
    logger.info("GDELT: {} results for '{:.50s}…'", len(chunks), query)
    return chunks


# ── Parsing ───────────────────────────────────────────────────────────────── #

def _parse_articles(articles: list[dict]) -> list[RetrievedChunk]:
    results: list[RetrievedChunk] = []
    seen_urls: set[str] = set()

    for item in articles:
        url    = item.get("url", "").strip()
        title  = item.get("title", "").strip()
        domain = item.get("domain", "").strip().lower()
        seen_at = item.get("seendate", "")
        lang = item.get("language", "English")

        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)

        # Build richer evidence text: title + temporal context + source authority
        evidence_parts = [f'"{title}"']
        if seen_at:
            try:
                evidence_parts.append(
                    f"[reported {seen_at[:4]}-{seen_at[4:6]}-{seen_at[6:8]}]"
                )
            except Exception:
                pass
        if domain:
            evidence_parts.append(f"[source: {domain}]")

        evidence_text = " ".join(evidence_parts)
        source_tier = _infer_tier(domain)
        source_name = domain.split(".")[0] if domain else "gdelt"

        # Trust-tier boosts
        tier_boost = {"govt": 1.15, "verified": 1.05, "portal": 1.0}.get(source_tier, 1.0)
        score = round(_DEFAULT_SCORE * tier_boost, 3)

        chunk = Chunk(
            chunk_id=int(hashlib.md5(url.encode()).hexdigest()[:8], 16),
            text=evidence_text,
            title=title[:200],
            url=url,
            source=source_name,
            source_tier=source_tier,
        )
        results.append(RetrievedChunk(chunk=chunk, raw_score=score, boosted_score=score))

    return results


def _infer_tier(domain: str) -> str:
    if not domain:
        return "portal"
    if domain in _GOVT_DOMAINS or any(domain.endswith(tld) for tld in _GOVT_TLDS):
        return "govt"
    if domain in _VERIFIED_DOMAINS:
        return "verified"
    return "portal"
