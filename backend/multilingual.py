"""
backend/multilingual.py — Language detection + translation via Sarvam AI.

Pipeline:
1. Detect language (simple heuristic; Sarvam doesn't have a detect endpoint)
2. If non-English → translate to English before pipeline
3. After verification → translate reasoning back to original language
4. (Stretch) TTS via Sarvam for verdict readback
"""

import asyncio
from dataclasses import dataclass

import httpx
from loguru import logger

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.config import cfg

# ── Sarvam language codes ─────────────────────────────────────────────────── #

LANG_MAP = {
    "hi": "hi-IN",  # Hindi
    "bn": "bn-IN",  # Bengali
    "ta": "ta-IN",  # Tamil
    "te": "te-IN",  # Telugu
    "mr": "mr-IN",  # Marathi
    "gu": "gu-IN",  # Gujarati
    "kn": "kn-IN",  # Kannada
    "ml": "ml-IN",  # Malayalam
    "pa": "pa-IN",  # Punjabi
    "or": "or-IN",  # Odia
    "en": "en-IN",
}

SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/translate"


# ── Simple language detection ─────────────────────────────────────────────── #

def detect_language(text: str) -> str:
    """
    Heuristic language detection via Unicode range analysis.
    Returns ISO 639-1 code ('en', 'hi', 'bn', etc.)
    """
    if not text:
        return "en"

    counts = {
        "hi": sum(1 for c in text if "\u0900" <= c <= "\u097F"),  # Devanagari
        "bn": sum(1 for c in text if "\u0980" <= c <= "\u09FF"),  # Bengali
        "ta": sum(1 for c in text if "\u0B80" <= c <= "\u0BFF"),  # Tamil
        "te": sum(1 for c in text if "\u0C00" <= c <= "\u0C7F"),  # Telugu
        "gu": sum(1 for c in text if "\u0A80" <= c <= "\u0AFF"),  # Gujarati
        "ml": sum(1 for c in text if "\u0D00" <= c <= "\u0D7F"),  # Malayalam
        "kn": sum(1 for c in text if "\u0C80" <= c <= "\u0CFF"),  # Kannada
        "pa": sum(1 for c in text if "\u0A00" <= c <= "\u0A7F"),  # Gurmukhi
    }

    best_lang = max(counts, key=counts.get)
    total_chars = len(text.replace(" ", ""))
    if total_chars > 0 and counts[best_lang] / total_chars > 0.15:
        return best_lang
    return "en"


# ── Sarvam translation ────────────────────────────────────────────────────── #

async def _translate(text: str, source: str, target: str) -> str:
    if source == target:
        return text
    if len(text.strip()) < 3:
        return text

    source_code = LANG_MAP.get(source, "en-IN")
    target_code = LANG_MAP.get(target, "en-IN")

    payload = {
        "input": text[:1000],  # Sarvam limit
        "source_language_code": source_code,
        "target_language_code": target_code,
        "speaker_gender": "Female",
        "mode": "formal",
        "model": "mayura:v1",
        "enable_preprocessing": True,
    }
    headers = {
        "api-subscription-key": cfg.SARVAM_API_KEY,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(SARVAM_TRANSLATE_URL, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return data.get("translated_text", text)


# ── Public API ────────────────────────────────────────────────────────────── #

@dataclass
class TranslationContext:
    original_text: str
    processed_text: str   # English, ready for pipeline
    source_lang: str      # ISO 639-1


async def prepare_for_pipeline(text: str) -> TranslationContext:
    """Detect language and translate to English if needed."""
    lang = detect_language(text)
    if lang == "en":
        return TranslationContext(
            original_text=text,
            processed_text=text,
            source_lang="en",
        )

    try:
        translated = await _translate(text, source=lang, target="en")
        logger.info(f"Translated from '{lang}' to English")
    except Exception as e:
        logger.warning(f"Sarvam translation failed ({e}), using original text")
        translated = text

    return TranslationContext(
        original_text=text,
        processed_text=translated,
        source_lang=lang,
    )


async def translate_reasoning(reasoning: str, target_lang: str) -> str:
    """Translate LLM reasoning back to user's original language."""
    if target_lang == "en":
        return reasoning
    try:
        return await _translate(reasoning, source="en", target=target_lang)
    except Exception as e:
        logger.warning(f"Reasoning translation failed: {e}")
        return reasoning
