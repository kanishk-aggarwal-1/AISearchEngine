import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
import backend.app.routers.health as health_module


class PhaseSixTests(unittest.TestCase):
    def test_security_headers_are_present(self):
        main_module._RATE_LIMIT_BUCKETS.clear()
        client = TestClient(main_module.app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("default-src", response.headers.get("content-security-policy", ""))

    def test_rate_limit_blocks_after_threshold(self):
        from unittest.mock import PropertyMock
        main_module._RATE_LIMIT_BUCKETS.clear()
        # using_redis is a @property — patch via the type to return False (in-process path)
        with patch.object(type(main_module.cache), "using_redis", new_callable=PropertyMock, return_value=False), \
             patch.object(main_module.settings, "rate_limit_per_minute", 1):
            client = TestClient(main_module.app)
            first = client.get("/health")
            second = client.get("/health")
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 429)
        main_module._RATE_LIMIT_BUCKETS.clear()

    def test_deep_health_reports_components(self):
        main_module._RATE_LIMIT_BUCKETS.clear()
        with patch.object(health_module.store, "ping", return_value=True), \
             patch.object(health_module.store, "last_successful_ingestion_at", return_value="2026-05-12T10:00:00+00:00"), \
             patch.object(health_module.store, "source_freshness_summary", return_value={}), \
             patch.object(type(health_module.cache), "using_redis", new_callable=PropertyMock, return_value=True), \
             patch.object(health_module.cache, "ping", new=AsyncMock(return_value=True)), \
             patch.object(health_module.vector_index, "health", new=AsyncMock(
                 return_value={"backend": "qdrant", "enabled": False, "status": "unconfigured"}
             )):
            client = TestClient(main_module.app)
            response = client.get("/health/deep")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["components"]["database"]["status"], "ok")
            self.assertEqual(payload["components"]["cache"]["status"], "ok")
            self.assertEqual(
                payload["components"]["ingestion"]["last_successful_ingestion_at"],
                "2026-05-12T10:00:00+00:00",
            )

    def test_deep_health_reports_degraded_dependencies(self):
        main_module._RATE_LIMIT_BUCKETS.clear()
        with patch.object(health_module.store, "ping", return_value=False), \
             patch.object(health_module.store, "last_successful_ingestion_at", return_value=None), \
             patch.object(health_module.store, "source_freshness_summary", return_value={}), \
             patch.object(type(health_module.cache), "using_redis", new_callable=PropertyMock, return_value=True), \
             patch.object(health_module.cache, "ping", new=AsyncMock(return_value=False)), \
             patch.object(health_module.vector_index, "health", new=AsyncMock(
                 return_value={"backend": "qdrant", "enabled": True, "status": "degraded"}
             )):
            client = TestClient(main_module.app)
            response = client.get("/health/deep")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["components"]["database"]["status"], "degraded")
            self.assertEqual(payload["components"]["cache"]["status"], "degraded")
            self.assertEqual(payload["components"]["ingestion"]["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
