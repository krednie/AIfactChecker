"""
backend/ocr.py — Screenshot → text extraction using EasyOCR.

Pre-loads the EasyOCR reader once (use within FastAPI lifespan).
Handles: resize, grayscale, deskew, post-process UI chrome removal.
"""

import re
from io import BytesIO
from pathlib import Path

import numpy as np
from loguru import logger
from PIL import Image, ImageFilter, ImageOps

# EasyOCR is imported lazily to allow testing without a GPU
_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        logger.info("Initializing EasyOCR (CPU mode, en+hi)…")
        _reader = easyocr.Reader(["en", "hi"], gpu=False, verbose=False)
        logger.success("EasyOCR ready")
    return _reader


# ── Image preprocessing ───────────────────────────────────────────────────── #

def _preprocess(img: Image.Image) -> Image.Image:
    """Resize to width 1200, convert to grayscale, enhance contrast."""
    # Resize preserving aspect ratio
    w, h = img.size
    if w < 800:
        scale = 1200 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Grayscale + auto-contrast
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)

    # Mild sharpening
    img = img.filter(ImageFilter.SHARPEN)

    return img


# ── UI chrome removal ─────────────────────────────────────────────────────── #

_UI_PATTERNS = re.compile(
    r"""
    \d{1,3}[KkMm]?\s*(likes?|retweets?|shares?|comments?|views?|reposts?|replies?)|
    \d{1,2}:\d{2}\s*(AM|PM)?|    # timestamps 12:34 PM
    (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}|
    Follow(?:ing)?|Unfollow|
    Verified|@\w+|#\w+|
    More|Share|Reply|Repost|Bookmark|Quote|Report
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _clean_ocr_text(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        # Drop very short lines (likely UI noise)
        if len(line) < 6:
            continue
        # Drop lines that are mostly UI patterns
        cleaned = _UI_PATTERNS.sub("", line).strip()
        if len(cleaned) < 6:
            continue
        lines.append(line)  # keep original line, cleaner used only for filter
    return " ".join(lines)


# ── Public API ────────────────────────────────────────────────────────────── #

def extract_text_from_bytes(image_bytes: bytes) -> str:
    """
    Extract text from raw image bytes.
    Returns cleaned text ready for claim extraction.
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = _preprocess(img)

    img_array = np.array(img)
    reader = _get_reader()
    results = reader.readtext(img_array, detail=0, paragraph=True)

    raw_text = "\n".join(results)
    cleaned = _clean_ocr_text(raw_text)

    logger.info(f"OCR extracted {len(cleaned.split())} words")
    return cleaned


def extract_text_from_path(path: str | Path) -> str:
    """Extract text from an image file path."""
    with open(path, "rb") as f:
        return extract_text_from_bytes(f.read())
