"""
Debug DDG - find snippet container
"""
from html.parser import HTMLParser
import asyncio, httpx, re

_DDG_URL = "https://html.duckduckgo.com/html/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

class _DDGResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._in_result_a = False
        self._in_snippet = False
        self._current = {}
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        cls = attr_dict.get("class") or ""

        if tag == "a" and "result__a" in cls:
            self._in_result_a = True
            self._current_text = []
            href = attr_dict.get("href") or ""
            self._current["url"] = self._extract_url(href)

        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True
            self._current_text = []
            href = attr_dict.get("href") or ""
            if not self._current.get("url"):
                self._current["url"] = self._extract_url(href)

    def handle_endtag(self, tag):
        if tag == "a" and self._in_result_a:
            self._in_result_a = False
            title = " ".join(t for t in self._current_text if t).strip()
            if title:
                self._current["title"] = title

        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            snippet = " ".join(t for t in self._current_text if t).strip()
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
        from urllib.parse import unquote
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
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _DDG_URL,
            data={"q": "Iran Parliament Speaker says U.S. plots ground attack despit", "b": "", "kl": ""},
            headers={"User-Agent": _UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"},
        )
        html = resp.text
        
        parser = _DDGResultParser()
        parser.feed(html)
        print(f"Parser found {len(parser.results)} results:")
        for r in parser.results:
            print(r)

if __name__ == "__main__":
    asyncio.run(main())
