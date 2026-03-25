"""
scripts/bulk_scrape.py — Exhaust Google Fact Check API daily quota + all RSS sources.

Strategy:
  - 10,000 requests/day free tier → paginate 100 results × 100 queries = up to 10,000 claims
  - 200+ topic queries covering every major misinformation category
  - All RSS feeds in parallel
  - Appends to existing corpus JSONL (deduplication by URL hash)
  - Rebuilds FAISS index after scraping

Usage:
    python scripts/bulk_scrape.py                      # full run
    python scripts/bulk_scrape.py --no-index           # scrape only, skip index rebuild
    python scripts/bulk_scrape.py --google-only        # skip RSS
    python scripts/bulk_scrape.py --rss-only           # skip Google API
    python scripts/bulk_scrape.py --resume             # append to existing corpus
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg

# ── Config ────────────────────────────────────────────────────────────────── #

GOOGLE_API_BASE = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
PAGE_SIZE = 100       # max per request
CONCURRENCY = 8       # parallel Google API requests
REQUEST_DELAY = 0.05  # 50ms between requests (~1000 req/min, well under quota)
MAX_PER_QUERY = 200   # page through up to 200 results per topic
OUTPUT_PATH = cfg.CORPUS_JSONL_PATH


# ── Massive query bank ────────────────────────────────────────────────────── #
# 200+ queries across every major misinformation category
# Google API deduplicates at the claim level anyway

QUERIES = [
    # ── India: Politics & Government ──────────────────────────────────────
    "India", "Modi", "BJP", "Congress INC", "Rahul Gandhi", "Amit Shah",
    "Yogi Adityanath", "Kejriwal", "Mamata Banerjee", "AAP",
    "election India 2024", "Lok Sabha", "Rajya Sabha", "Parliament India",
    "India constitution", "article 370", "CAA citizenship", "NRC India",
    "farmers protest India", "Manipur", "Adani", "Ambani",

    # ── India: Economy & Finance ───────────────────────────────────────────
    "India GDP", "rupee dollar", "RBI interest rate", "GST India",
    "UPI payment", "Aadhaar", "PAN card", "demonetization India",
    "inflation India", "petrol price India", "LPG price India",
    "India budget", "income tax India",

    # ── India: Health & COVID ──────────────────────────────────────────────
    "COVID India", "vaccine India", "Covaxin", "Covishield", "Sputnik India",
    "COVID death India", "lockdown India", "Omicron India", "dengue India",
    "monkeypox India", "tuberculosis India", "malaria India",
    "AIIMS hospital India", "ayurveda cure India",

    # ── India: Religion & Communal ─────────────────────────────────────────
    "Hindu Muslim India", "mosque temple India", "cow slaughter India",
    "love jihad India", "religious conversion India", "Waqf board India",
    "Ram Mandir Ayodhya", "Babri Masjid", "blasphemy India",
    "minority India", "Dalit India", "SC ST OBC India",

    # ── India: Crime & Social ──────────────────────────────────────────────
    "rape India viral", "lynching India", "encounter India",
    "police brutality India", "corruption India", "scam India",
    "WhatsApp forward viral India", "fake news India",

    # ── India: Military & Foreign Policy ──────────────────────────────────
    "Pakistan India border", "China India LAC", "surgical strike India",
    "Galwan valley", "AFSPA India", "Army India claim",
    "Bangladesh India", "Nepal India", "Sri Lanka India",
    "Afghanistan India", "Russia India Ukraine",

    # ── Pakistan ──────────────────────────────────────────────────────────
    "Pakistan", "Imran Khan", "PMLN", "ISI Pakistan", "Pakistan army",
    "Pakistan economy", "Pakistan election",

    # ── Global: COVID & Vaccines ───────────────────────────────────────────
    "COVID vaccine", "mRNA vaccine", "COVID origin", "lab leak COVID",
    "COVID deaths", "COVID lockdown", "long COVID", "COVID variant",
    "COVID ivermectin", "COVID hydroxychloroquine", "COVID cure",
    "vaccine side effects", "vaccine microchip", "vaccine autism",
    "5G COVID", "Bill Gates vaccine", "WHO COVID",

    # ── Global: Health Misinformation ─────────────────────────────────────
    "cancer cure", "cancer treatment hoax", "HIV AIDS cure",
    "cancer vaccine", "autism vaccine", "autism cause",
    "fluoride water conspiracy", "GMO food danger",
    "organic food cancer", "microwave danger", "5G radiation health",
    "essential oils cure", "bleach cure", "MMS cure",

    # ── Global: Climate & Environment ─────────────────────────────────────
    "climate change", "climate change hoax", "global warming fake",
    "CO2 emissions", "fossil fuel", "renewable energy fake",
    "solar panels dangerous", "wind energy birds", "electric car danger",
    "geoengineering chemtrails", "ozone layer",

    # ── Global: Technology ────────────────────────────────────────────────
    "5G towers danger", "5G health risks", "WiFi radiation",
    "Facebook data", "Google tracking", "AI deepfake",
    "cryptocurrency scam", "Bitcoin fraud", "NFT scam",
    "ChatGPT danger", "robot job loss",

    # ── Global: Politics & Elections ──────────────────────────────────────
    "election fraud", "election rigging", "voter fraud",
    "US election 2024", "Trump Biden", "Ukraine war Russia",
    "NATO expansion Russia", "Israel Gaza Palestine",
    "Hamas attack", "genocide Gaza", "Zelensky",
    "China Taiwan", "North Korea missile",
    "George Soros conspiracy", "WEF great reset",
    "globalism conspiracy", "deep state",

    # ── Global: Economy ───────────────────────────────────────────────────
    "inflation global", "recession 2024", "dollar collapse",
    "gold standard return", "central bank digital currency",
    "food shortage", "wheat export ban", "oil price manipulate",

    # ── Social Media Viral Formats ────────────────────────────────────────
    "misleading photo", "manipulated video", "out of context",
    "old photo new claim", "doctored image", "deepfake video",
    "viral video fake", "false caption", "satire mistaken",

    # ── Misinformation Orgs & Tactics ─────────────────────────────────────
    "misinformation", "disinformation", "propaganda",
    "fake news", "fact check", "debunked",
    "conspiracy theory", "hoax", "rumour viral",
    "WhatsApp rumour", "Telegram fake news",

    # ── Science Denial ────────────────────────────────────────────────────
    "flat earth", "moon landing fake", "evolution fake",
    "dinosaur never existed", "earth age", "creationism science",

    # ── Natural Disasters & Accidents ─────────────────────────────────────
    "earthquake HAARP", "flood caused by India dam",
    "earthquake weather modification", "hurricane geoengineering",

    # ── Celebrities & Viral Claims ────────────────────────────────────────
    "celebrity death hoax", "famous person arrested fake",
    "Bollywood star arrest fake", "cricketer controversy",
    "celebrity charity scam", "influencer fraud", "YouTuber arrested",

    # ── Drugs & Crime ─────────────────────────────────────────────────────
    "drug cartel Mexico", "drug mafia India", "narcotics seized India",
    "crime rate India fake", "murder statistics India",

    # ── Religion Global ───────────────────────────────────────────────────
    "Islam terrorism", "Christian persecution", "Hindu extremism",
    "religious viral claim", "quran misquote", "bible verse fake",

    # ── Africa & Developing World ─────────────────────────────────────────
    "Africa COVID vaccine", "Africa election fraud",
    "Nigeria scam", "Ethiopia conflict",
]

# Deduplicate queries preserving order
_seen = set()
QUERIES = [q for q in QUERIES if not (_seen.add(q.lower()) or q.lower() in _seen - {q.lower()})]


# ── RSS sources (expanded) ────────────────────────────────────────────────── #

RSS_SOURCES = [
    # Indian fact-checkers
    ("https://www.boomlive.in/fact-check/rss",             "boom",           "portal"),
    ("https://www.boomlive.in/feed",                        "boom",           "portal"),
    ("https://www.altnews.in/feed/",                        "altnews",        "portal"),
    ("https://www.vishvasnews.com/feed/",                   "vishvas",        "verified"),
    ("https://newsmobile.in/feed/",                         "newsmobile",     "verified"),
    ("https://www.factcrescendo.com/feed/",                 "factcrescendo",  "portal"),
    ("https://newschecker.in/feed",                         "newschecker",    "portal"),
    ("https://newsmeter.in/feed",                           "newsmeter",      "portal"),
    ("https://www.indiatoday.in/rss/1206514",               "indiatoday",     "verified"),
    ("https://www.indiatoday.in/fact-check/rss",            "indiatoday",     "verified"),
    ("https://www.thequint.com/news/webqoof/rss",           "thequint",       "verified"),
    ("https://factly.in/feed/",                             "factly",         "portal"),
    ("https://www.youturn.in/feed/",                        "youturn",        "portal"),
    # International fact-checkers
    ("https://www.snopes.com/feed/",                        "snopes",         "verified"),
    ("https://www.factcheck.org/feed/",                     "factcheck_org",  "verified"),
    ("https://www.politifact.com/rss/all/",                 "politifact",     "verified"),
    ("https://fullfact.org/feed/",                          "fullfact",       "verified"),
    ("https://www.afp.com/en/rss.xml",                      "afp",            "verified"),
    ("https://apnews.com/apf-factcheck.rss",                "apnews",         "verified"),
    # Health / Science
    ("https://www.who.int/rss-feeds/news-english.xml",      "who",            "govt"),
    ("https://tools.cdc.gov/api/v2/resources/media/403372.rss", "cdc",        "govt"),
]


# ── Helpers ───────────────────────────────────────────────────────────────── #

def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Load existing hashes for dedup ────────────────────────────────────────── #

def _load_existing_hashes(path: Path) -> set[str]:
    seen: set[str] = set()
    if not path.exists():
        return seen
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                h = obj.get("url_hash") or _url_hash(obj.get("url", ""))
                seen.add(h)
            except Exception:
                pass
    logger.info("Loaded {} existing URL hashes from corpus", len(seen))
    return seen


# ── Google Fact Check API ─────────────────────────────────────────────────── #

async def _fetch_google_page(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    query: str,
    page_token: str | None,
) -> dict:
    async with sem:
        params: dict = {
            "key": cfg.GOOGLE_FACT_CHECK_API_KEY,
            "query": query,
            "pageSize": PAGE_SIZE,
            "languageCode": "en",
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            r = await client.get(GOOGLE_API_BASE, params=params, timeout=20)
            r.raise_for_status()
            await asyncio.sleep(REQUEST_DELAY)
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Rate limit hit — sleeping 10s")
                await asyncio.sleep(10)
            else:
                logger.warning("Google API HTTP {} for '{}': {}", e.response.status_code, query, e)
            return {}
        except Exception as e:
            logger.warning("Google API error for '{}': {}", query, e)
            return {}


async def _scrape_query(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    query: str,
    seen_hashes: set[str],
) -> list[dict]:
    """Page through all results for one query. Returns raw article dicts."""
    articles: list[dict] = []
    page_token: str | None = None
    fetched = 0
    pages = 0

    while fetched < MAX_PER_QUERY:
        data = await _fetch_google_page(sem, client, query, page_token)
        if not data:
            break

        for claim_obj in data.get("claims", []):
            claim_text = claim_obj.get("text", "")
            claimant  = claim_obj.get("claimant", "")
            if not claim_text:
                continue

            for review in claim_obj.get("claimReview", []):
                url = review.get("url", "")
                fallback_url = f"https://google.com/factcheck/{hashlib.md5(claim_text.encode()).hexdigest()}"
                url = url or fallback_url
                h = _url_hash(url)

                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                publisher = review.get("publisher", {}).get("name", "")
                rating    = review.get("textualRating", "")
                rev_date  = review.get("reviewDate", "")
                title     = _clean(review.get("title", claim_text))
                body      = _clean(
                    f"Claim: {claim_text}. "
                    f"Claimant: {claimant}. "
                    f"Rating: {rating}. "
                    f"Reviewed by: {publisher}. "
                    f"Date: {rev_date}."
                )

                articles.append({
                    "url": url,
                    "url_hash": h,
                    "title": title[:300],
                    "body": body,
                    "source": "google_factcheck",
                    "source_tier": "verified",
                    "scraped_at": _now(),
                })
                fetched += 1

        page_token = data.get("nextPageToken")
        pages += 1
        if not page_token:
            break

    if fetched:
        logger.debug("'{}': {} claims ({} pages)", query, fetched, pages)
    return articles


async def scrape_google(seen_hashes: set[str], progress: tqdm) -> list[dict]:
    """Run all queries concurrently with a semaphore."""
    if not cfg.GOOGLE_FACT_CHECK_API_KEY:
        logger.error("GOOGLE_FACT_CHECK_API_KEY not set in .env — skipping")
        return []

    sem = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(max_connections=CONCURRENCY + 4, max_keepalive_connections=CONCURRENCY)
    all_articles: list[dict] = []

    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        tasks = [
            _scrape_query(sem, client, q, seen_hashes)
            for q in QUERIES
        ]
        for coro in asyncio.as_completed(tasks):
            batch = await coro
            all_articles.extend(batch)
            progress.update(len(batch))
            progress.set_postfix(total=len(all_articles))

    logger.success("Google Fact Check API: {} new articles", len(all_articles))
    return all_articles


# ── RSS ───────────────────────────────────────────────────────────────────── #

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Feedfetcher-Google; (+http://www.google.com/feedfetcher.html)",
]
_ua_idx = 0

def _next_ua() -> str:
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return ua


def _parse_rss(xml_text: str, source: str, source_tier: str, seen_hashes: set[str]) -> list[dict]:
    articles: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for entry in entries:
        title = ""
        for tag in ["title", "atom:title"]:
            el = entry.find(tag) if not tag.startswith("atom:") else entry.find(tag, ns)
            if el is not None and el.text:
                title = el.text.strip()
                break
        if not title:
            continue

        url = ""
        link_el = entry.find("link")
        if link_el is not None:
            url = (link_el.text or link_el.get("href", "")).strip()
        else:
            link_el = entry.find("atom:link", ns)
            url = (link_el.get("href", "") if link_el is not None else "").strip()
        if not url:
            continue

        h = _url_hash(url)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        body = ""
        for tag in ["description", "{http://purl.org/rss/1.0/modules/content/}encoded"]:
            el = entry.find(tag)
            if el is not None and el.text:
                body = _clean(el.text)
                break

        articles.append({
            "url": url,
            "url_hash": h,
            "title": _clean(title)[:300],
            "body": body or _clean(title),
            "source": source,
            "source_tier": source_tier,
            "scraped_at": _now(),
        })
    return articles


async def scrape_rss(seen_hashes: set[str]) -> list[dict]:
    all_articles: list[dict] = []
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)

    async with httpx.AsyncClient(timeout=20, limits=limits, follow_redirects=True) as client:
        tasks = []
        meta  = []
        for rss_url, source, tier in RSS_SOURCES:
            tasks.append(client.get(rss_url, headers={"User-Agent": _next_ua()}))
            meta.append((source, tier, rss_url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result, (source, tier, rss_url) in zip(results, meta):
        if isinstance(result, Exception):
            logger.warning("RSS {} failed: {}", rss_url, result)
            continue
        try:
            result.raise_for_status()
            batch = _parse_rss(result.text, source, tier, seen_hashes)
            all_articles.extend(batch)
            if batch:
                logger.info("RSS {}: {} articles", source, len(batch))
        except Exception as e:
            logger.warning("RSS {} parse error: {}", source, e)

    logger.success("RSS total: {} new articles", len(all_articles))
    return all_articles


# ── Save ──────────────────────────────────────────────────────────────────── #

def save_articles(articles: list[dict], path: Path, append: bool = True) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        for art in articles:
            f.write(json.dumps(art, ensure_ascii=False) + "\n")
    return len(articles)


# ── Rebuild index ─────────────────────────────────────────────────────────── #

def rebuild_index():
    """Run build_index.py as a subprocess so it gets its own clean memory."""
    import subprocess
    logger.info("Rebuilding FAISS index…")
    result = subprocess.run(
        [sys.executable, "scripts/build_index.py"],
        capture_output=False,
    )
    if result.returncode != 0:
        logger.error("Index build failed (exit {})", result.returncode)
    else:
        logger.success("Index rebuilt successfully")


# ── Main ──────────────────────────────────────────────────────────────────── #

async def main(args):
    t0 = time.time()

    # Load existing hashes for dedup
    seen_hashes = _load_existing_hashes(OUTPUT_PATH) if args.resume else set()
    all_new: list[dict] = []

    # Progress bar (tracks claim count, not requests)
    progress = tqdm(desc="Claims scraped", unit="claims", dynamic_ncols=True)

    # Google Fact Check API
    if not args.rss_only:
        logger.info(
            "Starting Google Fact Check API — {} queries × up to {} results each",
            len(QUERIES), MAX_PER_QUERY,
        )
        google_articles = await scrape_google(seen_hashes, progress)
        all_new.extend(google_articles)

    # RSS feeds
    if not args.google_only:
        logger.info("Scraping {} RSS feeds in parallel…", len(RSS_SOURCES))
        rss_articles = await scrape_rss(seen_hashes)
        all_new.extend(rss_articles)

    progress.close()

    if not all_new:
        logger.warning("No new articles scraped — corpus unchanged")
        return

    # Save
    saved = save_articles(all_new, OUTPUT_PATH, append=args.resume)
    elapsed = time.time() - t0
    logger.success(
        "Scraped {} new articles in {:.1f}s → {}",
        saved, elapsed, OUTPUT_PATH,
    )

    # Corpus total
    total_lines = sum(1 for _ in open(OUTPUT_PATH, encoding="utf-8"))
    logger.success("Corpus total: {} articles", total_lines)

    # Rebuild FAISS index
    if not args.no_index:
        rebuild_index()
    else:
        logger.info("Skipping index rebuild (--no-index). Run: python scripts/build_index.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk corpus scraper — exhausts daily quota")
    parser.add_argument("--resume",      action="store_true", help="Append to existing corpus (skip known URLs)")
    parser.add_argument("--no-index",    action="store_true", help="Skip FAISS index rebuild after scraping")
    parser.add_argument("--google-only", action="store_true", help="Only Google Fact Check API")
    parser.add_argument("--rss-only",    action="store_true", help="Only RSS feeds")
    args = parser.parse_args()

    asyncio.run(main(args))
