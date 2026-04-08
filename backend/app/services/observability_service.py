import threading
import time
from collections import defaultdict
from typing import Dict


class MetricsService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._timings_count: Dict[str, int] = defaultdict(int)
        self._timings_sum: Dict[str, float] = defaultdict(float)
        self._started = time.time()

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            self._timings_count[name] += 1
            self._timings_sum[name] += float(max(0.0, seconds))

    def snapshot(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
            timings = {
                key: {
                    "count": self._timings_count.get(key, 0),
                    "sum_seconds": round(self._timings_sum.get(key, 0.0), 6),
                    "avg_seconds": round(
                        (self._timings_sum.get(key, 0.0) / self._timings_count.get(key, 1))
                        if self._timings_count.get(key, 0)
                        else 0.0,
                        6,
                    ),
                }
                for key in set(self._timings_count.keys()) | set(self._timings_sum.keys())
            }
        return {
            "uptime_seconds": round(time.time() - self._started, 2),
            "counters": counters,
            "timings": timings,
        }

    def as_prometheus_text(self) -> str:
        snap = self.snapshot()
        lines = []
        for key, val in snap["counters"].items():
            metric = key.replace(".", "_")
            lines.append(f"signalscope_{metric} {val}")

        for key, val in snap["timings"].items():
            metric = key.replace(".", "_")
            lines.append(f"signalscope_{metric}_count {val['count']}")
            lines.append(f"signalscope_{metric}_sum_seconds {val['sum_seconds']}")
            lines.append(f"signalscope_{metric}_avg_seconds {val['avg_seconds']}")

        lines.append(f"signalscope_uptime_seconds {snap['uptime_seconds']}")
        return "\n".join(lines) + "\n"
