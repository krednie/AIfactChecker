"""
backend/scraper.py — Multi-source fact-check corpus builder.

Sources (in priority order):
1. Google Fact Check Tools API  — IFCN-verified, structured, bulk
2. Verified RSS feeds            — BOOM, AltNews, Vishvas, NewsMeter
3. Offline seed corpus           — fallback if < 50 live articles scraped

Usage:
    python -m backend.scraper            # scrapes all
    python -m backend.scraper --source google --limit 500
    python -m backend.scraper --source rss
"""

import asyncio
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg

# ── Data model ────────────────────────────────────────────────────────────── #

@dataclass
class Article:
    url: str
    title: str
    body: str
    source: str
    source_tier: str
    scraped_at: str
    url_hash: str = ""

    def __post_init__(self):
        self.url_hash = hashlib.md5(self.url.encode()).hexdigest()


# ── Shared helpers ────────────────────────────────────────────────────────── #

_SEEN_HASHES: set[str] = set()      # url_hash → already scraped (cross-run)
_SEEN_TITLE_FINGERPRINTS: set[int] = set()  # cheap near-dedup on title words

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Feedfetcher-Google; (+http://www.google.com/feedfetcher.html)",
    "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/125.0",
]
_ua_index = 0


def _load_seen_hashes_from_corpus() -> None:
    """
    Pre-populate _SEEN_HASHES and _SEEN_TITLE_FINGERPRINTS from the existing
    corpus JSONL so that re-running the scraper skips already-known articles.

    Called once at module import time. Safe to call if the file doesn't exist.
    """
    global _SEEN_HASHES, _SEEN_TITLE_FINGERPRINTS
    corpus_path = cfg.CORPUS_JSONL_PATH
    if not corpus_path.exists():
        return
    count = 0
    try:
        with open(corpus_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url_hash = rec.get("url_hash", "")
                if url_hash:
                    _SEEN_HASHES.add(url_hash)
                title = rec.get("title", "")
                if title:
                    fp = hash(tuple(title.lower().split()[:8]))
                    _SEEN_TITLE_FINGERPRINTS.add(fp)
                count += 1
        logger.info("Cross-run dedup: loaded {} existing url_hashes from corpus", count)
    except Exception as e:
        logger.warning("Could not load existing corpus for dedup: {}", e)


# Eagerly load at import time so all calls to _dedup() benefit immediately.
_load_seen_hashes_from_corpus()


def _next_ua() -> str:
    global _ua_index
    ua = USER_AGENTS[_ua_index % len(USER_AGENTS)]
    _ua_index += 1
    return ua


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _fetch(client: httpx.AsyncClient, url: str, **kwargs) -> str | None:
    try:
        r = await client.get(
            url, headers={"User-Agent": _next_ua()}, follow_redirects=True, **kwargs
        )
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning(f"Fetch failed ({url}): {e}")
        return None


def _dedup(article: Article) -> bool:
    """Return True (and register) if article is new; False if duplicate."""
    # 1. Exact URL dedup
    if article.url_hash in _SEEN_HASHES:
        return False
    # 2. Cheap title near-dedup (first 8 words)
    title_fp = hash(tuple(article.title.lower().split()[:8]))
    if title_fp in _SEEN_TITLE_FINGERPRINTS:
        return False
    _SEEN_HASHES.add(article.url_hash)
    _SEEN_TITLE_FINGERPRINTS.add(title_fp)
    return True


def _make_article(url: str, title: str, body: str, source: str, source_tier: str) -> Article | None:
    title = _clean(title)
    body = _clean(body)
    if not url or not title:
        return None
    a = Article(
        url=url, title=title,
        body=body or title,
        source=source, source_tier=source_tier,
        scraped_at=datetime.utcnow().isoformat(),
    )
    return a if _dedup(a) else None


# ── Source 1: Google Fact Check Tools API ─────────────────────────────────── #

# Broad English-language + India-specific queries
_GOOGLE_QUERIES = [
    # India topics
    "India", "Modi", "BJP", "Congress", "vaccine India", "Aadhaar",
    "UPI", "rupee", "election India", "Kashmir", "Pakistan India",
    "Bollywood", "WhatsApp forward", "viral India",
    # Global health & science
    "COVID", "cancer cure", "climate change", "5G", "autism vaccine",
    # General misinformation themes
    "conspiracy", "fake photo", "manipulated video", "misleading",
    "false claim", "misinformation", "viral video",
    # Politics
    "election fraud", "political", "protest",
]

_GOOGLE_API_BASE = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


async def _scrape_google_factcheck(
    client: httpx.AsyncClient, max_per_query: int = 100, max_total: int = 800
) -> list[Article]:
    """Query Google Fact Check Tools API across many topics."""
    api_key = cfg.GOOGLE_FACT_CHECK_API_KEY
    if not api_key:
        logger.warning("GOOGLE_FACT_CHECK_API_KEY not set — skipping Google API source")
        return []

    articles: list[Article] = []

    for query in _GOOGLE_QUERIES:
        if len(articles) >= max_total:
            break

        page_token: str | None = None
        fetched_this_query = 0

        while fetched_this_query < max_per_query:
            params: dict = {
                "key": api_key,
                "query": query,
                "pageSize": 100,
                "languageCode": "en",
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                r = await client.get(_GOOGLE_API_BASE, params=params, timeout=20)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                logger.warning(f"Google API error for query '{query}': {e}")
                break

            for claim_obj in data.get("claims", []):
                claimant = claim_obj.get("claimant", "")
                claim_text = claim_obj.get("text", "")
                if not claim_text:
                    continue

                for review in claim_obj.get("claimReview", []):
                    url = review.get("url", "")
                    title = review.get("title", claim_text)
                    publisher = review.get("publisher", {}).get("name", "")
                    rating = review.get("textualRating", "")
                    review_date = review.get("reviewDate", "")

                    body = (
                        f"Claim: {claim_text}. "
                        f"Claimant: {claimant}. "
                        f"Rating: {rating}. "
                        f"Reviewed by: {publisher}. "
                        f"Date: {review_date}."
                    )

                    art = _make_article(
                        url=url or f"https://google.com/factcheck/{hashlib.md5(claim_text.encode()).hexdigest()}",
                        title=title,
                        body=body,
                        source="google_factcheck",
                        source_tier="verified",
                    )
                    if art:
                        articles.append(art)
                        fetched_this_query += 1

            page_token = data.get("nextPageToken")
            if not page_token:
                break  # no more pages for this query

        if fetched_this_query:
            logger.debug(f"Google API '{query}': {fetched_this_query} claims")

    logger.info(f"Google Fact Check API: {len(articles)} articles total")
    return articles


# ── Source 2: Verified RSS feeds ───────────────────────────────────────────── #

_RSS_SOURCES = [
    # (url, source_name, source_tier)
    ("https://www.boomlive.in/fact-check/rss",          "boom",        "portal"),
    ("https://www.boomlive.in/feed",                     "boom",        "portal"),
    ("https://www.altnews.in/feed/",                     "altnews",     "portal"),
    ("https://www.vishvasnews.com/feed/",                "vishvas",     "verified"),
    ("https://newsmobile.in/feed/",                      "newsmobile",  "verified"),
    ("https://www.factcrescendo.com/feed/",              "factcrescendo","portal"),
    ("https://newschecker.in/feed",                      "newschecker", "portal"),
    ("https://www.indiatoday.in/rss/1206514",            "indiatoday",  "verified"),
    ("https://newsmeter.in/feed",                        "newsmeter",   "portal"),
]


def _parse_rss_xml(xml_text: str, source: str, source_tier: str) -> list[Article]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for entry in entries:
        # Title
        for tag in ["title", "atom:title"]:
            el = entry.find(tag) if not tag.startswith("atom:") else entry.find(tag, ns)
            if el is not None and el.text:
                title = el.text.strip()
                break
        else:
            continue

        # URL
        link_el = entry.find("link")
        if link_el is not None:
            url = (link_el.text or link_el.get("href", "")).strip()
        else:
            link_el = entry.find("atom:link", ns)
            url = link_el.get("href", "") if link_el is not None else ""
        if not url:
            continue

        # Body
        body = ""
        for tag in [
            "description",
            "{http://purl.org/rss/1.0/modules/content/}encoded",
        ]:
            el = entry.find(tag)
            if el is not None and el.text:
                body = _clean(el.text)
                break

        art = _make_article(url, title, body, source, source_tier)
        if art:
            articles.append(art)

    return articles


async def _scrape_all_rss(client: httpx.AsyncClient) -> list[Article]:
    seen_sources: set[str] = set()
    tasks = []
    sources_meta = []

    for rss_url, source, source_tier in _RSS_SOURCES:
        # Try each URL but skip duplicate successful source names
        if source in seen_sources:
            # We'll try as fallback
            pass
        seen_sources.add(source)
        tasks.append(_fetch(client, rss_url))
        sources_meta.append((source, source_tier))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    articles: list[Article] = []
    per_source: dict[str, int] = {}

    for xml_text, (source, source_tier) in zip(results, sources_meta):
        if not isinstance(xml_text, str) or not xml_text:
            continue
        batch = _parse_rss_xml(xml_text, source, source_tier)
        articles.extend(batch)
        per_source[source] = per_source.get(source, 0) + len(batch)

    for src, count in per_source.items():
        logger.info(f"RSS {src}: {count} articles")
    logger.info(f"RSS total: {len(articles)} articles")
    return articles


# ── Source 3: Offline seed corpus ──────────────────────────────────────────── #

_SEED_PATH = Path(__file__).parent.parent / "data" / "seed.json"


def _load_seed() -> list[Article]:
    if not _SEED_PATH.exists():
        return []
    with open(_SEED_PATH, encoding="utf-8") as f:
        records = json.load(f)
    articles = []
    for r in records:
        art = _make_article(
            url=r.get("url", ""),
            title=r.get("title", ""),
            body=r.get("body", ""),
            source=r.get("source", "seed"),
            source_tier=r.get("source_tier", "portal"),
        )
        if art:
            articles.append(art)
    logger.info(f"Seed corpus: {len(articles)} articles loaded")
    return articles


# ── Orchestrator ──────────────────────────────────────────────────────────── #

async def scrape_all(sources: list[str] | None = None) -> list[Article]:
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    all_articles: list[Article] = []

    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        tasks = []
        if not sources or "google" in sources:
            tasks.append(_scrape_google_factcheck(client))
        if not sources or "rss" in sources:
            tasks.append(_scrape_all_rss(client))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
            else:
                logger.error(f"Scraper error: {result}")

    # Fallback to seed if still thin
    if (not sources or "seed" in sources) and len(all_articles) < 50:
        logger.warning(f"Only {len(all_articles)} live articles; loading seed corpus as fallback")
        all_articles.extend(_load_seed())

    logger.info(f"Total articles: {len(all_articles)}")
    return all_articles


def save_corpus(articles: list[Article], path: Path | None = None) -> Path:
    out_path = path or cfg.CORPUS_JSONL_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for article in articles:
            f.write(json.dumps(asdict(article), ensure_ascii=False) + "\n")
    logger.success(f"Saved {len(articles)} articles → {out_path}")
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Viral Claim Radar corpus builder")
    parser.add_argument(
        "--source", nargs="+", choices=["google", "rss", "seed"],
        help="Sources to scrape (default: all)"
    )
    parser.add_argument("--out", type=Path, help="Override output JSONL path")
    parser.add_argument("--limit", type=int, default=800, help="Max articles from Google API")
    args = parser.parse_args()

    articles = asyncio.run(scrape_all(args.source))
    save_corpus(articles, args.out)
