"""Jewellery catalog triage from product photos, one Jev request per image.

Jev answers narrow typed questions (domain, category, attributes, visual QC
checks). Code decides catalog readiness and when a human must review.
Jev is never asked "is this catalog ready?".

    python examples/catalog_triage.py                     # every image in examples/images
    python examples/catalog_triage.py photo.jpg --json    # one image, full JSON
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jev_images import ask

HERE = Path(__file__).parent
REF = "img-5c1e9a-product"  # unique so it can't match inside other words

# lean: thresholds copied from jewellery-vision-poc's policy.yaml; re-tune on real catalog data.
NOUL_TRUE = 0.5
AUTO_ACCEPT = 0.6
MANUAL_REVIEW = 0.4


def choice(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def noul(instructions: str) -> dict:
    return {"type": "noul", "instructions": instructions}


IF_JEWELLERY = "Assume the main product in `photo` is jewellery. "

QUESTIONS = {
    "domain": choice(
        "Which product domain does the main product in `photo` belong to?",
        {
            "jewellery": "Jewellery: rings, necklaces, earrings, bangles, bracelets, pendants, chains, anklets, nose pins.",
            "apparel": "Clothing: shirts, dresses, trousers, kurtas, sarees, jackets.",
            "both": "Apparel and jewellery are both presented as products, e.g. a styled outfit with featured jewellery.",
            "other": "Neither jewellery nor apparel, e.g. shoes, bags, watches, food, scenery.",
        },
    ),
    # Speculative: asked in the same request, used only when domain == jewellery.
    "category": choice(
        IF_JEWELLERY + "What type of jewellery item is it? If several pieces are presented as one matching set, answer jewellery_set.",
        {
            "ring": "A finger ring, including bands, solitaires and cocktail rings.",
            "necklace": "A necklace, including chokers, haars and beaded strands.",
            "earrings": "Ear jewellery: studs, hoops, drops or jhumkas, single or pair.",
            "bangle": "A rigid circular wrist ornament without a clasp, including kadas.",
            "bracelet": "A flexible, linked wrist ornament, usually with a clasp.",
            "pendant": "A hanging ornament shown as the clear focus, chain secondary or absent.",
            "chain": "A plain neck chain without a prominent pendant.",
            "anklet": "An ankle ornament such as payal.",
            "brooch": "A decorative pin attached to clothing.",
            "nose_pin": "A nose stud, nose pin or nath.",
            "mangalsutra": "A necklace with black beads and usually a small gold pendant.",
            "jewellery_set": "Several matching pieces presented together, e.g. necklace with earrings.",
            "other": "Jewellery that fits none of the above, e.g. maang tikka.",
        },
    ),
    "metal_color": choice(
        IF_JEWELLERY + "What is its dominant metal colour as it appears in the photo?",
        {
            "yellow_gold": "Yellow gold coloured metal.",
            "white_gold": "Bright white or grey metal, white gold or platinum look.",
            "rose_gold": "Pinkish rose gold coloured metal.",
            "silver": "Silver-coloured metal, including oxidised silver.",
            "mixed": "Two or more clearly different metal colours.",
            "unknown": "Metal colour cannot be judged, or no metal is visible.",
        },
    ),
    "stone_presence": choice(
        IF_JEWELLERY + "How many stones, gems or pearls are set in it?",
        {
            "none": "No stones, gems or pearls are visible.",
            "single": "Exactly one prominent stone; small side accents don't count.",
            "multiple": "Two or more stones, gems or pearls.",
            "unknown": "Cannot be judged from the photo.",
        },
    ),
    # Raw visual checks. Catalog readiness is decided from these in code below.
    "multiple_products": noul(
        "Does `photo` show more than one separate product (not counting the two earrings of a pair, or the pieces of one matching set)?"
    ),
    "cropped": noul("Is any part of the main product in `photo` cut off by the edge of the image?"),
    "occluded": noul(
        "Is the main product in `photo` partly hidden behind another object, a hand, hair, packaging or a text overlay?"
    ),
    "blurry": noul("Is the product in `photo` out of focus, motion-blurred or too low-resolution to see its details?"),
    "label_visible": noul(
        "Is there a visible barcode, price tag, SKU sticker, watermark or other unwanted label in `photo`?"
    ),
    "background_clean": noul("Is the background of `photo` plain and uncluttered, like a white or solid studio backdrop?"),
}

BLOCKING = ("multiple_products", "cropped", "occluded", "blurry", "label_visible")
ATTRIBUTES = ("category", "metal_color", "stone_presence")


def status(confidence: float) -> str:
    if confidence >= AUTO_ACCEPT:
        return "auto_accept"
    if confidence >= MANUAL_REVIEW:
        return "review"
    return "low_confidence"


def triage(path: Path) -> dict:
    resp = ask({"task": "Product photo for a jewellery and fashion e-commerce catalog.", "photo": REF}, QUESTIONS, {REF: path})
    a = resp["answers"]
    domain = a["domain"]["choice"]
    reasons = [] if domain == "jewellery" else [f"domain is {domain}, not jewellery"]

    attributes = {}
    if domain == "jewellery":
        for name in ATTRIBUTES:
            attributes[name] = {"value": a[name]["choice"], "confidence": round(a[name]["confidence"], 2)}
        if status(a["category"]["confidence"]) != "auto_accept":
            reasons.append(f"category {status(a['category']['confidence'])}")
    if status(a["domain"]["confidence"]) != "auto_accept":
        reasons.append(f"domain {status(a['domain']['confidence'])}")

    checks = {name: round(a[name]["noul"], 2) for name in (*BLOCKING, "background_clean")}
    failed = [name for name in BLOCKING if checks[name] >= NOUL_TRUE]
    return {
        "image": path.name,
        "domain": domain,
        "attributes": attributes,
        "catalog_ready": domain == "jewellery" and not failed,
        "failed_checks": failed,
        "warnings": [] if checks["background_clean"] >= NOUL_TRUE else ["background_not_clean"],
        "review_required": bool(reasons),
        "review_reasons": reasons,
        "checks": checks,
        "model": resp.get("model"),
        "usage": resp.get("usage"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("images", nargs="*", type=Path, help="defaults to examples/images/*.jpg")
    ap.add_argument("--json", action="store_true", help="print full results as JSON")
    args = ap.parse_args()

    results = [triage(p) for p in args.images or sorted((HERE / "images").glob("*.jpg"))]
    if args.json:
        print(json.dumps(results, indent=2))
        return
    for r in results:
        attrs = ", ".join(f"{k}={v['value']} ({v['confidence']})" for k, v in r["attributes"].items())
        if r["domain"] != "jewellery":
            ready = "blocked: not jewellery"
        else:
            ready = "READY" if r["catalog_ready"] else "blocked: " + ", ".join(r["failed_checks"])
        review = "review: " + "; ".join(r["review_reasons"]) if r["review_required"] else "auto"
        print(f"{r['image']:<18} {r['domain']:<10} {ready:<40} {review}")
        if attrs:
            print(f"{'':<18} {attrs}")


if __name__ == "__main__":
    main()
