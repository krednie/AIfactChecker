"""
backend/cache.py — Redis-backed cache for analysis responses.

The cache is intentionally fail-open:
- startup should not crash if Redis is unavailable
- reads/writes should degrade to no-op on failures
- payloads are stored as JSON, keyed by a stable hash of normalized text
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

try:
    import redis.asyncio as redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    redis = None

    class RedisError(Exception):
        """Fallback Redis error when the redis package is not installed."""


class RedisAnalysisCache:
    def __init__(
        self,
        *,
        enabled: bool,
        redis_url: str,
        ttl_seconds: int,
        key_prefix: str,
    ) -> None:
        self.enabled = enabled
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self.client = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return bool(self.enabled and self._connected and self.client is not None)

    def _build_key(self, normalized_text: str) -> str:
        digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        return f"{self.key_prefix}:{digest}"

    async def startup(self) -> bool:
        if not self.enabled:
            logger.info("Redis cache disabled via configuration")
            self._connected = False
            return False

        if redis is None:
            logger.warning("Redis package not installed; continuing without cache")
            self._connected = False
            return False

        try:
            self.client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self.client.ping()
            self._connected = True
            logger.success("Redis cache connected at {}", self.redis_url)
            return True
        except Exception as exc:
            logger.warning("Redis startup failed: {}. Continuing without cache.", exc)
            self._connected = False
            await self.shutdown()
            return False

    async def shutdown(self) -> None:
        client = self.client
        self.client = None
        self._connected = False
        if client is None:
            return
        try:
            await client.aclose()
        except Exception as exc:
            logger.warning("Redis shutdown failed: {}", exc)

    async def ping(self) -> bool:
        if not self.client:
            self._connected = False
            return False
        try:
            pong = await self.client.ping()
            self._connected = bool(pong)
            return self._connected
        except Exception as exc:
            logger.warning("Redis ping failed: {}", exc)
            self._connected = False
            return False

    async def get_analysis(self, normalized_text: str) -> dict[str, Any] | None:
        if not self.client:
            return None

        key = self._build_key(normalized_text)
        try:
            raw = await self.client.get(key)
            if raw is None:
                logger.info("Redis cache MISS for {}", key)
                return None
            logger.info("Redis cache HIT for {}", key)
            self._connected = True
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis cache read failed: {}", exc)
            self._connected = False
            return None

    async def set_analysis(self, normalized_text: str, payload: dict[str, Any]) -> bool:
        if not self.client:
            return False

        key = self._build_key(normalized_text)
        try:
            await self.client.set(
                key,
                json.dumps(payload, ensure_ascii=False),
                ex=self.ttl_seconds,
            )
            logger.info("Redis cache WRITE for {}", key)
            self._connected = True
            return True
        except Exception as exc:
            logger.warning("Redis cache write failed: {}", exc)
            self._connected = False
            return False
