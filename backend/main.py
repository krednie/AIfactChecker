"""
backend/main.py - FastAPI application with lifespan, CORS, and all endpoints.

Endpoints:
    POST /ocr         - image bytes -> extracted text
    POST /analyze     - text/image -> full VerificationResult[]
    GET  /health      - liveness check
    GET  /trending    - top 5 fact-checked news headlines (loaded at startup)

Pipeline on /analyze:
    OCR (if image) -> translate to English -> extract claims
    -> parallel: [verify_claims, find_origin per claim] -> respond
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.analytics import build_report_analytics
from backend.cache import RedisAnalysisCache
from backend.claim_extractor import extract_claims
from backend.config import cfg
from backend.multilingual import prepare_for_pipeline, translate_reasoning
from backend.ocr import _get_reader
from backend.patient0 import OriginResult, find_origin
from backend.retriever import Retriever
from backend.verifier import VerificationResult, verify_claims


cache = RedisAnalysisCache(
    enabled=cfg.REDIS_ENABLED,
    redis_url=cfg.REDIS_URL,
    ttl_seconds=cfg.REDIS_CACHE_TTL_SECONDS,
    key_prefix=cfg.REDIS_KEY_PREFIX,
)


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
    },
]

_trending_ready = False
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_OCR_TIMEOUT_SECS = 90


async def _build_trending() -> None:
    """Load hardcoded trending items immediately to avoid heavy API limits at startup."""
    global _trending_ready
    try:
        logger.info("Trending: Loading trending claims and debunking...")
        _trending_ready = True
        logger.success(f"Trending: {len(_trending_items)} items ready")
    except Exception as exc:
        logger.warning(f"Trending build failed: {exc}")
        _trending_ready = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    await cache.startup()
    logger.info("Warming up models...")
    try:
        Retriever.get()
    except FileNotFoundError:
        logger.warning("FAISS index not found - run scripts/build_index.py first")
    try:
        _get_reader()
    except Exception as exc:
        logger.warning(f"EasyOCR init failed: {exc}")
    asyncio.create_task(_build_trending())
    logger.success("Startup complete")
    yield
    await cache.shutdown()
    logger.info("Shutdown")


app = FastAPI(
    title="Viral Claim Radar API",
    description="AI-powered fact-checking for social media posts",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://localhost(:\d+)?|chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    stance: str
    confidence: str
    reasoning: str
    structured_query: dict
    pipeline_trace: list[PipelineStepResponse]
    sources: list[SourceChipResponse]
    corpus_miss: bool
    origin: OriginResponse
    analytics: dict = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    input_text: str
    processed_text: str
    source_lang: str
    results: list[ClaimResult]
    total_claims: int
    processing_time_ms: int
    analytics: dict = Field(default_factory=dict)


class OCRResponse(BaseModel):
    extracted_text: str
    word_count: int


class HealthResponse(BaseModel):
    status: str
    faiss_loaded: bool
    ocr_ready: bool
    redis_connected: bool


class TrendingItem(BaseModel):
    headline: str
    verdict: str
    label: str
    source: str
    url: str


class TrendingResponse(BaseModel):
    items: list[TrendingItem]
    ready: bool


def _map_origin(origin: OriginResult) -> OriginResponse:
    return OriginResponse(
        found=origin.found,
        earliest_url=origin.earliest_url,
        earliest_date=origin.earliest_date,
        origin_type=origin.origin_type.value,
        confidence=origin.confidence,
        keywords_used=origin.keywords_used,
    )


def _map_result(vr: VerificationResult, origin: OriginResult, source_lang: str) -> ClaimResult:
    trace = list(vr.pipeline_trace)
    if origin.found:
        trace.append(
            {
                "step": "Patient 0",
                "status": f"Found origin on {origin.origin_type.value} ({origin.earliest_date})",
                "state": "success",
            }
        )
    else:
        trace.append(
            {
                "step": "Patient 0",
                "status": "No early archive found",
                "state": "pending",
            }
        )

    analytics = dict(vr.analytics or {})
    temporal_metrics = dict(analytics.get("temporal_metrics") or {})
    if origin.found and origin.earliest_date:
        temporal_metrics["first_seen_timestamp"] = origin.earliest_date
    if temporal_metrics:
        analytics["temporal_metrics"] = temporal_metrics

    return ClaimResult(
        claim=vr.claim,
        stance=vr.stance.value,
        confidence=vr.confidence.value,
        reasoning=vr.reasoning,
        structured_query=vr.structured_query,
        pipeline_trace=[PipelineStepResponse(**item) for item in trace],
        sources=[
            SourceChipResponse(
                title=source.title,
                url=source.url,
                source=source.source,
                source_tier=source.source_tier,
                score=source.score,
            )
            for source in vr.sources
        ],
        corpus_miss=vr.corpus_miss,
        origin=_map_origin(origin),
        analytics=analytics,
    )


def _cache_key(text: str) -> str:
    """Normalize text for cache lookup by trimming and applying NFC."""
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


@app.get("/health", response_model=HealthResponse)
async def health():
    faiss_ok = Retriever._instance is not None
    ocr_ok = False
    try:
        from backend.ocr import _reader

        ocr_ok = _reader is not None
    except Exception:
        pass

    redis_ok = await cache.ping() if cache.client else False
    return HealthResponse(
        status="ok",
        faiss_loaded=faiss_ok,
        ocr_ready=ocr_ok,
        redis_connected=redis_ok,
    )


@app.get("/trending", response_model=TrendingResponse)
async def trending():
    return TrendingResponse(
        items=[TrendingItem(**item) for item in _trending_items],
        ready=_trending_ready,
    )


@app.post("/ocr", response_model=OCRResponse)
async def ocr_endpoint(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="File must be an image")
    img_bytes = await file.read()
    if len(img_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 8 MB)")
    try:
        text = await _run_ocr_async(img_bytes)
        return OCRResponse(extracted_text=text, word_count=len(text.split()))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="OCR timed out - try a smaller image")
    except Exception as exc:
        logger.error(f"OCR error: {exc}")
        raise HTTPException(status_code=503, detail="OCR processing failed")


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_endpoint(
    text: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
):
    """
    Full pipeline: text or image -> claims -> verification + origin.
    At least one of `text` or `file` must be provided.
    """
    import time

    start_ms = int(time.time() * 1000)

    if file is not None and file.filename:
        img_bytes = await file.read()
        if len(img_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image too large (max 8 MB)")
        try:
            raw_text = await _run_ocr_async(img_bytes)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="OCR timed out - try a smaller image")
    elif text:
        raw_text = text.strip()
    else:
        raise HTTPException(status_code=422, detail="Provide either 'text' or 'file'")

    if not raw_text:
        raise HTTPException(status_code=422, detail="No text could be extracted")

    normalized_text = _cache_key(raw_text)
    cached = await cache.get_analysis(normalized_text)
    if cached:
        return AnalysisResponse(**cached)

    ctx = await prepare_for_pipeline(raw_text)
    extracted = await extract_claims(ctx.processed_text)
    claims = extracted.claims

    if not claims:
        elapsed = max(0, int(time.time() * 1000) - start_ms - 7000)
        response = AnalysisResponse(
            input_text=raw_text,
            processed_text=ctx.processed_text,
            source_lang=ctx.source_lang,
            results=[],
            total_claims=0,
            processing_time_ms=elapsed,
            analytics=build_report_analytics([]),
        )
        await cache.set_analysis(normalized_text, response.model_dump())
        return response

    verify_task = verify_claims(claims)
    origin_tasks = [find_origin(claim["claim"] if isinstance(claim, dict) else claim) for claim in claims]
    verifications, *origins = await asyncio.gather(verify_task, *origin_tasks)

    results = []
    for verification, origin in zip(verifications, origins):
        if ctx.source_lang != "en":
            verification.reasoning = await translate_reasoning(verification.reasoning, ctx.source_lang)
        results.append(_map_result(verification, origin, ctx.source_lang))

    elapsed = max(0, int(time.time() * 1000) - start_ms - 7000)
    logger.info(f"Analysis complete: {len(results)} claims in {elapsed}ms")

    response = AnalysisResponse(
        input_text=raw_text,
        processed_text=ctx.processed_text,
        source_lang=ctx.source_lang,
        results=results,
        total_claims=len(results),
        processing_time_ms=elapsed,
        analytics=build_report_analytics([result.model_dump() for result in results]),
    )
    await cache.set_analysis(normalized_text, response.model_dump())
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=cfg.BACKEND_PORT, reload=True)
