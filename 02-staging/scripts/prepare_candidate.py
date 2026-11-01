#!/usr/bin/env python3
"""Generate a v2 release build context without modifying demo-app sources.

A new webcam product models a real feature change. --broken also introduces
a controlled checkout regression *only* in the generated candidate build.
The bad image is never deployed to real production by this lab.
"""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "demo-app"
BUILD_ROOT = ROOT / "02-staging" / ".build"

def prepare(variant: str) -> Path:
    target = BUILD_ROOT / f"candidate-{variant}"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in ("Dockerfile", ".dockerignore"):
        shutil.copy2(SOURCE / name, target / name)
    for name in ("app", "scripts"):
        shutil.copytree(SOURCE / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    catalog_file = target / "app" / "catalog.py"
    catalog = catalog_file.read_text(encoding="utf-8")
    anchor = '    "pad": {"name": "Mouse Pad", "price_cents": 1200},'
    if catalog.count(anchor) != 1:
        raise RuntimeError("Catalog source format changed; update the candidate generator")
    catalog = catalog.replace(anchor, anchor + '\n    "webcam": {"name": "HD Webcam", "price_cents": 3800},')
    catalog_file.write_text(catalog, encoding="utf-8")

    if variant == "broken":
        checkout_file = target / "app" / "checkout.py"
        checkout = checkout_file.read_text(encoding="utf-8")
        good = "subtotal_cents += line_total_cents"
        bad = "subtotal_cents += unit_price_cents  # LAB BUG: ignores quantity"
        if checkout.count(good) != 1:
            raise RuntimeError("Checkout source format changed; update the regression fixture")
        checkout_file.write_text(checkout.replace(good, bad), encoding="utf-8")

    print(f"Generated {variant} candidate: {target}")
    print(f"Build with: docker build -t safe-demo:candidate-{variant} {target}")
    return target

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True, choices=("good", "broken"))
    args = parser.parse_args()
    prepare(args.variant)
