"""Crop a product photo to the product with a Jev Box question.

A Box answer is always a box, even when the target is absent, so a Noul in
the same request checks the product is there before code crops.

    python examples/auto_crop.py examples/images/ring_002.jpg
    python examples/auto_crop.py photo.jpg --target "the gold ring" --out ring.jpg
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps

from jev_images import ask

REF = "img-8b2d4f-photo"
PAD = 0.05            # lean: fixed padding; tune per catalog
MIN_PRESENT = 0.5     # Noul threshold for "target is in the photo"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image", type=Path)
    ap.add_argument("--target", default="the main product", help='what to find, e.g. "the gold ring"')
    ap.add_argument("--out", type=Path, help="defaults to <image>.crop.jpg next to the input")
    args = ap.parse_args()

    resp = ask(
        {"photo": REF},
        {
            "present": {"type": "noul", "instructions": f"Is {args.target} visible in `photo`?"},
            "box": {"type": "box", "instructions": f"{args.target} in `photo`"},
        },
        {REF: args.image},
    )
    present = resp["answers"]["present"]["noul"]
    box = resp["answers"]["box"]
    if present < MIN_PRESENT:
        raise SystemExit(f"{args.target} not found (p={present:.2f}); not cropping.")

    edges = box["box"]
    left, top = max(0.0, edges["left"] - PAD), max(0.0, edges["top"] - PAD)
    right, bottom = min(1.0, edges["right"] + PAD), min(1.0, edges["bottom"] + PAD)

    with Image.open(args.image) as original:
        img = ImageOps.exif_transpose(original).convert("RGB")
    w, h = img.size
    out = args.out or args.image.with_suffix(".crop.jpg")
    img.crop((round(left * w), round(top * h), round(right * w), round(bottom * h))).save(out, quality=92)
    print(f"{out}  present={present:.2f}  box_confidence={box['confidence']:.2f}  edges={edges}")


if __name__ == "__main__":
    main()
