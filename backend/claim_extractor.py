"""
backend/claim_extractor.py — Extract structured claims from text using Groq LLM.

Returns a list of atomic, verifiable claims as JSON.
Handles JSON parse failures with retry + fallback.
Deduplicates near-identical claims via cosine similarity.
"""

import asyncio
import json
import re
from dataclasses import dataclass

from groq import AsyncGroq
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg


# ── Prompts ───────────────────────────────────────────────────────────────── #

SYSTEM_PROMPT = """You are a precise claim extraction engine for a fact-checking system.

Your task: Extract every distinct, verifiable factual statement from the provided text, and break it down into a structured query.

Rules:
1. Extract ALL factual statements, including breaking news, historical events, and commonly accepted truths.
2. Treat factual search queries, topics, or headlines (e.g. "apple stock today", "iran bombed israel") as implicit claims to be verified. Even short phrases count.
3. Only skip pure opinions, questions, commands, and obvious satire.
4. IMPORTANT: If the text reads like a search query or news headline, convert it into a full claim statement and include it.
5. For each claim, generate:
   - "claim": The full, self-contained statement.
   - "intent": What the user is trying to verify.
   - "keywords": 3-5 precise search keywords.
   - "ambiguity_removed": Any context added to make it clear.
   - "structure": An object with: "subject", "predicate", "object", "time", "location". (Use null if not applicable).

Output ONLY a JSON array of objects in this EXACT format:
[
  {
    "claim": "Apple stock price dropped today",
    "intent": "verify historical stock market data",
    "keywords": ["Apple Inc", "AAPL", "stock price", "latest"],
    "ambiguity_removed": "Clarified 'today' to mean the current trading day",
    "structure": {
      "subject": "Apple Inc",
      "predicate": "stock price drop",
      "object": null,
      "time": "today",
      "location": "global market"
    }
  }
]
If there are absolutely no factual statements, output: []"""

USER_TEMPLATE = """Extract all verifiable factual claims and their structured queries from this text:

---
{text}
---

Remember: output ONLY the JSON array, no explanation."""


# ── Data model ────────────────────────────────────────────────────────────── #

@dataclass
class ExtractedClaims:
    claims: list[dict]
    raw_text: str
    language_detected: str  # "en" or detected language code


# ── LLM call with retry ───────────────────────────────────────────────────── #

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def _call_groq(text: str) -> str:
    client = AsyncGroq(api_key=cfg.GROQ_API_KEY)
    response = await client.chat.completions.create(
        model=cfg.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(text=text[:4000])},
        ],
        temperature=0.0,
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _parse_claims(raw: str) -> list[dict]:
    """Parse LLM output → list of dicts. Multiple fallback strategies."""
    raw = raw.strip()

    def _validate_claim(c: dict) -> dict | None:
        if not isinstance(c, dict) or "claim" not in c:
            return None
        # Ensure schema
        return {
            "claim": str(c.get("claim", "")).strip(),
            "intent": str(c.get("intent", "")),
            "keywords": [str(k) for k in c.get("keywords", [])],
            "ambiguity_removed": str(c.get("ambiguity_removed", "")),
            "structure": {
                "subject": c.get("structure", {}).get("subject"),
                "predicate": c.get("structure", {}).get("predicate"),
                "object": c.get("structure", {}).get("object"),
                "time": c.get("structure", {}).get("time"),
                "location": c.get("structure", {}).get("location"),
            }
        }

    # Strategy 1: direct JSON parse
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [v for c in data if (v := _validate_claim(c))]
        for key in ("claims", "results", "extracted"):
            if key in data and isinstance(data[key], list):
                return [v for c in data[key] if (v := _validate_claim(c))]
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract JSON array with regex
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if match:
        try:
            arr = json.loads(match.group())
            return [v for c in arr if (v := _validate_claim(c))]
        except json.JSONDecodeError:
            pass

    return []


def _dedup_claims(claims: list[dict], threshold: float = 0.85) -> list[dict]:
    """Remove near-duplicate claims using simple character n-gram overlap."""
    if len(claims) <= 1:
        return claims

    def _ngrams(text: str, n: int = 4) -> set[str]:
        text = text.lower()
        return {text[i:i+n] for i in range(len(text) - n + 1)}

    def _similarity(a: str, b: str) -> float:
        na, nb = _ngrams(a), _ngrams(b)
        if not na or not nb:
            return 0.0
        return len(na & nb) / len(na | nb)

    unique: list[dict] = []
    for claim_obj in claims:
        claim_text = claim_obj["claim"]
        if all(_similarity(claim_text, u["claim"]) < threshold for u in unique):
            unique.append(claim_obj)

    removed = len(claims) - len(unique)
    if removed:
        logger.debug(f"Dedup removed {removed} near-duplicate claims")
    return unique


# ── Public API ────────────────────────────────────────────────────────────── #

async def extract_claims(text: str) -> ExtractedClaims:
    """
    Extract and deduplicate verifiable claims from arbitrary text.
    Handles Hindi/multilingual text — translation happens upstream.

    Returns ExtractedClaims with claims list (may be empty if none found).
    """
    if not text or len(text.strip()) < 3:
        return ExtractedClaims(claims=[], raw_text=text, language_detected="en")

    try:
        raw = await _call_groq(text)
        claims = _parse_claims(raw)
    except Exception as e:
        logger.error(f"Claim extraction failed after retries: {e}")
        claims = []

    # Fallback: if the LLM returned nothing but the text looks like a factual query,
    # wrap it as a direct claim so the pipeline can still process it.
    if not claims and len(text.strip().split()) >= 2:
        fallback_text = text.strip()
        words = fallback_text.split()
        claims = [{
            "claim": fallback_text,
            "intent": "verify factual claim",
            "keywords": words[:5],
            "ambiguity_removed": "",
            "structure": {
                "subject": words[0] if words else None,
                "predicate": " ".join(words[1:]) if len(words) > 1 else None,
                "object": None,
                "time": None,
                "location": None,
            }
        }]
        logger.info(f"LLM returned no claims — using fallback for: '{fallback_text[:60]}'")

    claims = _dedup_claims(claims)
    logger.info(f"Extracted {len(claims)} unique claims")

    return ExtractedClaims(
        claims=claims,
        raw_text=text,
        language_detected="en",
    )


# ── CLI smoke test ────────────────────────────────────────────────────────── #

if __name__ == "__main__":
    TEST_INPUTS = [
        "COVID-19 vaccines contain microchips. Bill Gates funded the pandemic to sell vaccines.",
        "apple stock today"
    ]

    async def run():
        for i, text in enumerate(TEST_INPUTS, 1):
            result = await extract_claims(text)
            print(f"\n--- Input {i} ---")
            print(f"Text: {text[:80]}...")
            print(f"Claims ({len(result.claims)}):")
            for c in result.claims:
                print(f"  • {c['claim']}")
                print(f"    Intent: {c['intent']}")
                print(f"    Keywords: {c['keywords']}")
                print(f"    Structure: {c['structure']}")

    asyncio.run(run())
