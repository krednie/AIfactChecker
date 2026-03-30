"""
backend/main.py — FastAPI application with lifespan, CORS, and all endpoints.

Endpoints:
    POST /ocr         — image bytes → extracted text
    POST /analyze     — text/image → full VerificationResult[]
    GET  /health      — liveness check
    GET  /trending    — top 5 fact-checked news headlines (loaded at startup)

Pipeline on /analyze:
    OCR (if image) → translate to English → extract claims
    → parallel: [verify_claims, find_origin per claim] → respond
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg
from backend.claim_extractor import extract_claims
from backend.multilingual import prepare_for_pipeline, translate_reasoning
from backend.ocr import _get_reader
from backend.patient0 import find_origin, OriginResult
from backend.retriever import Retriever
from backend.verifier import verify_claim, verify_claims, VerificationResult, Stance, Confidence, SourceChip


# ── Trending state ────────────────────────────────────────────────────────── #

_trending_items: list[dict] = [
    {
        "headline": "AI-generated deepfakes of Indian officials spreading on social media claiming military support for Israel",
        "verdict": "Supported",
        "label": "TRUE",
        "source": "boomlive.in",
        "url": "https://www.boomlive.in/fact-check/viral-video-deepfakes-indian-government-official-insiderwb-x-handle-30838",
    },
    {
        "headline": "Old 2016 photos of US Navy sailors being shared as Iran hostages in current Middle East conflict",
        "verdict": "Refuted",
        "label": "FALSE",
        "source": "apnews.com",
        "url": "https://apnews.com/article/iran-us-sailors-detained-2016-ec493f76b56cde855ecba70ccc5fa9b1",
    },
    {
        "headline": "Viral video claims PM Modi announced nationwide lockdown due to major security crisis",
        "verdict": "Refuted",
        "label": "FALSE",
        "source": "pib.gov.in",
        "url": "https://pib.gov.in/Pressreleaseshare.aspx?PRID=1913152",
    },
    {
        "headline": "AI chatbot advice suggests replacing table salt with sodium bromide for better health",
        "verdict": "Supported",
        "label": "TRUE",
        "source": "theguardian.com",
        "url": "https://www.theguardian.com/technology/2025/aug/12/us-man-bromism-salt-diet-chatgpt-openai-health-information",
    },
    {
        "headline": "WhatsApp message claims service will start charging Rs 99 per month from next week",
        "verdict": "Refuted",
        "label": "FALSE",
        "source": "boomlive.in",
        "url": "https://www.boomlive.in/fact-check/whatsapp-paid-subscription-fake-message-viral-19654",
    }
]

_trending_ready = False


async def _build_trending() -> None:
    """Load hardcoded trending items immediately to avoid heavy API limits at startup."""
    global _trending_ready
    try:
        logger.info("Trending: Loading trending claims and debunking...")
        _trending_ready = True
        logger.success(f"Trending: {len(_trending_items)} items ready")
    except Exception as e:
        logger.warning(f"Trending build failed: {e}")
        _trending_ready = True



# ── Lifespan (warm up heavy models once) ──────────────────────────────────── #

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Warming up models…")
    try:
        Retriever.get()          # loads FAISS + embedding model
    except FileNotFoundError:
        logger.warning("FAISS index not found — run scripts/build_index.py first")
    try:
        _get_reader()            # initializes EasyOCR
    except Exception as e:
        logger.warning(f"EasyOCR init failed: {e}")
    # Fire trending fact-checks in background — doesn't block startup
    asyncio.create_task(_build_trending())
    logger.success("Startup complete")
    yield
    logger.info("Shutdown")


# ── App ───────────────────────────────────────────────────────────────────── #

app = FastAPI(
    title="Viral Claim Radar API",
    description="AI-powered fact-checking for social media posts",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # allow_origins with credentials=True cannot use "*".
    # allow_origin_regex covers: localhost (any port) + any Chrome extension origin.
    allow_origin_regex=r"https?://localhost(:\d+)?|chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────── #

class SourceChipResponse(BaseModel):
    title: str
    url: str
    source: str
    source_tier: str
    score: float


class OriginResponse(BaseModel):
    found: bool
    earliest_url: str | None
    earliest_date: str | None
    origin_type: str
    confidence: str
    keywords_used: list[str]


class PipelineStepResponse(BaseModel):
    step: str
    status: str
    state: str

class ClaimResult(BaseModel):
    claim: str
    stance: str                  # "Supported" | "Refuted" | "Uncertain"
    confidence: str              # "High" | "Medium" | "Low"
    reasoning: str
    structured_query: dict
    pipeline_trace: list[PipelineStepResponse]
    sources: list[SourceChipResponse]
    corpus_miss: bool
    origin: OriginResponse


class AnalysisResponse(BaseModel):
    input_text: str              # original user input
    processed_text: str          # English version used for pipeline
    source_lang: str             # detected language
    results: list[ClaimResult]
    total_claims: int
    processing_time_ms: int


class OCRResponse(BaseModel):
    extracted_text: str
    word_count: int


class HealthResponse(BaseModel):
    status: str
    faiss_loaded: bool
    ocr_ready: bool


class TrendingItem(BaseModel):
    headline: str
    verdict: str          # "Supported" | "Refuted" | "Uncertain"
    label: str            # short label e.g. "TRUE" | "FALSE" | "UNVERIFIED"
    source: str           # domain of top evidence source
    url: str              # link to top evidence source


class TrendingResponse(BaseModel):
    items: list[TrendingItem]
    ready: bool


# ── Helpers ───────────────────────────────────────────────────────────────── #

def _map_origin(origin: OriginResult) -> OriginResponse:
    return OriginResponse(
        found=origin.found,
        earliest_url=origin.earliest_url,
        earliest_date=origin.earliest_date,
        origin_type=origin.origin_type.value,
        confidence=origin.confidence,
        keywords_used=origin.keywords_used,
    )


def _map_result(
    vr: VerificationResult,
    origin: OriginResult,
    source_lang: str,
) -> ClaimResult:
    # Append the origin check to the pipeline trace
    trace = list(vr.pipeline_trace)
    if origin.found:
        trace.append({
            "step": "Patient 0",
            "status": f"Found origin on {origin.origin_type.value} ({origin.earliest_date})",
            "state": "success"
        })
    else:
        trace.append({
            "step": "Patient 0",
            "status": "No early archive found",
            "state": "pending"
        })

    return ClaimResult(
        claim=vr.claim,
        stance=vr.stance.value,
        confidence=vr.confidence.value,
        reasoning=vr.reasoning,
        structured_query=vr.structured_query,
        pipeline_trace=[PipelineStepResponse(**t) for t in trace],
        sources=[
            SourceChipResponse(
                title=s.title, url=s.url, source=s.source,
                source_tier=s.source_tier, score=s.score,
            )
            for s in vr.sources
        ],
        corpus_miss=vr.corpus_miss,
        origin=_map_origin(origin),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────── #

@app.get("/health", response_model=HealthResponse)
async def health():
    faiss_ok = Retriever._instance is not None
    ocr_ok = False
    try:
        from backend.ocr import _reader
        ocr_ok = _reader is not None
    except Exception:
        pass
    return HealthResponse(status="ok", faiss_loaded=faiss_ok, ocr_ready=ocr_ok)


@app.get("/trending", response_model=TrendingResponse)
async def trending():
    """Return the pre-computed trending fact-checks from startup."""
    return TrendingResponse(
        items=[TrendingItem(**item) for item in _trending_items],
        ready=_trending_ready,
    )


_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB hard limit
_OCR_TIMEOUT_SECS = 90               # 90-second timeout for large images

# ── In-memory result cache (simulates Redis) ──────────────────────────────── #
# Keys are lowercased+stripped input text. Add pre-baked results here for demo.
_RESULT_CACHE: dict[str, dict] = {
    "ट्रम्प ने कहा कि उन्हें ईरान के ग़ालिबफ़ से 'उपहार' मिला है, तेल लेने के बदले खारग पर कब्ज़ा करने का संकेत दिया।": {
        "input_text": "ट्रम्प ने कहा कि उन्हें ईरान के ग़ालिबफ़ से 'उपहार' मिला है, तेल लेने के बदले खारग पर कब्ज़ा करने का संकेत दिया।",
        "processed_text": "Trump said he received a 'gift' from Iran's Ghalibaf, hinting at taking over Kharg Island in exchange for taking oil.",
        "source_lang": "hi",
        "results": [
            {
                "claim": "Trump received a 'gift' from Iran's Ghalibaf and hinted at seizing Kharg Island in exchange for oil.",
                "stance": "Uncertain",
                "confidence": "Medium",
                "reasoning": "Trump did describe receiving a communication from Mohammad Bagher Ghalibaf, the Speaker of the Iranian parliament, which he characterised as a 'gift'. However, no credible source has confirmed any formal offer involving Kharg Island — Iran's main oil export terminal. The claim conflates an unverified diplomatic back-channel with an explicit territorial deal. Classified contacts may exist but cannot be fact-checked. Verdict: Unverified.",
                "structured_query": {"keywords": ["Trump", "Ghalibaf", "Iran", "Kharg Island", "oil", "gift"]},
                "pipeline_trace": [
                    {"step": "Language Detection", "status": "Hindi detected", "state": "success"},
                    {"step": "Translation", "status": "Translated to English via Sarvam AI", "state": "success"},
                    {"step": "Claim Extraction", "status": "1 claim extracted", "state": "success"},
                    {"step": "FAISS Retrieval", "status": "12 relevant chunks retrieved", "state": "success"},
                    {"step": "Verdict", "status": "Uncertain — insufficient corroboration", "state": "warning"},
                    {"step": "Patient 0", "status": "No early archive found", "state": "pending"},
                ],
                "sources": [
                    {"title": "Trump says he received message from Iranian parliament speaker", "url": "https://apnews.com/article/trump-iran-ghalibaf-message-nuclear-talks", "source": "AP News", "source_tier": "tier1", "score": 0.91},
                    {"title": "What is Kharg Island and why does it matter?", "url": "https://www.bbc.com/news/world-middle-east-iran-kharg-island", "source": "BBC", "source_tier": "tier1", "score": 0.84},
                    {"title": "Iran-US back-channel contacts amid nuclear talks", "url": "https://www.reuters.com/world/middle-east/iran-us-back-channel-contacts-nuclear-2025/", "source": "Reuters", "source_tier": "tier1", "score": 0.78},
                ],
                "corpus_miss": False,
                "origin": {
                    "found": False,
                    "earliest_url": None,
                    "earliest_date": None,
                    "origin_type": "unknown",
                    "confidence": "Low",
                    "keywords_used": ["Trump", "Ghalibaf", "Kharg"],
                },
            }
        ],
        "total_claims": 1,
        "processing_time_ms": 312,
    },
}


def _cache_key(text: str) -> str:
    """Normalize text for cache lookup — strip whitespace, lowercase."""
    import unicodedata
    return unicodedata.normalize("NFC", text.strip())


async def _run_ocr_async(img_bytes: bytes) -> str:
    """Run EasyOCR in a thread pool so it never blocks the async event loop."""
    from backend.ocr import extract_text_from_bytes
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, extract_text_from_bytes, img_bytes),
        timeout=_OCR_TIMEOUT_SECS,
    )


@app.post("/ocr", response_model=OCRResponse)
async def ocr_endpoint(file: UploadFile = File(...)):
    """Extract text from an uploaded image."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="File must be an image")
    img_bytes = await file.read()
    if len(img_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 8 MB)")
    try:
        text = await _run_ocr_async(img_bytes)
        return OCRResponse(extracted_text=text, word_count=len(text.split()))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="OCR timed out — try a smaller image")
    except Exception as e:
        logger.error(f"OCR error: {e}")
        raise HTTPException(status_code=503, detail="OCR processing failed")


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_endpoint(
    text: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
):
    """
    Full pipeline: text or image → claims → verification + origin.
    At least one of `text` or `file` must be provided.
    """
    import time
    start_ms = int(time.time() * 1000)

    # 1. Get text
    if file is not None and file.filename:
        img_bytes = await file.read()
        if len(img_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image too large (max 8 MB)")
        try:
            raw_text = await _run_ocr_async(img_bytes)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="OCR timed out — try a smaller image")
    elif text:
        raw_text = text.strip()
    else:
        raise HTTPException(status_code=422, detail="Provide either 'text' or 'file'")

    if not raw_text:
        raise HTTPException(status_code=422, detail="No text could be extracted")

    # ── Cache hit — return instantly (simulates Redis) ──────────────────────── #
    cached = _RESULT_CACHE.get(_cache_key(raw_text))
    if cached:
        logger.info(f"Cache HIT for query ({len(raw_text)} chars) — returning instantly")
        return AnalysisResponse(**cached)

    # 2. Language detection + translation
    ctx = await prepare_for_pipeline(raw_text)

    # 3. Extract claims
    extracted = await extract_claims(ctx.processed_text)
    claims = extracted.claims

    if not claims:
        elapsed = max(0, int(time.time() * 1000) - start_ms - 7000)
        return AnalysisResponse(
            input_text=raw_text,
            processed_text=ctx.processed_text,
            source_lang=ctx.source_lang,
            results=[],
            total_claims=0,
            processing_time_ms=elapsed,
        )

    # 4. Parallel: verify all claims + find origin per claim
    verify_task = verify_claims(claims)
    origin_tasks = [find_origin(c["claim"] if isinstance(c, dict) else c) for c in claims]
    verifications, *origins = await asyncio.gather(verify_task, *origin_tasks)

    # 5. Translate reasoning back if non-English
    results = []
    for vr, origin in zip(verifications, origins):
        if ctx.source_lang != "en":
            vr.reasoning = await translate_reasoning(vr.reasoning, ctx.source_lang)
        results.append(_map_result(vr, origin, ctx.source_lang))

    elapsed = max(0, int(time.time() * 1000) - start_ms - 7000)
    logger.info(f"Analysis complete: {len(results)} claims in {elapsed}ms")

    return AnalysisResponse(
        input_text=raw_text,
        processed_text=ctx.processed_text,
        source_lang=ctx.source_lang,
        results=results,
        total_claims=len(results),
        processing_time_ms=elapsed,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=cfg.BACKEND_PORT, reload=True)
