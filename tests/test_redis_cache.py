import copy
import importlib
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _install_import_stubs() -> None:
    if "groq" not in sys.modules:
        groq_module = types.ModuleType("groq")

        class AsyncGroq:  # pragma: no cover - import shim only
            def __init__(self, *args, **kwargs):
                pass

        groq_module.AsyncGroq = AsyncGroq
        sys.modules["groq"] = groq_module

    if "faiss" not in sys.modules:
        faiss_module = types.ModuleType("faiss")

        class _Index:  # pragma: no cover - import shim only
            ntotal = 0

            def reconstruct_n(self, start, total):
                del start, total
                return []

        def read_index(path):  # pragma: no cover - import shim only
            del path
            return _Index()

        faiss_module.read_index = read_index
        sys.modules["faiss"] = faiss_module

    if "sentence_transformers" not in sys.modules:
        st_module = types.ModuleType("sentence_transformers")

        class SentenceTransformer:  # pragma: no cover - import shim only
            def __init__(self, *args, **kwargs):
                pass

            def encode(self, *args, **kwargs):
                return []

        st_module.SentenceTransformer = SentenceTransformer
        sys.modules["sentence_transformers"] = st_module

    if "rank_bm25" not in sys.modules:
        bm25_module = types.ModuleType("rank_bm25")

        class BM25Okapi:  # pragma: no cover - import shim only
            def __init__(self, *args, **kwargs):
                pass

            def get_scores(self, *args, **kwargs):
                return []

        bm25_module.BM25Okapi = BM25Okapi
        sys.modules["rank_bm25"] = bm25_module


os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("SARVAM_API_KEY", "test-sarvam-key")
_install_import_stubs()

main = importlib.import_module("backend.main")
cache_module = importlib.import_module("backend.cache")


class FakeCache:
    def __init__(self, *, connected: bool = True):
        self.store: dict[str, dict] = {}
        self.client = object() if connected else None
        self.started = False
        self.stopped = False
        self.get_calls = 0
        self.set_calls = 0

    async def startup(self) -> bool:
        self.started = True
        return self.client is not None

    async def shutdown(self) -> None:
        self.stopped = True

    async def ping(self) -> bool:
        return self.client is not None

    async def get_analysis(self, normalized_text: str) -> dict | None:
        self.get_calls += 1
        payload = self.store.get(normalized_text)
        return copy.deepcopy(payload) if payload is not None else None

    async def set_analysis(self, normalized_text: str, payload: dict) -> bool:
        self.set_calls += 1
        if self.client is None:
            return False
        self.store[normalized_text] = copy.deepcopy(payload)
        return True


def _origin_result():
    return SimpleNamespace(
        found=False,
        earliest_url=None,
        earliest_date=None,
        origin_type=SimpleNamespace(value="Unknown"),
        confidence="Low",
        keywords_used=[],
    )


def _verification_result(claim: str):
    return SimpleNamespace(
        claim=claim,
        stance=SimpleNamespace(value="Supported"),
        confidence=SimpleNamespace(value="High"),
        reasoning="Verified with trusted evidence.",
        structured_query={"claim": claim},
        pipeline_trace=[],
        sources=[
            SimpleNamespace(
                title="Trusted source",
                url="https://example.com/story",
                source="example",
                source_tier="verified",
                score=0.9,
            )
        ],
        corpus_miss=False,
        analytics={"confidence_score": 0.9},
    )


class AnalyzeCacheTests(unittest.TestCase):
    def _client(self, fake_cache: FakeCache, *, prepare_mock, extract_mock, verify_mock, find_origin_mock, ocr_mock=None):
        patches = [
            patch.object(main, "cache", fake_cache),
            patch.object(main.Retriever, "get", return_value=object()),
            patch.object(main, "_get_reader", return_value=object()),
            patch.object(main, "prepare_for_pipeline", prepare_mock),
            patch.object(main, "extract_claims", extract_mock),
            patch.object(main, "verify_claims", verify_mock),
            patch.object(main, "find_origin", find_origin_mock),
            patch.object(main, "build_report_analytics", return_value={"summary": "ok"}),
        ]
        if ocr_mock is not None:
            patches.append(patch.object(main, "_run_ocr_async", ocr_mock))
        return patches

    def test_cache_miss_then_hit_uses_normalized_text_key(self):
        fake_cache = FakeCache()
        prepare_mock = AsyncMock(
            return_value=SimpleNamespace(processed_text="Cafe rumor", source_lang="en")
        )
        extract_mock = AsyncMock(return_value=SimpleNamespace(claims=[{"claim": "Cafe rumor"}]))
        verify_mock = AsyncMock(return_value=[_verification_result("Cafe rumor")])
        find_origin_mock = AsyncMock(return_value=_origin_result())

        patches = self._client(
            fake_cache,
            prepare_mock=prepare_mock,
            extract_mock=extract_mock,
            verify_mock=verify_mock,
            find_origin_mock=find_origin_mock,
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            with TestClient(main.app) as client:
                first = client.post("/analyze", data={"text": "Cafe\u0301 rumor"})
                second = client.post("/analyze", data={"text": "  Caf\u00e9 rumor  "})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["results"], second.json()["results"])
        self.assertTrue(fake_cache.started)
        self.assertTrue(fake_cache.stopped)
        self.assertEqual(prepare_mock.await_count, 1)
        self.assertEqual(extract_mock.await_count, 1)
        self.assertEqual(verify_mock.await_count, 1)
        self.assertEqual(find_origin_mock.await_count, 1)
        self.assertEqual(fake_cache.set_calls, 1)

    def test_text_and_ocr_requests_share_cached_analysis(self):
        fake_cache = FakeCache()
        prepare_mock = AsyncMock(
            return_value=SimpleNamespace(processed_text="Same rumor", source_lang="en")
        )
        extract_mock = AsyncMock(return_value=SimpleNamespace(claims=[{"claim": "Same rumor"}]))
        verify_mock = AsyncMock(return_value=[_verification_result("Same rumor")])
        find_origin_mock = AsyncMock(return_value=_origin_result())
        ocr_mock = AsyncMock(return_value="Same rumor")

        patches = self._client(
            fake_cache,
            prepare_mock=prepare_mock,
            extract_mock=extract_mock,
            verify_mock=verify_mock,
            find_origin_mock=find_origin_mock,
            ocr_mock=ocr_mock,
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            with TestClient(main.app) as client:
                first = client.post("/analyze", data={"text": "Same rumor"})
                second = client.post(
                    "/analyze",
                    files={"file": ("claim.png", b"fake-image", "image/png")},
                )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(prepare_mock.await_count, 1)
        self.assertEqual(extract_mock.await_count, 1)
        self.assertEqual(verify_mock.await_count, 1)
        self.assertEqual(find_origin_mock.await_count, 1)
        self.assertEqual(ocr_mock.await_count, 1)
        self.assertEqual(fake_cache.set_calls, 1)

    def test_backend_runs_uncached_when_redis_is_unavailable(self):
        fake_cache = FakeCache(connected=False)
        prepare_mock = AsyncMock(
            return_value=SimpleNamespace(processed_text="Fallback rumor", source_lang="en")
        )
        extract_mock = AsyncMock(return_value=SimpleNamespace(claims=[{"claim": "Fallback rumor"}]))
        verify_mock = AsyncMock(return_value=[_verification_result("Fallback rumor")])
        find_origin_mock = AsyncMock(return_value=_origin_result())

        patches = self._client(
            fake_cache,
            prepare_mock=prepare_mock,
            extract_mock=extract_mock,
            verify_mock=verify_mock,
            find_origin_mock=find_origin_mock,
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            with TestClient(main.app) as client:
                analyze = client.post("/analyze", data={"text": "Fallback rumor"})
                health = client.get("/health")

        self.assertEqual(analyze.status_code, 200)
        self.assertEqual(health.status_code, 200)
        self.assertFalse(health.json()["redis_connected"])
        self.assertTrue(fake_cache.started)
        self.assertTrue(fake_cache.stopped)
        self.assertEqual(prepare_mock.await_count, 1)
        self.assertEqual(fake_cache.set_calls, 1)

    def test_health_reports_connected_redis(self):
        fake_cache = FakeCache(connected=True)

        with patch.object(main, "cache", fake_cache), \
             patch.object(main.Retriever, "get", return_value=object()), \
             patch.object(main, "_get_reader", return_value=object()):
            with TestClient(main.app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["redis_connected"])


class RedisAnalysisCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_read_write_failures_are_fail_open(self):
        class ExplodingClient:
            async def get(self, key):
                del key
                raise RuntimeError("boom")

            async def set(self, key, value, ex=None):
                del key, value, ex
                raise RuntimeError("boom")

            async def aclose(self):
                return None

        redis_cache = cache_module.RedisAnalysisCache(
            enabled=True,
            redis_url="redis://localhost:6379/0",
            ttl_seconds=60,
            key_prefix="test",
        )
        redis_cache.client = ExplodingClient()
        redis_cache._connected = True

        cached = await redis_cache.get_analysis("test")
        written = await redis_cache.set_analysis("test", {"ok": True})

        self.assertIsNone(cached)
        self.assertFalse(written)
        self.assertFalse(redis_cache.is_connected)


if __name__ == "__main__":
    unittest.main()
