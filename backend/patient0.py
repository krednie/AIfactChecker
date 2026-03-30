"""
backend/patient0.py — Origin tracing ("Patient 0").

Strategy:
  1. Extract 3-5 query keywords via LLM
  2. Wayback Machine CDX API — score by URL-slug word overlap
  3. Take highest-confidence / earliest-date result.

Note: DDG is NOT used here. Only the verifier uses DDG for live evidence.
Hard timeout: 15 s so we never block the pipeline.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import quote

import httpx
from groq import AsyncGroq
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg


# ── Models ────────────────────────────────────────────────────────────────── #

class OriginType(str, Enum):
    NEWS_ARTICLE = "News Article"
    SOCIAL_POST  = "Social Media Post"
    GOVERNMENT   = "Government Source"
    SATIRE       = "Satire/Parody"
    UNKNOWN      = "Unknown"


@dataclass
class OriginResult:
    found: bool
    earliest_url:  str | None
    earliest_date: str | None     # ISO-8601 or None when only DDG found it
    origin_type:   OriginType
    confidence:    str            # "High" | "Medium" | "Low"
    keywords_used: list[str]


ORIGIN_NOT_FOUND = OriginResult(
    found=False,
    earliest_url=None,
    earliest_date=None,
    origin_type=OriginType.UNKNOWN,
    confidence="Low",
    keywords_used=[],
)

CDX_BASE      = "https://web.archive.org/cdx/search/cdx"
CDX_TIMEOUT   = 3.5  # s per CDX request
TOTAL_TIMEOUT = 15   # s hard cap for the whole find_origin call

# ── Confidence thresholds ─────────────────────────────────────────────────── #
# CDX: overlap of claim words vs URL slug  (URLs are short → lower bar)
_CDX_HIGH   = 0.55
_CDX_MEDIUM = 0.25   # was 0.50 — lowered so more Wayback hits qualify

_CONF_RANK = {"High": 3, "Medium": 2, "Low": 1}


# ── Helpers ───────────────────────────────────────────────────────────────── #

def _word_overlap(claim_words: list[str], text: str) -> float:
    """Return fraction of claim_words present in `text`."""
    if not claim_words:
        return 0.0
    text_words = set(re.sub(r"[^a-z0-9]", " ", text.lower()).split())
    return sum(1 for w in claim_words if w in text_words) / len(claim_words)


def _claim_words(claim: str) -> list[str]:
    words = [w for w in re.sub(r"[^a-z0-9]", " ", claim.lower()).split() if len(w) > 2]
    return words or claim.lower().split()


# ── LLM keyword extraction ────────────────────────────────────────────────── #

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def _extract_keywords(claim: str) -> list[str]:
    client = AsyncGroq(api_key=cfg.GROQ_API_KEY)
    resp = await client.chat.completions.create(
        model=cfg.GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract 3-5 specific, distinctive keywords or short phrases from the claim "
                    "that would help find its origin on the internet. "
                    'Return ONLY a JSON array of strings: ["keyword1", "keyword2"]'
                ),
            },
            {"role": "user", "content": f"Claim: {claim}"},
        ],
        temperature=0.0,
        max_tokens=128,
        response_format={"type": "json_object"},
    )
    raw  = resp.choices[0].message.content
    data = json.loads(raw)
    if isinstance(data, list):
        return [str(k) for k in data]
    for key in ("keywords", "words", "phrases"):
        if key in data:
            return [str(k) for k in data[key]]
    return []


# ── Wayback CDX lookup ────────────────────────────────────────────────────── #

async def _cdx_search(query: str, client: httpx.AsyncClient) -> list[dict]:
    """Fetch up to 150 CDX rows for a keyword wildcard search."""
    params = {
        "url":      f"*{quote(query)}*",
        "output":   "json",
        "fl":       "original,timestamp,statuscode",
        "limit":    "150",
        "from":     "20100101",
        "filter":   "statuscode:200",
        "collapse": "urlkey",
    }
    try:
        r = await client.get(CDX_BASE, params=params, timeout=CDX_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        if len(rows) < 2:
            return []
        header    = rows[0]
        data_rows = rows[1:]
        oi        = header.index("original")
        ti        = header.index("timestamp")
        out = []
        for row in data_rows:
            ts   = row[ti]
            date = datetime.strptime(ts[:8], "%Y%m%d").strftime("%Y-%m-%d")
            out.append({
                "url":      f"https://web.archive.org/web/{ts}/{row[oi]}",
                "original": row[oi],
                "date":     date,
            })
        return out
    except Exception as e:
        logger.debug(f"CDX search failed for '{query}': {e}")
        return []



# ── Origin-type classifier ────────────────────────────────────────────────── #

async def _classify_origin(url: str) -> OriginType:
    d = url.lower()
    if any(x in d for x in ["twitter.com", "facebook.com", "instagram.com",
                              "t.me", "whatsapp", "reddit.com"]):
        return OriginType.SOCIAL_POST
    if any(x in d for x in ["gov.in", "nic.in", "gov.uk", "cdc.gov", "who.int"]):
        return OriginType.GOVERNMENT
    if any(x in d for x in ["theonion.com", "thebeaverton.com", "clickhole.com"]):
        return OriginType.SATIRE
    if any(x in d for x in ["reuters.com", "bbc.com", "ndtv.com", "thehindu.com",
                              "hindustantimes.com", "indiatoday.in"]):
        return OriginType.NEWS_ARTICLE
    return OriginType.UNKNOWN


# ── Core logic ────────────────────────────────────────────────────────────── #

async def _find_origin_inner(claim: str) -> OriginResult:
    # 1 — keywords
    try:
        keywords = await _extract_keywords(claim)
    except Exception as e:
        logger.warning(f"Keyword extraction failed: {e}")
        keywords = claim.split()[:5]

    if not keywords:
        return ORIGIN_NOT_FOUND

    cwords = _claim_words(claim)

    # 2 — CDX only (DDG is reserved for verifier.py — avoids rate-limiting)
    async with httpx.AsyncClient() as http_client:
        cdx_tasks = [_cdx_search(kw, http_client) for kw in keywords[:3]]
        cdx_results_list = await asyncio.gather(*cdx_tasks, return_exceptions=True)

    # 3 — score CDX by URL-slug overlap
    scored: list[tuple[dict, str]] = []
    for rlist in cdx_results_list:
        if not isinstance(rlist, list):
            continue
        for cand in rlist:
            ratio = _word_overlap(cwords, cand["original"])
            if ratio >= _CDX_HIGH:
                scored.append((cand, "High"))
            elif ratio >= _CDX_MEDIUM:
                scored.append((cand, "Medium"))

    all_scored = scored

    if not all_scored:
        logger.info(f"Patient 0: no match found for '{claim[:60]}…'")
        return ORIGIN_NOT_FOUND

    # Sort: highest confidence first, then earliest date
    all_scored.sort(key=lambda item: (-_CONF_RANK.get(item[1], 0), item[0]["date"]))
    best, final_conf = all_scored[0]

    origin_type = await _classify_origin(best["original"])
    real_date   = None if best.get("from_ddg") else best["date"]

    logger.info(
        "Patient 0: '{}…' → {} ({}, {})",
        claim[:50], best["original"][:60], final_conf, real_date or "date unknown"
    )

    return OriginResult(
        found=True,
        earliest_url=best["url"],
        earliest_date=real_date,
        origin_type=origin_type,
        confidence=final_conf,
        keywords_used=keywords,
    )


# ── Public entrypoint ─────────────────────────────────────────────────────── #

async def find_origin(claim: str) -> OriginResult:
    """Find origin with a 15-second hard timeout."""
    try:
        return await asyncio.wait_for(_find_origin_inner(claim), timeout=TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"Patient 0 timed out for: '{claim[:60]}…'")
        return ORIGIN_NOT_FOUND
    except Exception as e:
        logger.error(f"Patient 0 error: {e}")
        return ORIGIN_NOT_FOUND
