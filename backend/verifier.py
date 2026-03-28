"""
backend/verifier.py — RAG + stance classification pipeline.

For each claim:
1. Retrieve top-K evidence chunks from FAISS (with trust-tier boosting)
2. If corpus miss → live Google Fact Check API lookup as fallback
3. Send claim + evidence to Groq LLM → JSON stance
4. Calibrate confidence, force Uncertain on corpus miss

Supports async parallel verification of multiple claims.
"""

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlencode

import httpx
from groq import AsyncGroq
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg
from backend.retriever import Retriever, RetrievedChunk
from backend.gdelt_search import gdelt_search
from backend.ddg_search import ddg_search


# ── Models ────────────────────────────────────────────────────────────────── #

class Stance(str, Enum):
    SUPPORTED = "Supported"
    REFUTED = "Refuted"
    UNCERTAIN = "Uncertain"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class SourceChip:
    title: str
    url: str
    source: str
    source_tier: str
    score: float


@dataclass
class VerificationResult:
    claim: str
    stance: Stance
    confidence: Confidence
    reasoning: str
    structured_query: dict = field(default_factory=dict)
    pipeline_trace: list[dict] = field(default_factory=list)
    sources: list[SourceChip] = field(default_factory=list)
    corpus_miss: bool = False


# ── Prompts ───────────────────────────────────────────────────────────────── #

STANCE_SYSTEM = """You are an expert fact-checker. Given a claim and evidence passages,
determine whether the evidence supports, refutes, or is uncertain about the claim.

CRITICAL RULES FOR FACT-CHECK EVIDENCE:
- Many evidence passages are FACT-CHECK ARTICLES that debunk specific viral posts
  (fake videos, AI-generated images, manipulated photos). A fact-check that says
  "This VIDEO of X is fake" does NOT mean the underlying event X did not happen.
- Carefully distinguish between: (a) the underlying factual event, and (b) a specific
  viral media post about that event. Only judge the CLAIM, not the media.
- If evidence only debunks specific media (videos/images) but doesn't deny the
  underlying event occurred, output Uncertain — not Refuted.
- If textualRating says "False" but it's clearly about a fake video/image, treat
  that as Uncertain for the underlying event unless the text explicitly says the
  event itself did not occur.

Respond ONLY with valid JSON in this exact format:
{
  "stance": "Supported" | "Refuted" | "Uncertain",
  "confidence": "High" | "Medium" | "Low",
  "reasoning": "2-3 sentence explanation citing specific evidence"
}

Guidelines:
- Supported: evidence strongly corroborates that the core event/claim occurred
- Refuted: evidence explicitly states the core event/claim did NOT occur
- Uncertain: evidence is tangential, only about media authenticity, or insufficient
- High confidence: multiple strong sources explicitly address the core claim
- Medium confidence: some direct evidence but incomplete
- Low confidence: indirect evidence or only debunks related media"""

STANCE_USER = """Claim: {claim}

Evidence:
{evidence}

Determine the stance of the evidence toward the claim."""


# ── LLM call ──────────────────────────────────────────────────────────────── #

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def _call_stance_llm(claim: str, evidence_text: str) -> dict:
    client = AsyncGroq(api_key=cfg.GROQ_API_KEY)
    response = await client.chat.completions.create(
        model=cfg.GROQ_MODEL,
        messages=[
            {"role": "system", "content": STANCE_SYSTEM},
            {"role": "user", "content": STANCE_USER.format(
                claim=claim, evidence=evidence_text[:6000]
            )},
        ],
        temperature=0.0,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


def _build_evidence_text(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, rc in enumerate(chunks, 1):
        parts.append(
            f"[{i}] Source: {rc.chunk.source} ({rc.chunk.source_tier})\n"
            f"Title: {rc.chunk.title}\n"
            f"URL: {rc.chunk.url}\n"
            f"Text: {rc.chunk.text[:800]}\n"  # Increased from 500 → 800 for richer context
        )
    return "\n---\n".join(parts)[:6000]  # Increased total cap from 5000 → 6000


def _calibrate_confidence(raw_confidence: str, chunks: list[RetrievedChunk]) -> Confidence:
    """
    Downgrade confidence if top evidence scores are mediocre.
    """
    top_score = chunks[0].raw_score if chunks else 0.0
    try:
        conf = Confidence(raw_confidence)
    except ValueError:
        conf = Confidence.LOW

    if top_score < 0.45 and conf == Confidence.HIGH:
        conf = Confidence.MEDIUM
    if top_score < 0.35 and conf in (Confidence.HIGH, Confidence.MEDIUM):
        conf = Confidence.LOW
    return conf


# ── Live Google Fact Check fallback ──────────────────────────────────────── #

async def _live_google_factcheck(claim: str) -> list[dict]:
    """Hit Google Fact Check API in real-time for claims not in local FAISS index."""
    if not cfg.GOOGLE_FACT_CHECK_API_KEY:
        return []
    params = urlencode({
        "key": cfg.GOOGLE_FACT_CHECK_API_KEY,
        "query": claim[:200],
        "pageSize": 10,
        "languageCode": "en",
    })
    url = f"https://factchecktools.googleapis.com/v1alpha1/claims:search?{params}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("claims", [])
    except Exception as e:
        logger.warning(f"Live Google API lookup failed: {e}")
        return []


def _live_claims_to_chunks(live_claims: list[dict]) -> list[RetrievedChunk]:
    """Convert live Google Fact Check API results into RetrievedChunk format."""
    from backend.retriever import Chunk
    chunks = []
    for item in live_claims:
        reviews = item.get("claimReview", [])
        if not reviews:
            continue
        review = reviews[0]
        text = (
            f"Claim: {item.get('text', '')}. "
            f"Rating: {review.get('textualRating', 'Unknown')}. "
            f"Reviewed by: {review.get('publisher', {}).get('name', 'Unknown')}."
        )
        url = review.get("url", "")
        chunk = Chunk(
            chunk_id=hash(url) & 0xFFFFFFFF,
            text=text,
            title=review.get("title", item.get("text", ""))[:200],
            url=url,
            source="google_live",
            source_tier="verified",
        )
        chunks.append(RetrievedChunk(chunk=chunk, raw_score=0.72, boosted_score=0.72 * 1.2))
    return chunks


def _merge_chunks(bing: list[RetrievedChunk], google: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Merge Bing + Google chunks, deduplicate by URL, sort by boosted_score desc."""
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for rc in google + bing:          # Google first — higher trust tier
        url = rc.chunk.url
        if url and url not in seen:
            seen.add(url)
            merged.append(rc)
    merged.sort(key=lambda r: r.boosted_score, reverse=True)
    return merged


# ── Core verification ─────────────────────────────────────────────────────── #

async def verify_claim(claim_data: dict) -> VerificationResult:
    """Verify a single claim end-to-end and build pipeline trace.
    
    ALWAYS queries all four sources in parallel:
      1. FAISS local corpus (static, may be stale)
      2. GDELT DOC 2.0 (live global news, free)
      3. Google Fact Check API (live fact-checks)
      4. DuckDuckGo HTML (live web search, no API key)
    Then merges + deduplicates, preferring fresh authoritative results.
    """
    import time
    claim = claim_data.get("claim", "")
    trace = []

    # ── Stage 1: FAISS local corpus (fast) ──────────────────────────────── #
    faiss_start = time.time()
    retriever = Retriever.get()
    faiss_chunks = retriever.retrieve(claim)
    faiss_elapsed = int((time.time() - faiss_start) * 1000)

    top_faiss_score = faiss_chunks[0].raw_score if faiss_chunks else 0.0
    corpus_hit = top_faiss_score >= 0.6  # strong local match → skip live searches

    trace.append({
        "step": "Database Search",
        "status": f"Found {len(faiss_chunks)} articles in {faiss_elapsed}ms (top score: {top_faiss_score:.2f})",
        "state": "success" if corpus_hit else "pending"
    })

    # ── Stage 2: DDG always runs; GDELT + Google only on corpus miss ──── #
    gdelt_chunks: list[RetrievedChunk] = []
    google_chunks: list[RetrievedChunk] = []

    # DDG always fires — fastest and best live results
    ddg_task = ddg_search(claim)

    if not corpus_hit:
        logger.info("Corpus miss (top={:.2f}) — searching GDELT + Google + DDG for '{:.60s}…'", top_faiss_score, claim)
        live_start = time.time()
        raw_gdelt, live_claims, ddg_chunks = await asyncio.gather(
            gdelt_search(claim),
            _live_google_factcheck(claim),
            ddg_task,
        )
        gdelt_chunks = raw_gdelt
        google_chunks = _live_claims_to_chunks(live_claims)
        live_elapsed = int((time.time() - live_start) * 1000)

        logger.info(
            "Live results — GDELT: {}, Google: {}, DDG: {} ({}ms)",
            len(gdelt_chunks), len(google_chunks), len(ddg_chunks), live_elapsed,
        )

        trace.append({
            "step": "Live Search",
            "status": f"{len(gdelt_chunks)} GDELT + {len(google_chunks)} Google + {len(ddg_chunks)} DDG in {live_elapsed}ms",
            "state": "success" if (gdelt_chunks or google_chunks or ddg_chunks) else "warning"
        })
    else:
        logger.info("Corpus hit (top={:.2f}) — running DDG only for '{:.60s}…'", top_faiss_score, claim)
        live_start = time.time()
        ddg_chunks = await ddg_task
        live_elapsed = int((time.time() - live_start) * 1000)
        trace.append({
            "step": "Live Search",
            "status": f"{len(ddg_chunks)} DDG results in {live_elapsed}ms (GDELT/Google skipped)",
            "state": "success" if ddg_chunks else "warning"
        })

    # ── Stage 3: Merge all sources, dedup by URL, sort by score ──────── #
    live_merged = _merge_chunks(gdelt_chunks + ddg_chunks, google_chunks)

    # Combine: live results first (fresher), then FAISS
    seen_urls: set[str] = set()
    all_chunks: list[RetrievedChunk] = []
    for rc in live_merged + faiss_chunks:
        url = rc.chunk.url
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_chunks.append(rc)

    all_chunks.sort(key=lambda r: r.boosted_score, reverse=True)

    # If we have nothing at all, bail
    if not all_chunks:
        logger.warning("No results from any source for: '{:.60s}…'", claim)
        return VerificationResult(
            claim=claim,
            stance=Stance.UNCERTAIN,
            confidence=Confidence.LOW,
            reasoning="No relevant evidence found in the verified corpus or live web sources. Cannot assess this claim.",
            sources=[],
            corpus_miss=True,
            structured_query=claim_data,
            pipeline_trace=trace,
        )

    # Use the merged set for evidence
    chunks = all_chunks[:12]  # top 12 for LLM context

    evidence_text = _build_evidence_text(chunks)

    try:
        llm_result = await _call_stance_llm(claim, evidence_text)
        
        # Robust parsing for Enum
        raw_stance = str(llm_result.get("stance", "Uncertain")).strip().capitalize()
        try:
            stance = Stance(raw_stance)
        except ValueError:
            stance = Stance.UNCERTAIN
            
        raw_conf = llm_result.get("confidence", "Low")
        reasoning = llm_result.get("reasoning", "No reasoning provided.")
    except Exception as e:
        logger.error(f"Stance LLM failed: {e}")
        stance = Stance.UNCERTAIN
        raw_conf = "Low"
        reasoning = "Verification failed due to a processing error."

    confidence = _calibrate_confidence(raw_conf, chunks)

    # Build source chips (top 8 unique URLs — show more evidence)
    source_urls: set[str] = set()
    sources: list[SourceChip] = []
    for rc in chunks:
        if rc.chunk.url not in source_urls:
            source_urls.add(rc.chunk.url)
            sources.append(SourceChip(
                title=rc.chunk.title,
                url=rc.chunk.url,
                source=rc.chunk.source,
                source_tier=rc.chunk.source_tier,
                score=rc.raw_score,
            ))
        if len(sources) >= 8:
            break

    return VerificationResult(
        claim=claim,
        stance=stance,
        confidence=confidence,
        reasoning=reasoning,
        structured_query=claim_data,
        pipeline_trace=trace,
        sources=sources,
        corpus_miss=False,
    )


async def verify_claims(claims: list[dict]) -> list[VerificationResult]:
    """Verify multiple claims in parallel. Never drops claims — errors become Uncertain."""
    tasks = [verify_claim(c) for c in claims]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    verified: list[VerificationResult] = []
    for claim_data, r in zip(claims, results):
        claim_str = claim_data.get("claim", "")
        if isinstance(r, Exception):
            logger.error(f"Verification error for '{claim_str[:60]}': {r}")
            # Return Uncertain instead of silently dropping the claim
            verified.append(VerificationResult(
                claim=claim_str,
                stance=Stance.UNCERTAIN,
                confidence=Confidence.LOW,
                reasoning="Verification could not be completed due to an internal error.",
                sources=[],
                corpus_miss=True,
                structured_query=claim_data,
                pipeline_trace=[{"step": "Verification", "status": "Internal Error", "state": "error"}]
            ))
        else:
            verified.append(r)
    return verified
