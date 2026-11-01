"""Show per-request distribution across v1/v2, based on /health JSON version.

Examples:
 python3 scripts/traffic_report.py --requests 1000
 python3 scripts/traffic_report.py --requests 1000 --min-v2-pct 2 --max-v2-pct 10
"""
import argparse
import json
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def report(url: str, requests: int, timeout: float) -> tuple[Counter, int]:
    counts: Counter[str] = Counter()
    failed = 0
    for index in range(requests):
        req = Request(url, headers={"Connection": "close", "Cache-Control": "no-cache"})
        try:
            with urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    raise ValueError(f"unexpected HTTP {response.status}")
                payload = json.load(response)
                if payload.get("status") != "ok" or payload.get("version") not in {"v1", "v2"}:
                    raise ValueError(f"unexpected payload: {payload}")
                counts[payload["version"]] += 1
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            failed += 1
            if failed <= 5:
                print(f"Request {index + 1} failed: {exc}")
    return counts, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure canary per-request distribution")
    parser.add_argument("--url", default="http://127.0.0.1:18082/health")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--min-v2-pct", type=float)
    parser.add_argument("--max-v2-pct", type=float)
    args = parser.parse_args()
    if args.requests < 1 or args.timeout <= 0:
        parser.error("requests and timeout must be positive")
    counts, failures = report(args.url, args.requests, args.timeout)
    successful = sum(counts.values())
    print(f"Total: {args.requests}, successful: {successful}, failed: {failures}")
    for version in ("v1", "v2"):
        percentage = 100 * counts[version] / successful if successful else 0
        print(f"{version}: {counts[version]} requests ({percentage:.2f}% of successful)")
    if failures or not successful:
        raise SystemExit("FAIL: requests did not all succeed")
    v2 = 100 * counts["v2"] / successful
    if args.min_v2_pct is not None and v2 < args.min_v2_pct:
        raise SystemExit(f"FAIL: v2 {v2:.2f}% is below minimum {args.min_v2_pct}%")
    if args.max_v2_pct is not None and v2 > args.max_v2_pct:
        raise SystemExit(f"FAIL: v2 {v2:.2f}% is above maximum {args.max_v2_pct}%")
    print("PASS: report generated (weighted sampling is approximate)")


if __name__ == "__main__":
    main()
