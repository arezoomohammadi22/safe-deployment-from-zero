#!/usr/bin/env python3
"""Confirm staging regression while the production simulation stays correct."""
import sys
from urllib.error import URLError
from validate_environment import request_json, validate

def main() -> None:
    prod = "http://127.0.0.1:18080"
    staging = "http://127.0.0.1:18081"
    validate(prod, "v1", "stable")
    status, health = request_json(staging + "/health")
    assert status == 200 and health.get("version") == "v2", "Staging not running"
    status, catalog = request_json(staging + "/api/products")
    assert status == 200 and any(p["sku"] == "webcam" for p in catalog["products"]), \
        "Staging candidate not running"
    status, order = request_json(staging + "/api/checkout", {
        "items": [{"sku": "keyboard", "quantity": 2},
                  {"sku": "mouse", "quantity": 1}]
    })
    assert status == 200, "Staging checkout not reachable"
    assert order.get("subtotal_cents") != 11500, "Expected bug not reproduced in staging"
    print("EXPECTED REGRESSION DETECTED: staging checkout subtotal =", order.get("subtotal_cents"))
    print("PASS: local production remained healthy, unchanged and isolated")

if __name__ == "__main__":
    try:
        main()
    except (AssertionError, URLError, OSError, ValueError, KeyError) as exc:
        print("ISOLATION CHECK FAILED:", exc, file=sys.stderr)
        sys.exit(1)
