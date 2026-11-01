#!/usr/bin/env python3
"""Check the actual HTTP behavior of an isolated deployment (no dependencies).

Usage:
  python3 02-staging/scripts/validate_environment.py \
    --url http://127.0.0.1:18081 --version v2 --catalog candidate
"""

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

def request_json(url: str, payload=None):
    encoded = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=encoded,
                      headers={"Content-Type": "application/json"} if encoded else {})
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        with exc:
            return exc.code, json.load(exc)

def validate(base_url: str, version: str, catalog_kind: str) -> None:
    base_url = base_url.rstrip("/")
    for attempt in range(20):
        try:
            status, health = request_json(base_url + "/health")
            if status == 200 and health.get("status") == "ok":
                break
        except (URLError, TimeoutError, ConnectionError, OSError, ValueError):
            pass
        time.sleep(0.25)
    else:
        raise AssertionError(f"{base_url}: HTTP health check not ready")
    assert health.get("version") == version, (f"Expected version {version}, "
                                               f"got {health.get('version')}")
    print(f"PASS {base_url}: HTTP healthy; release={version}")

    status, data = request_json(base_url + "/api/products")
    assert status == 200, f"Catalog returned {status}"
    skus = {product["sku"] for product in data["products"]}
    assert {"keyboard", "mouse", "pad"} <= skus, "Missing base catalog products"
    assert ("webcam" in skus) == (catalog_kind == "candidate"), \
        f"Unexpected catalog for {catalog_kind}: {skus}"
    print(f"PASS {base_url}: catalog type={catalog_kind}")

    status, result = request_json(base_url + "/api/checkout", {
        "items": [{"sku": "keyboard", "quantity": 2},
                  {"sku": "mouse", "quantity": 1}]
    })
    assert status == 200, f"Checkout returned HTTP {status}"
    expected = {"subtotal_cents": 11500, "shipping_cents": 0, "total_cents": 11500}
    actual = {key: result.get(key) for key in expected}
    assert actual == expected, f"Checkout mismatch: expected {expected}; got {actual}"
    print(f"PASS {base_url}: checkout amounts correct")

    status, result = request_json(base_url + "/api/checkout", {
        "items": [{"sku": "mouse", "quantity": 0}]
    })
    assert status == 400 and "error" in result, "Invalid order was not rejected"
    print(f"PASS {base_url}: invalid order rejected")
    print("ENVIRONMENT VALIDATION: ALL PASSED")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--catalog", required=True, choices=("stable", "candidate"))
    args = parser.parse_args()
    try:
        validate(args.url, args.version, args.catalog)
    except (AssertionError, URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
        print(f"ENVIRONMENT VALIDATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
