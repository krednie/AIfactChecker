"""
Diagnose DDG — dumps raw HTML + parser attempt
"""
import asyncio, httpx, re, sys
from html.parser import HTMLParser
from urllib.parse import unquote

_DDG_URL = "https://html.duckduckgo.com/html/"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

class _DDGResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.all_classes = []
        self._in_result_a = False
        self._in_snippet = False
        self._current = {}
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        cls = attr_dict.get("class") or ""
        if cls:
            self.all_classes.append((tag, cls))

        if tag == "a" and "result__a" in cls:
            self._in_result_a = True
            self._current_text = []
            href = attr_dict.get("href") or ""
            self._current["url"] = self._extract_url(href)

        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True
            self._current_text = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_result_a:
            self._in_result_a = False
            title = " ".join(self._current_text).strip()
            if title:
                self._current["title"] = title

        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            snippet = " ".join(self._current_text).strip()
            self._current["snippet"] = snippet
            if self._current.get("url") and self._current.get("title"):
                self.results.append(self._current)
            self._current = {}

    def handle_data(self, data):
        if self._in_result_a or self._in_snippet:
            stripped = data.strip()
            if stripped:
                self._current_text.append(stripped)

    @staticmethod
    def _extract_url(href):
        if not href:
            return ""
        if "uddg=" in href:
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                return unquote(match.group(1))
        if href.startswith("http"):
            return href
        return ""


async def main():
    query = "Iran Parliament Speaker says U.S. plots ground attack"
    print(f"Query: {query}")
    print("=" * 60)

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.post(
                _DDG_URL,
                data={"q": query, "b": "", "kl": ""},
                headers={
                    "User-Agent": _UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://duckduckgo.com/",
                    "Origin": "https://duckduckgo.com",
                },
            )
            print(f"Status: {resp.status_code}")
            print(f"URL after redirects: {resp.url}")
            print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
            html = resp.text
    except Exception as e:
        print(f"ERROR fetching: {e}")
        sys.exit(1)

    print(f"HTML length: {len(html)} chars")

    # Check for CAPTCHA / block signals
    if "captcha" in html.lower():
        print("\n!! CAPTCHA DETECTED — DDG is blocking the request")
    if "Pardon Our Interruption" in html or "blocked" in html.lower()[:500]:
        print("\n!! BLOCK PAGE DETECTED")
    if "result__a" in html:
        print("\n[OK] 'result__a' class found in HTML")
    else:
        print("\n!! 'result__a' NOT found — DDG changed their HTML structure or returned a block page")

    # Check what CSS classes are actually present
    print("\n--- Checking for known DDG result classes ---")
    for marker in ["result__a", "result__snippet", "result__body", "results_links", "web-result", "result__title", "__url"]:
        count = html.count(marker)
        print(f"  '{marker}': {count} occurrences")

    # Dump first 3000 chars of HTML to understand structure
    print("\n--- First 3000 chars of HTML ---")
    print(html[:3000])
    print("\n--- Last 1000 chars of HTML ---")
    print(html[-1000:])

    # Try parsing
    parser = _DDGResultParser()
    parser.feed(html)
    print(f"\n--- Parser found {len(parser.results)} results ---")
    for r in parser.results[:5]:
        print(r)

    # Show unique (tag, class) pairs found
    print(f"\n--- Unique tag+class combos (top 30) ---")
    seen = set()
    for tag, cls in parser.all_classes:
        key = f"{tag}.{cls[:60]}"
        if key not in seen:
            seen.add(key)
            print(f"  {key}")
        if len(seen) >= 30:
            break

asyncio.run(main())
