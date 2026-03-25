"""
backend/patient0.py — Origin tracing ("Patient 0") via Wayback Machine CDX API.

For a given claim:
1. Extract 3-5 query keywords via LLM
2. Search Wayback Machine CDX API for earliest archive date
3. Classify origin type via LLM
4. Return OriginResult with earliest URL, date, and origin type

Hard timeout: 6 seconds (asyncio.wait_for) to not block the UI.
"""

import asyncio
import json
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
    SOCIAL_POST = "Social Media Post"
    GOVERNMENT = "Government Source"
    SATIRE = "Satire/Parody"
    UNKNOWN = "Unknown"


@dataclass
class OriginResult:
    found: bool
    earliest_url: str | None
    earliest_date: str | None          # ISO-8601 date
    origin_type: OriginType
    confidence: str                    # "High" | "Medium" | "Low"
    keywords_used: list[str]


ORIGIN_NOT_FOUND = OriginResult(
    found=False,
    earliest_url=None,
    earliest_date=None,
    origin_type=OriginType.UNKNOWN,
    confidence="Low",
    keywords_used=[],
)

CDX_BASE = "https://web.archive.org/cdx/search/cdx"
CDX_TIMEOUT = 5  # seconds per CDX request
TOTAL_TIMEOUT = 6  # seconds for the entire find_origin call


# ── Keyword extraction ────────────────────────────────────────────────────── #

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def _extract_keywords(claim: str) -> list[str]:
    client = AsyncGroq(api_key=cfg.GROQ_API_KEY)
    response = await client.chat.completions.create(
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
    raw = response.choices[0].message.content
    data = json.loads(raw)
    if isinstance(data, list):
        return [str(k) for k in data]
    for key in ("keywords", "words", "phrases"):
        if key in data:
            return [str(k) for k in data[key]]
    return []


# ── Wayback CDX lookup ────────────────────────────────────────────────────── #

async def _cdx_search(query: str, client: httpx.AsyncClient) -> dict | None:
    """Search CDX API and return earliest result dict or None."""
    params = {
        "url": f"*{quote(query)}*",
        "output": "json",
        "fl": "original,timestamp,statuscode",
        "limit": "5",
        "from": "20100101",
        "filter": "statuscode:200",
        "collapse": "urlkey",
    }
    try:
        r = await client.get(CDX_BASE, params=params, timeout=CDX_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        if len(rows) < 2:  # first row is header
            return None

        # rows[0] is header ["original","timestamp","statuscode"]
        header = rows[0]
        data_rows = rows[1:]

        # Sort by timestamp ascending → earliest
        orig_idx = header.index("original")
        ts_idx = header.index("timestamp")
        data_rows.sort(key=lambda row: row[ts_idx])

        earliest = data_rows[0]
        ts = earliest[ts_idx]
        date = datetime.strptime(ts[:8], "%Y%m%d").strftime("%Y-%m-%d")
        wayback_url = f"https://web.archive.org/web/{ts}/{earliest[orig_idx]}"

        return {"url": wayback_url, "original": earliest[orig_idx], "date": date}
    except Exception as e:
        logger.debug(f"CDX search failed for '{query}': {e}")
        return None


# ── Origin type classification ────────────────────────────────────────────── #

async def _classify_origin(url: str) -> OriginType:
    domain = url.lower()
    if any(d in domain for d in ["twitter.com", "facebook.com", "instagram.com",
                                   "t.me", "whatsapp", "reddit.com"]):
        return OriginType.SOCIAL_POST
    if any(d in domain for d in ["gov.in", "nic.in", "gov.uk", "cdc.gov", "who.int"]):
        return OriginType.GOVERNMENT
    if any(d in domain for d in ["theonion.com", "thebeaverton.com", "clickhole.com"]):
        return OriginType.SATIRE
    if any(d in domain for d in ["reuters.com", "bbc.com", "ndtv.com", "thehindu.com",
                                   "hindustantimes.com", "indiatoday.in"]):
        return OriginType.NEWS_ARTICLE
    return OriginType.UNKNOWN


# ── Public API ────────────────────────────────────────────────────────────── #

async def _find_origin_inner(claim: str) -> OriginResult:
    try:
        keywords = await _extract_keywords(claim)
    except Exception as e:
        logger.warning(f"Keyword extraction failed: {e}")
        # Fallback: first 5 words of claim
        keywords = claim.split()[:5]

    if not keywords:
        return ORIGIN_NOT_FOUND

    async with httpx.AsyncClient() as client:
        tasks = [_cdx_search(kw, client) for kw in keywords[:3]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Pick the earliest valid result
    valid = [r for r in results if isinstance(r, dict) and r]
    if not valid:
        logger.info(f"Patient 0 not found for: '{claim[:60]}…'")
        return OriginResult(
            found=False,
            earliest_url=None,
            earliest_date=None,
            origin_type=OriginType.UNKNOWN,
            confidence="Low",
            keywords_used=keywords,
        )

    best = min(valid, key=lambda r: r["date"])
    origin_type = await _classify_origin(best["original"])

    return OriginResult(
        found=True,
        earliest_url=best["url"],
        earliest_date=best["date"],
        origin_type=origin_type,
        confidence="Medium",
        keywords_used=keywords,
    )


async def find_origin(claim: str) -> OriginResult:
    """Find origin with hard 6-second timeout."""
    try:
        return await asyncio.wait_for(_find_origin_inner(claim), timeout=TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"Patient 0 search timed out for: '{claim[:60]}…'")
        return ORIGIN_NOT_FOUND
    except Exception as e:
        logger.error(f"Patient 0 error: {e}")
        return ORIGIN_NOT_FOUND
