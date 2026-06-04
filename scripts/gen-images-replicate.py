#!/usr/bin/env python3
"""Generate Devpost explainer images via Replicate google/nano-banana-pro (Nano Banana Pro).

Reuses the prompts in gen-explainer-images.py. Used because the Gemini API free tier
hard-caps gemini-3-pro-image; Replicate is paid so there is no quota wall.

Usage:
  REPLICATE_API_TOKEN=... python3 scripts/gen-images-replicate.py [name ...]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from gen_explainer_images import IMAGES  # noqa: E402  (prompt definitions)

TOKEN = os.environ["REPLICATE_API_TOKEN"]
MODEL = "google/nano-banana-pro"
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "img")


def _post(url, payload, extra_headers=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def gen(name, spec):
    payload = {
        "input": {
            "prompt": spec["prompt"],
            "aspect_ratio": spec["ar"],
            "resolution": "2K",
            "output_format": "png",
        }
    }
    try:
        pred = _post(
            f"https://api.replicate.com/v1/models/{MODEL}/predictions",
            payload,
            {"Prefer": "wait"},
        )
    except urllib.error.HTTPError as e:
        print(f"  [{name}] create HTTP {e.code}: {e.read().decode()[:200]}")
        return False

    # Poll if not finished within the Prefer: wait window.
    for _ in range(40):
        status = pred.get("status")
        if status in ("succeeded", "failed", "canceled"):
            break
        time.sleep(3)
        pred = _get(pred["urls"]["get"])

    if pred.get("status") != "succeeded":
        print(f"  [{name}] {pred.get('status')}: {str(pred.get('error'))[:200]}")
        return False

    out = pred.get("output")
    img_url = out[0] if isinstance(out, list) else out
    if not img_url:
        print(f"  [{name}] no output url")
        return False

    path = os.path.join(OUT, f"{name}.png")
    urllib.request.urlretrieve(img_url, path)
    print(f"  [{name}] OK -> docs/img/{name}.png ({os.path.getsize(path)//1024} KB)")
    return True


targets = sys.argv[1:] or list(IMAGES)
ok = 0
for name in targets:
    if name not in IMAGES:
        print(f"  [{name}] unknown")
        continue
    if gen(name, IMAGES[name]):
        ok += 1
print(f"\n{ok}/{len(targets)} generated")
