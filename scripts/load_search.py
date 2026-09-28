"""Small repeatable load probe for the search API.

Example: python scripts/load_search.py --requests 100 --concurrency 10
"""

import argparse
import asyncio
import statistics
import time

import httpx


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/search")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--query", default="latest artificial intelligence research")
    args = parser.parse_args()
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    latencies: list[float] = []
    failures = 0

    async with httpx.AsyncClient(timeout=60) as client:

        async def send() -> None:
            nonlocal failures
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post(
                        args.url,
                        json={
                            "query": args.query,
                            "user_id": "anonymous",
                            "categories": ["tech", "research"],
                            "top_k": 6,
                        },
                    )
                    if response.status_code >= 400:
                        failures += 1
                except httpx.HTTPError:
                    failures += 1
                finally:
                    latencies.append(time.perf_counter() - started)

        await asyncio.gather(*(send() for _ in range(max(1, args.requests))))

    ordered = sorted(latencies)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    print(
        f"requests={len(latencies)} failures={failures} "
        f"median_ms={statistics.median(latencies) * 1000:.1f} p95_ms={p95 * 1000:.1f}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
