"""Send Jev a System One request with images attached.

The `jev` CLI sends text state only. Jev itself accepts images as request
`assets` behind the `TypeSafe-Danger-Zone-Images: true` header, so these
examples call the API directly and reuse jev-studio's stored credentials.
Images are "dreamer-ready" upstream: https://docs.typesafe.ai/images.md
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

from jev_studio.cli.credentials import with_stored_credentials
from jev_studio.cli.provider import USER_AGENT, _http_post, _typesafe_base

MIN_SIDE, MAX_SIDE = 280, 1568


def encode(path: Path) -> str:
    """Upright, 280..1568 px per side, baseline JPEG, base64 (API limits)."""
    with Image.open(path) as original:
        img = ImageOps.exif_transpose(original).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    if min(img.size) < MIN_SIDE:
        scale = MIN_SIDE / min(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def ask(state: dict, questions: dict, images: dict[str, Path], model: str = "jev-latest") -> dict:
    """POST /v1/systemone. `images` maps a reference string (used in state or
    instructions) to an image file. Returns the raw response body."""
    env = with_stored_credentials(dict(os.environ))
    key = env.get("TYPESAFE_API_KEY")
    if not key:
        sys.exit("Set TYPESAFE_API_KEY or run `jev auth login`. Images need TypeSafe direct.")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "TypeSafe-Danger-Zone-Images": "true",
    }
    body = {
        "model": model,
        "state": state,
        "questions": questions,
        "assets": {
            ref: {"type": "image", "format": "jpg", "data_base64": encode(path)}
            for ref, path in images.items()
        },
    }
    status, resp = _http_post(_typesafe_base(env) + "/v1/systemone", headers, body, 120_000)
    if status >= 400:
        sys.exit(f"TypeSafe API {status}: {json.dumps(resp)[:300]}")
    return resp
