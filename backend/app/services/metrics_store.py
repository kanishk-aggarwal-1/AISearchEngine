"""
Redis-backed live metrics.

Every counter/gauge/histogram is persisted in Redis so the numbers survive
process restarts and serverless cold starts — the dashboard shows real
cumulative traffic, not per-instance memory that resets on every deploy.

When Redis is unavailable (local dev / tests without Redis) it transparently
falls back to an in-process mirror so the app still works; those numbers are
naturally non-persistent, which is fine for dev.

Only non-sensitive aggregate numbers are stored — no queries, no user IDs,
no PII. Just counts, latencies, and rates.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


# How many recent latency samples to keep for percentile estimation.
_LATENCY_WINDOW = 500
# How many trailing minutes the time-series chart covers.
_SERIES_MINUTES = 30
# Per-minute bucket TTL (seconds) — a bit over the chart window so old
# buckets self-expire and Redis never grows unbounded.
_BUCKET_TTL = 60 * (_SERIES_MINUTES + 10)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


class MetricsStore:
    def __init__(self, cache) -> None:
        # `cache` is the CacheService singleton; we use its raw redis client.
        self.cache = cache
        self.logger = getattr(cache, "logger", None)
        self.prefix = f"{getattr(cache, 'prefix', 'signalscope')}:metrics"
        # ── in-process fallback state ───────────────────────────────────────
        self._counters: dict[str, float] = defaultdict(float)
        self._latency: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._minute_count: dict[int, int] = defaultdict(int)
        self._minute_lat_sum: dict[int, float] = defaultdict(float)
        self._minute_lat_cnt: dict[int, int] = defaultdict(int)
        # ── summary cache ───────────────────────────────────────────────────
        # Avoid firing a 97-command Redis pipeline on every 5-second dashboard
        # poll.  We cache the assembled result for 2 s; within that window all
        # concurrent pollers share one pipeline execution.
        self._summary_cache: dict | None = None
        self._summary_cache_at: float = 0.0
        _SUMMARY_CACHE_TTL_S = 2.0
        self._summary_cache_ttl = _SUMMARY_CACHE_TTL_S

    # ── key helpers ─────────────────────────────────────────────────────────
    def _k(self, name: str) -> str:
        return f"{self.prefix}:{name}"

    @property
    def _redis(self):
        return self.cache.client if self.cache.using_redis else None

    @staticmethod
    def _now_minute() -> int:
        return int(time.time() // 60)

    # ── recording ────────────────────────────────────────────────────────────
    async def record_search(
        self,
        *,
        latency_ms: float,
        cache_hit: bool,
        citation_coverage: float,
        no_result: bool,
    ) -> None:
        """Record one completed search request. citation_coverage is a 0..1
        fraction of returned sources that carry a citation snippet."""
        latency_ms = max(0.0, float(latency_ms))
        citation_coverage = min(1.0, max(0.0, float(citation_coverage)))
        minute = self._now_minute()
        r = self._redis
        if r is not None:
            try:
                pipe = r.pipeline()
                pipe.incr(self._k("searches_total"))
                pipe.incr(self._k("cache_hits_total" if cache_hit else "cache_misses_total"))
                # Only count citation coverage for searches that actually returned
                # sources.  Including zero-result searches (coverage = 0.0) in the
                # denominator would silently deflate the reported average.
                if not no_result:
                    pipe.incrbyfloat(self._k("citation_sum"), citation_coverage)
                    pipe.incr(self._k("citation_n"))
                if no_result:
                    pipe.incr(self._k("no_result_total"))
                # latency samples (capped list)
                pipe.lpush(self._k("latency_ms"), latency_ms)
                pipe.ltrim(self._k("latency_ms"), 0, _LATENCY_WINDOW - 1)
                # per-minute buckets for the time series
                cnt_key = self._k(f"smin:{minute}")
                lsum_key = self._k(f"lsum:{minute}")
                lcnt_key = self._k(f"lcnt:{minute}")
                pipe.incr(cnt_key)
                pipe.expire(cnt_key, _BUCKET_TTL)
                pipe.incrbyfloat(lsum_key, latency_ms)
                pipe.expire(lsum_key, _BUCKET_TTL)
                pipe.incr(lcnt_key)
                pipe.expire(lcnt_key, _BUCKET_TTL)
                await pipe.execute()
                return
            except Exception as exc:  # pragma: no cover - network hiccup
                if self.logger:
                    self.logger.warning("metrics_record_failed error=%s — using in-process", exc)
        # ── in-process fallback ─────────────────────────────────────────────
        self._counters["searches_total"] += 1
        self._counters["cache_hits_total" if cache_hit else "cache_misses_total"] += 1
        if not no_result:
            self._counters["citation_sum"] += citation_coverage
            self._counters["citation_n"] += 1
        if no_result:
            self._counters["no_result_total"] += 1
        self._latency.append(latency_ms)
        self._minute_count[minute] += 1
        self._minute_lat_sum[minute] += latency_ms
        self._minute_lat_cnt[minute] += 1

    # ── reading ───────────────────────────────────────────────────────────────
    async def summary(self) -> dict:
        """Return live aggregate metrics. Pure reads — never mutates counters.

        The result is cached in-process for 2 s so that N concurrent dashboard
        pollers share one Redis pipeline execution instead of each firing 97
        commands independently.
        """
        now = time.time()
        if self._summary_cache is not None and (now - self._summary_cache_at) < self._summary_cache_ttl:
            return self._summary_cache

        minute = self._now_minute()
        recent_minutes = [minute - i for i in range(_SERIES_MINUTES - 1, -1, -1)]
        r = self._redis
        if r is not None:
            try:
                result = await self._summary_redis(r, recent_minutes)
                self._summary_cache = result
                self._summary_cache_at = now
                return result
            except Exception as exc:  # pragma: no cover
                if self.logger:
                    self.logger.warning("metrics_summary_failed error=%s — using in-process", exc)
        result = self._summary_inprocess(recent_minutes)
        self._summary_cache = result
        self._summary_cache_at = now
        return result

    async def _summary_redis(self, r, recent_minutes: list[int]) -> dict:
        pipe = r.pipeline()
        pipe.get(self._k("searches_total"))
        pipe.get(self._k("cache_hits_total"))
        pipe.get(self._k("cache_misses_total"))
        pipe.get(self._k("no_result_total"))
        pipe.get(self._k("citation_sum"))
        pipe.get(self._k("citation_n"))
        pipe.lrange(self._k("latency_ms"), 0, _LATENCY_WINDOW - 1)
        for m in recent_minutes:
            pipe.get(self._k(f"smin:{m}"))
            pipe.get(self._k(f"lsum:{m}"))
            pipe.get(self._k(f"lcnt:{m}"))
        res = await pipe.execute()

        searches_total = int(float(res[0] or 0))
        cache_hits = int(float(res[1] or 0))
        cache_misses = int(float(res[2] or 0))
        no_result = int(float(res[3] or 0))
        citation_sum = float(res[4] or 0.0)
        citation_n = int(float(res[5] or 0))
        latencies = [float(x) for x in (res[6] or [])]

        series = []
        idx = 7
        for m in recent_minutes:
            cnt = int(float(res[idx] or 0))
            lsum = float(res[idx + 1] or 0.0)
            lcnt = int(float(res[idx + 2] or 0))
            series.append({"minute": m, "searches": cnt, "avg_latency_ms": round(lsum / lcnt, 1) if lcnt else 0.0})
            idx += 3

        return self._assemble(
            searches_total, cache_hits, cache_misses, no_result,
            citation_sum, citation_n, latencies, series,
        )

    def _summary_inprocess(self, recent_minutes: list[int]) -> dict:
        series = []
        for m in recent_minutes:
            cnt = self._minute_count.get(m, 0)
            lcnt = self._minute_lat_cnt.get(m, 0)
            lsum = self._minute_lat_sum.get(m, 0.0)
            series.append({"minute": m, "searches": cnt, "avg_latency_ms": round(lsum / lcnt, 1) if lcnt else 0.0})
        return self._assemble(
            int(self._counters.get("searches_total", 0)),
            int(self._counters.get("cache_hits_total", 0)),
            int(self._counters.get("cache_misses_total", 0)),
            int(self._counters.get("no_result_total", 0)),
            self._counters.get("citation_sum", 0.0),
            int(self._counters.get("citation_n", 0)),
            list(self._latency),
            series,
        )

    def _assemble(
        self, searches_total, cache_hits, cache_misses, no_result,
        citation_sum, citation_n, latencies, series,
    ) -> dict:
        cache_total = cache_hits + cache_misses
        sorted_lat = sorted(latencies)
        searches_5m = sum(p["searches"] for p in series[-5:])
        return {
            "searches_total": searches_total,
            "searches_last_5min": searches_5m,
            "latency_p50_ms": round(_percentile(sorted_lat, 50), 1),
            "latency_p95_ms": round(_percentile(sorted_lat, 95), 1),
            "cache_hit_rate": round(cache_hits / cache_total, 4) if cache_total else 0.0,
            "cache_hits_total": cache_hits,
            "cache_misses_total": cache_misses,
            "citation_coverage_pct": round((citation_sum / citation_n) * 100, 1) if citation_n else 0.0,
            "no_result_rate": round(no_result / searches_total, 4) if searches_total else 0.0,
            "no_result_total": no_result,
            "series": series,
            "backend": "redis" if self.cache.using_redis else "in-process",
        }
