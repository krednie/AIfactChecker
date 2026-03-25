"""
scripts/test_keys.py — Verify that Groq and Sarvam API keys are valid.
Run: python scripts/test_keys.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.config import cfg
from loguru import logger


async def test_groq():
    from groq import AsyncGroq
    client = AsyncGroq(api_key=cfg.GROQ_API_KEY, timeout=5.0)
    response = await client.chat.completions.create(
        model=cfg.GROQ_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        max_tokens=10,
    )
    answer = response.choices[0].message.content.strip()
    assert answer, "Empty response from model"
    logger.success(f"✅  Groq API OK — model={cfg.GROQ_MODEL}, reply='{answer[:50]}'")


async def test_sarvam():
    import httpx
    url = "https://api.sarvam.ai/translate"
    payload = {
        "input": "Hello",
        "source_language_code": "en-IN",
        "target_language_code": "hi-IN",
        "speaker_gender": "Female",
        "mode": "formal",
        "model": "mayura:v1",
        "enable_preprocessing": False,
    }
    headers = {"api-subscription-key": cfg.SARVAM_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        translated = data.get("translated_text", "")
        assert translated, "Empty translation response"
        logger.success(f"✅  Sarvam API OK — translated: '{translated}'")


async def main():
    logger.info("Testing API keys…")
    results = {"groq": False, "sarvam": False}

    try:
        logger.info("Starting test_groq...")
        await test_groq()
        logger.info("Finished test_groq.")
        results["groq"] = True
    except Exception as e:
        logger.error(f"❌  Groq FAILED: {e}")

    try:
        logger.info("Starting test_sarvam...")
        await test_sarvam()
        logger.info("Finished test_sarvam.")
        results["sarvam"] = True
    except Exception as e:
        logger.error(f"❌  Sarvam FAILED: {e}")

    if all(results.values()):
        logger.success("All API keys verified!")
        sys.exit(0)
    else:
        failed = [k for k, v in results.items() if not v]
        logger.error(f"Failed APIs: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
