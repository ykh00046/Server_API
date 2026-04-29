"""Manual performance smoke for Production Data Hub API.

Not part of CI. Run against a locally-started API:
    python scripts/perf_smoke.py --url http://localhost:8000 --n 10000 --path /healthz

Outputs a one-line JSON summary:
    {"elapsed_sec": 7.42, "rss_delta_mb": 3.1, "counts": {"2xx": 10000}}

`psutil` is optional; if missing, rss_delta_mb is null.
"""

from __future__ import annotations

import argparse
import json
import time

try:
    import httpx
except ImportError as exc:
    raise SystemExit("httpx is required. pip install httpx") from exc

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def run(url: str, path: str, n: int) -> dict:
    counts = {"2xx": 0, "4xx": 0, "5xx": 0, "error": 0}
    rss_before = None
    if _HAS_PSUTIL:
        rss_before = psutil.Process().memory_info().rss

    start = time.perf_counter()
    with httpx.Client(base_url=url, timeout=10.0) as client:
        for _ in range(n):
            try:
                r = client.get(path)
                bucket = f"{r.status_code // 100}xx"
                counts[bucket] = counts.get(bucket, 0) + 1
            except Exception:
                counts["error"] += 1
    elapsed = time.perf_counter() - start

    rss_delta_mb: float | None = None
    if _HAS_PSUTIL and rss_before is not None:
        rss_after = psutil.Process().memory_info().rss
        rss_delta_mb = round((rss_after - rss_before) / (1024 * 1024), 2)

    return {
        "elapsed_sec": round(elapsed, 2),
        "rps": round(n / elapsed, 1) if elapsed > 0 else None,
        "rss_delta_mb": rss_delta_mb,
        "counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--path", default="/healthz")
    parser.add_argument("--n", type=int, default=10000)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.path, args.n)))


if __name__ == "__main__":
    main()
