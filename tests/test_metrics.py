"""
Tests for the Redis-backed live metrics (MetricsStore) and the public
GET /metrics/summary endpoint.

Uses an in-process fake cache (using_redis=False) so the fallback path is
exercised deterministically without a Redis dependency.
"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.services.document_store import DocumentStore
from backend.app.services.metrics_store import MetricsStore, _percentile


def _run(coro):
    return asyncio.run(coro)


def _inprocess_metrics():
    cache = SimpleNamespace(using_redis=False, client=None, logger=None, prefix="test")
    return MetricsStore(cache)


class PercentileTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_percentile([], 50), 0.0)

    def test_single(self):
        self.assertEqual(_percentile([42.0], 95), 42.0)

    def test_p50_median(self):
        self.assertEqual(_percentile([10, 20, 30], 50), 20)

    def test_p95_near_top(self):
        vals = sorted(float(i) for i in range(1, 101))  # 1..100
        self.assertGreaterEqual(_percentile(vals, 95), 95)


class MetricsStoreTests(unittest.TestCase):
    def test_initial_summary_is_zeroed(self):
        m = _inprocess_metrics()
        s = _run(m.summary())
        self.assertEqual(s["searches_total"], 0)
        self.assertEqual(s["cache_hit_rate"], 0.0)
        self.assertEqual(s["no_result_rate"], 0.0)
        self.assertEqual(s["backend"], "in-process")

    def test_records_searches_and_totals(self):
        m = _inprocess_metrics()
        _run(m.record_search(latency_ms=100, cache_hit=False, citation_coverage=1.0, no_result=False))
        _run(m.record_search(latency_ms=200, cache_hit=True, citation_coverage=0.5, no_result=False))
        _run(m.record_search(latency_ms=300, cache_hit=False, citation_coverage=0.0, no_result=True))
        s = _run(m.summary())
        self.assertEqual(s["searches_total"], 3)
        self.assertEqual(s["cache_hits_total"], 1)
        self.assertEqual(s["cache_misses_total"], 2)
        # cache hit rate = 1/3
        self.assertAlmostEqual(s["cache_hit_rate"], 0.3333, places=3)
        # citation coverage avg = (1.0 + 0.5) / 2 = 75%
        # The no-result search (coverage=0.0) is excluded from both numerator
        # AND denominator — averaging zero-result searches in deflates the metric.
        self.assertAlmostEqual(s["citation_coverage_pct"], 75.0, places=1)
        # no-result rate = 1/3
        self.assertAlmostEqual(s["no_result_rate"], 0.3333, places=3)

    def test_latency_percentiles(self):
        m = _inprocess_metrics()
        for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            _run(m.record_search(latency_ms=ms, cache_hit=False, citation_coverage=1.0, no_result=False))
        s = _run(m.summary())
        self.assertGreater(s["latency_p50_ms"], 0)
        self.assertGreaterEqual(s["latency_p95_ms"], s["latency_p50_ms"])

    def test_series_has_30_minute_buckets(self):
        m = _inprocess_metrics()
        _run(m.record_search(latency_ms=120, cache_hit=False, citation_coverage=1.0, no_result=False))
        s = _run(m.summary())
        self.assertEqual(len(s["series"]), 30)
        # the most recent bucket should contain our search
        self.assertEqual(s["series"][-1]["searches"], 1)
        self.assertEqual(s["searches_last_5min"], 1)

    def test_redis_pipeline_path(self):
        """When using_redis=True, record/summary drive the redis pipeline."""
        recorded = {}

        class FakePipe:
            def __init__(self):
                self.ops = []

            def incr(self, k):
                self.ops.append(("incr", k))
                return self

            def incrbyfloat(self, k, v):
                self.ops.append(("incrbyfloat", k, v))
                return self

            def lpush(self, k, v):
                self.ops.append(("lpush", k, v))
                return self

            def ltrim(self, k, a, b):
                return self

            def expire(self, k, t):
                return self

            async def execute(self):
                for op in self.ops:
                    if op[0] == "incr":
                        recorded[op[1]] = recorded.get(op[1], 0) + 1
                return []

        fake_client = SimpleNamespace(pipeline=lambda: FakePipe())
        cache = SimpleNamespace(using_redis=True, client=fake_client, logger=None, prefix="test")
        m = MetricsStore(cache)
        _run(m.record_search(latency_ms=50, cache_hit=False, citation_coverage=1.0, no_result=False))
        # searches_total + cache_misses_total + citation_n + per-min count were incr'd
        self.assertTrue(any("searches_total" in k for k in recorded))


class MetricsSummaryEndpointTests(unittest.TestCase):
    def test_summary_endpoint_public_and_shaped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "metrics_http.db"))
            fresh_metrics = _inprocess_metrics()
            _run(fresh_metrics.record_search(latency_ms=123, cache_hit=False, citation_coverage=1.0, no_result=False))
            fake_cache = SimpleNamespace(using_redis=False, incr=AsyncMock(return_value=1), ping=AsyncMock(return_value=False))
            with (
                patch("backend.app.routers.health.store", store),
                patch("backend.app.routers.health.metrics_store", fresh_metrics),
                patch("backend.app.main.cache", fake_cache),
                patch("backend.app.main.embedding_service", SimpleNamespace(real_embeddings_enabled=True)),
            ):
                client = TestClient(main_module.app)
                r = client.get("/metrics/summary")
                self.assertEqual(r.status_code, 200)
                body = r.json()
                # required keys present
                for key in [
                    "searches_total", "searches_last_5min", "latency_p50_ms", "latency_p95_ms",
                    "cache_hit_rate", "citation_coverage_pct", "no_result_rate",
                    "documents_indexed", "distinct_sources", "last_ingestion_at", "series",
                ]:
                    self.assertIn(key, body)
                self.assertEqual(body["searches_total"], 1)
                # no sensitive fields leaked
                blob = r.text.lower()
                for forbidden in ["password", "api_key", "token", "secret", "email"]:
                    self.assertNotIn(forbidden, blob)


if __name__ == "__main__":
    unittest.main()
