"""
backend/ddg_search.py — DuckDuckGo HTML search for live evidence.

Uses the DDG HTML endpoint (https://html.duckduckgo.com/html/) which is
free, requires no API key, and returns real web search results.

Parsing strategy:
  - Request the HTML page with a simple form POST
  - Parse with Python's html.parser (no bs4 dependency)
  - Extract result titles, snippets, and URLs from the DDG HTML structure
  - Both direct href and uddg= redirect wrappers are handled (DDG alternates)

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
_TIMEOUT = 20.0   # raised: Render cold-start + DDG latency needs headroom
_MAX_RESULTS = 12
_DEFAULT_SCORE = 999.0  # massively boosted per user request so DDG always ranks first
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_DDG_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://duckduckgo.com/",
    "Origin": "https://duckduckgo.com",
}

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

    DDG HTML structure per result (as of 2025):
      <div class="result results_links results_links_deep web-result">
        <div class="links_main links_deep result__body">
          <h2 class="result__title">
            <a rel="nofollow" class="result__a" href="DIRECT_URL">Title</a>
          </h2>
          ...
          <a class="result__snippet" href="DIRECT_URL">Snippet text...</a>
        </div>
      </div>

    Notes:
    - DDG switched from uddg= redirect URLs to direct hrefs for result__a.
      Both formats are handled gracefully.
    - result__snippet is an <a> tag whose text content is the snippet.
    - cls can be None if the tag has no class attribute — guard accordingly.
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
        cls = attr_dict.get("class") or ""   # guard: class can be None

        if tag == "a" and "result__a" in cls:
            self._in_result_a = True
            self._current_text = []
            href = attr_dict.get("href") or ""
            self._current["url"] = self._extract_url(href)

        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True
            self._current_text = []
            # snippet anchor also carries a direct URL — use as fallback
            href = attr_dict.get("href") or ""
            if not self._current.get("url"):
                self._current["url"] = self._extract_url(href)

    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_result_a:
            self._in_result_a = False
            title = " ".join(t for t in self._current_text if t).strip()
            if title:
                self._current["title"] = title

        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            snippet = " ".join(t for t in self._current_text if t).strip()
            self._current["snippet"] = snippet
            # Commit result if we have at least a URL and title
            if self._current.get("url") and self._current.get("title"):
                self.results.append(self._current)
            self._current = {}

    def handle_data(self, data: str):
        if self._in_result_a or self._in_snippet:
            stripped = data.strip()
            if stripped:
                self._current_text.append(stripped)

    @staticmethod
    def _extract_url(href: str) -> str:
        """Extract real URL — handles both direct hrefs and uddg= redirect wrappers."""
        if not href:
            return ""
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

    html = await _fetch_ddg_html(query)
    if not html:
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


async def _fetch_ddg_html(query: str) -> str:
    """Fetch DDG HTML via POST; fall back to GET if POST returns no results."""
    q = query[:300]
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        # --- Primary: POST (standard DDG HTML form) ---
        try:
            resp = await client.post(
                _DDG_URL,
                data={"q": q, "b": "", "kl": ""},
                headers=_DDG_HEADERS,
            )
            resp.raise_for_status()
            html = resp.text
            # Quick sanity check — if results are present we're done
            if "result__a" in html:
                return html
            logger.debug("DDG POST returned no result__a — trying GET fallback")
        except httpx.TimeoutException:
            logger.warning("DDG POST timed out for: {:.60s}…", query)
        except Exception as e:
            logger.warning("DDG POST error: {} — trying GET fallback", e)

        # --- Fallback: GET (some regions/IPs work better with GET) ---
        try:
            resp = await client.get(
                _DDG_URL,
                params={"q": q, "kl": ""},
                headers=_DDG_HEADERS,
            )
            resp.raise_for_status()
            return resp.text
        except httpx.TimeoutException:
            logger.warning("DDG GET timed out for: {:.60s}…", query)
        except Exception as e:
            logger.warning("DDG GET error: {}", e)

    return ""


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

        # Trust-tier boosts on top of the already-high base score
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
