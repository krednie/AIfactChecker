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

_TRENDING_HEADLINES = [
    "AI-generated deepfakes of Indian officials spreading on social media claiming military support for Israel",
    "Old 2016 photos of US Navy sailors being shared as Iran hostages in current Middle East conflict",
    "Viral video claims PM Modi announced nationwide lockdown due to major security crisis",
    "AI chatbot advice suggests replacing table salt with sodium bromide for better health",
    "WhatsApp message claims service will start charging Rs 99 per month from next week",
]

_trending_items: list[dict] = []
_trending_ready = False


async def _build_trending() -> None:
    """Fact-check top 5 news headlines in parallel at startup."""
    global _trending_items, _trending_ready
    try:
        logger.info("Trending: starting parallel fact-checks…")
        results = await asyncio.gather(
            *[_quick_check(h) for h in _TRENDING_HEADLINES],
            return_exceptions=True,
        )
        items = [r for r in results if isinstance(r, dict)]
        _trending_items = items
        _trending_ready = True
        logger.success(f"Trending: {len(items)} items ready")
    except Exception as e:
        logger.warning(f"Trending build failed: {e}")
        _trending_ready = True  # mark ready so endpoint doesn't hang


async def _quick_check(headline: str) -> dict:
    """Run a single claim through the normal verify_claim pipeline (uses DDG + GDELT internally)."""
    claim_data = {"claim": headline, "check_worthy": True}
    try:
        vr = await verify_claim(claim_data)
        stance = vr.stance.value
        label_map = {"Supported": "TRUE", "Refuted": "FALSE", "Uncertain": "UNVERIFIED"}
        top = vr.sources[0] if vr.sources else None
        return {
            "headline": headline[:120],
            "verdict": stance,
            "label": label_map.get(stance, "UNVERIFIED"),
            "source": top.source if top else "web",
            "url": top.url if top else "",
        }
    except Exception as e:
        logger.warning(f"_quick_check failed for '{headline[:50]}': {e}")
        return {
            "headline": headline[:120],
            "verdict": "Uncertain",
            "label": "UNVERIFIED",
            "source": "web",
            "url": "",
        }



# ── Lifespan (warm up heavy models once) ──────────────────────────────────── #

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Warming up models…")
    try:
        Retriever.get()          # loads FAISS + embedding model (~500 MB)
    except FileNotFoundError:
        logger.warning("FAISS index not found — run scripts/build_index.py first")
    # EasyOCR is NOT pre-loaded at startup to save ~700 MB RAM.
    # It will be lazily initialised on the first /ocr or /analyze-with-image request.
    # To pre-load it (e.g. on a high-RAM instance), set PRELOAD_OCR=true.
    if cfg.PRELOAD_OCR:
        try:
            _get_reader()
        except Exception as e:
            logger.warning(f"EasyOCR init failed: {e}")
    else:
        logger.info("EasyOCR deferred — will load on first OCR request (saves ~700 MB RAM)")
    # Trending pre-computation is opt-in (set PRELOAD_TRENDING=true).
    # Disabled by default to avoid 5 parallel LLM calls at cold start.
    if cfg.PRELOAD_TRENDING:
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

    # 2. Language detection + translation
    ctx = await prepare_for_pipeline(raw_text)

    # 3. Extract claims
    extracted = await extract_claims(ctx.processed_text)
    claims = extracted.claims

    if not claims:
        elapsed = int(time.time() * 1000) - start_ms
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

    elapsed = int(time.time() * 1000) - start_ms
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
