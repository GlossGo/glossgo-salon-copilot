#!/usr/bin/env python3
"""Generate Devpost explainer images with Nano Banana Pro (gemini-3-pro-image-preview).

Usage:
  GEMINI_API_KEY=... python3 scripts/gen-explainer-images.py [name ...]
If names are given, only those images are generated; otherwise all.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

KEY = os.environ.get("GEMINI_API_KEY", "")  # lazy: empty is fine when only importing IMAGES
MODEL = "gemini-3-pro-image-preview"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "img")

BRAND = (
    "Brand palette: glossgo magenta-to-violet gradient (#a23db4 to #6d28d9) with "
    "warm cream and soft pink accents. Clean modern flat-illustration style, premium "
    "SaaS marketing look, generous whitespace, rounded corners, subtle soft shadows. "
    "Turkish beauty-salon context. No watermark. Crisp, legible."
)

IMAGES = {
    "hero": {
        "ar": "16:9",
        "prompt": (
            "Hero cover illustration for an AI product called 'glossgo Salon Co-Pilot'. "
            "Center-left: a confident woman hair stylist coloring a happy client's hair "
            "in a bright modern Turkish salon. Floating around them, three translucent "
            "glassy UI cards showing: a green WhatsApp message bubble, a 5-star review with "
            "a reply, and a calendar with one highlighted open slot. A subtle friendly robot "
            "/ AI spark motif connects the cards, suggesting an assistant working in the "
            "background. Large clean title text at top reading exactly 'glossgo Salon Co-Pilot' "
            "(glossgo in lowercase). Smaller subtitle below reading exactly 'AI agents that run "
            "the salon while you work'. " + BRAND
        ),
    },
    "three-agents": {
        "ar": "16:9",
        "prompt": (
            "A clean infographic with three side-by-side rounded cards, equal size, on a soft "
            "cream background. Card 1 icon: an empty salon chair turning into a filled chair with "
            "a WhatsApp send arrow; title text exactly 'No-Show Recovery'; one line beneath exactly "
            "'fills cancelled slots from the waitlist'. Card 2 icon: a 5-star rating with a speech "
            "reply bubble; title text exactly 'Review Responder'; one line beneath exactly "
            "'drafts tone-matched replies'. Card 3 icon: a weekly calendar with one highlighted gap "
            "and a small promo tag; title text exactly 'Calendar Optimizer'; one line beneath exactly "
            "'markets the off-peak gaps'. A small header above the three cards reads exactly "
            "'Three specialist AI agents, one orchestrator'. " + BRAND
        ),
    },
    "how-it-works": {
        "ar": "16:9",
        "prompt": (
            "A horizontal left-to-right pipeline diagram, 5 simple stages connected by arrows, "
            "flat illustration. Stage 1: a salon event icon (a cancelled booking + a new review) "
            "labeled exactly 'Salon event'. Stage 2: a glowing AI brain chip labeled exactly "
            "'Gemini orchestrator routes it'. Stage 3: three small agent avatars labeled exactly "
            "'Specialist agent acts'. Stage 4: a smartphone showing an approval list with green "
            "approve buttons labeled exactly 'Owner approves in one tap'. Stage 5: a paper-plane "
            "send icon labeled exactly 'Message goes out'. Numbers 1 to 5 above each stage. "
            "Clean, lots of whitespace. " + BRAND
        ),
    },
    "shadow-mode": {
        "ar": "4:3",
        "prompt": (
            "A smartphone mockup held in a hand, screen showing an AI 'owner approval queue' app. "
            "The screen lists two draft cards: one is a Turkish WhatsApp message preview to a "
            "customer about an opened appointment slot, the other is a draft reply to a 2-star review. "
            "Each card has a green 'Approve' button and a light 'Reject' button. A small lock-shield "
            "badge in the corner. Bold caption text at the bottom reading exactly "
            "'Shadow mode: nothing sends without owner approval'. " + BRAND
        ),
    },
}


def _retry_delay(err_body):
    try:
        for d in json.loads(err_body).get("error", {}).get("details", []):
            if d.get("@type", "").endswith("RetryInfo"):
                return int(str(d.get("retryDelay", "45s")).rstrip("s")) + 5
    except Exception:
        pass
    return 50


def gen(name, spec, tries=5):
    body = {
        "contents": [{"parts": [{"text": spec["prompt"]}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": spec["ar"]},
        },
    }
    data = None
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(
            URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            eb = e.read().decode()
            if e.code == 429 and attempt < tries:
                wait = _retry_delay(eb)
                print(f"  [{name}] 429 (attempt {attempt}/{tries}), waiting {wait}s")
                time.sleep(wait)
                continue
            print(f"  [{name}] HTTP {e.code}: {eb[:200]}")
            return False
    if data is None:
        return False
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            path = os.path.join(OUT, f"{name}.png")
            with open(path, "wb") as f:
                f.write(base64.b64decode(inline["data"]))
            print(f"  [{name}] OK -> docs/img/{name}.png ({os.path.getsize(path)//1024} KB)")
            return True
    print(f"  [{name}] no image in response: {json.dumps(data)[:300]}")
    return False


targets = sys.argv[1:] or list(IMAGES)
ok = 0
for i, name in enumerate(targets):
    if name not in IMAGES:
        print(f"  [{name}] unknown")
        continue
    if i:
        time.sleep(50)  # pace under free-tier per-minute request limit
    if gen(name, IMAGES[name]):
        ok += 1
print(f"\n{ok}/{len(targets)} generated")
