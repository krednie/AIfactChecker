"""
backend/ddg_search.py — DuckDuckGo HTML search for live evidence.

Uses the DDG HTML endpoint (https://html.duckduckgo.com/html/) which is
free, requires no API key, and returns real web search results.

Parsing strategy:
  - Request the HTML page with a simple form POST
  - Parse with Python's html.parser (no bs4 dependency)
  - Extract result titles, snippets, and URLs from the known DDG HTML structure
  - Convert to RetrievedChunk format for the pipeline

Graceful degradation:
  - Any network/parse error → returns [] silently
  - Never raises — callers always get a list (possibly empty)
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import httpx
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.retriever import Chunk, RetrievedChunk


# ── Constants ─────────────────────────────────────────────────────────────── #

_DDG_URL = "https://html.duckduckgo.com/html/"
_TIMEOUT = 10.0
_MAX_RESULTS = 12
_DEFAULT_SCORE = 0.58  # synthetic — DDG snippets are decent evidence
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Domains known to publish credible fact-checks / authoritative news
_VERIFIED_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "factcheck.org", "snopes.com", "politifact.com", "fullfact.org",
    "who.int", "cdc.gov", "pib.gov.in",
    "thehindu.com", "ndtv.com", "indiatoday.in",
    "altnews.in", "boomlive.in", "afp.com", "factcheck.afp.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com",
    "aljazeera.com", "cnn.com",
}

_GOVT_DOMAINS = {
    "pib.gov.in", "moh.gov.in", "who.int", "cdc.gov",
    "mohfw.gov.in", "rbi.org.in", "meity.gov.in",
}

_GOVT_TLDS = (".gov", ".gov.in", ".nic.in", ".mil", ".edu")


# ── HTML Parser ───────────────────────────────────────────────────────────── #

class _DDGResultParser(HTMLParser):
    """
    Parses DuckDuckGo HTML search results page.
    
    DDG HTML structure per result:
      <div class="result results_links results_links_deep web-result">
        <a class="result__a" href="...">Title</a>
        <a class="result__snippet">Snippet text...</a>
        <span class="result__url__domain">domain.com</span>
      </div>
    
    We extract: title, href (URL), snippet text.
    """
    
    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._in_result_a = False
        self._in_snippet = False
        self._current: dict = {}
        self._current_text: list[str] = []
    
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "")
        
        if tag == "a" and "result__a" in cls:
            self._in_result_a = True
            self._current_text = []
            href = attr_dict.get("href", "")
            # DDG wraps URLs in a redirect: //duckduckgo.com/l/?uddg=REAL_URL&...
            real_url = self._extract_url(href)
            self._current["url"] = real_url
            
        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True
            self._current_text = []
    
    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_result_a:
            self._in_result_a = False
            self._current["title"] = " ".join(self._current_text).strip()
            
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            self._current["snippet"] = " ".join(self._current_text).strip()
            # A complete result has title + url + snippet
            if self._current.get("url") and self._current.get("title"):
                self.results.append(self._current)
            self._current = {}
    
    def handle_data(self, data: str):
        if self._in_result_a or self._in_snippet:
            self._current_text.append(data.strip())
    
    @staticmethod
    def _extract_url(href: str) -> str:
        """Extract real URL from DDG redirect wrapper."""
        if "uddg=" in href:
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                return unquote(match.group(1))
        if href.startswith("http"):
            return href
        return ""


# ── Public API ────────────────────────────────────────────────────────────── #

async def ddg_search(query: str, n: int = _MAX_RESULTS) -> list[RetrievedChunk]:
    """
    Search DuckDuckGo HTML for `query` and return results as RetrievedChunks.
    
    Args:
        query: Claim text to search for.
        n:     Max number of results.
    
    Returns:
        List of RetrievedChunk objects — may be empty on error.
    """
    if not query:
        return []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _DDG_URL,
                data={"q": query[:300], "b": "", "kl": ""},
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            resp.raise_for_status()
            html = resp.text
    except httpx.TimeoutException:
        logger.warning("DDG search timed out for: {:.60s}…", query)
        return []
    except Exception as e:
        logger.warning("DDG search error: {}", e)
        return []

    # Parse HTML
    parser = _DDGResultParser()
    try:
        parser.feed(html)
    except Exception as e:
        logger.warning("DDG HTML parse error: {}", e)
        return []

    if not parser.results:
        logger.debug("DDG returned 0 parsed results for: {:.60s}…", query)
        return []

    chunks = _to_chunks(parser.results[:n])
    logger.info("DDG: {} results for '{:.50s}…'", len(chunks), query)
    return chunks


# ── Conversion ────────────────────────────────────────────────────────────── #

def _to_chunks(results: list[dict]) -> list[RetrievedChunk]:
    """Convert parsed DDG results to RetrievedChunks."""
    chunks: list[RetrievedChunk] = []
    seen_urls: set[str] = set()

    for item in results:
        url = item.get("url", "").strip()
        title = item.get("title", "").strip()
        snippet = item.get("snippet", "").strip()

        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)

        # Skip DDG internal / ad links
        if "duckduckgo.com" in url:
            continue

        # Extract domain
        domain = ""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            pass

        evidence_text = f'"{title}"'
        if snippet:
            evidence_text += f" — {snippet}"
        if domain:
            evidence_text += f" [source: {domain}]"

        source_tier = _infer_tier(domain)
        source_name = domain.split(".")[0] if domain else "ddg"

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
        chunks.append(RetrievedChunk(chunk=chunk, raw_score=score, boosted_score=score))

    return chunks


def _infer_tier(domain: str) -> str:
    if not domain:
        return "portal"
    if domain in _GOVT_DOMAINS or any(domain.endswith(tld) for tld in _GOVT_TLDS):
        return "govt"
    if domain in _VERIFIED_DOMAINS:
        return "verified"
    return "portal"
