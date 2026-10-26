# Visual examples

Jev reads images. The `jev` CLI sends text state only, so these scripts call
`/v1/systemone` directly with images as request `assets` and the
`TypeSafe-Danger-Zone-Images: true` header ([Images docs](https://docs.typesafe.ai/images.md)).
They reuse the TypeSafe key from `jev auth login` or `TYPESAFE_API_KEY`.

> Images and Box questions are **dreamer-ready** upstream: good for prototypes,
> the format and accuracy may change between Jev releases.

Ported from a local Clef-Flash proof of concept for jewellery catalogs: same
idea, Jev does the vision instead of a local model.

## Setup

```bash
pip install -e . pillow        # from the repo root
jev auth login                 # or export TYPESAFE_API_KEY=...
```

## `catalog_triage.py` — product photo → catalog record

One request per photo asks Jev typed questions in parallel:

| Question | Type | Used for |
| --- | --- | --- |
| `domain` | Choice: jewellery / apparel / both / other | routing |
| `category`, `metal_color`, `stone_presence` | Choice (speculative, "assume it is jewellery") | attributes, only read when domain is jewellery |
| `multiple_products`, `cropped`, `occluded`, `blurry`, `label_visible` | Noul | blocking QC checks |
| `background_clean` | Noul | warning only |

Jev is never asked "is this catalog ready?". Code decides:
`catalog_ready = domain == jewellery and no blocking check ≥ 0.5`.
Choice confidence below 0.6 sends the photo to human review.
Thresholds are starting points; tune them on your own catalog.

```bash
python examples/catalog_triage.py                  # all photos in examples/images
python examples/catalog_triage.py photo.jpg --json # full answers + usage
```

Sample run (jev-1.14, most attribute lines trimmed):

```
bangle_003.jpg     jewellery  READY                                    auto
                   category=bangle (0.91), metal_color=yellow_gold (0.88), stone_presence=multiple (0.35)
chain_001.jpg      jewellery  blocked: cropped                         auto
earrings_002.jpg   jewellery  blocked: blurry                          auto
necklace_002.jpg   jewellery  READY                                    auto
ring_001.jpg       jewellery  blocked: occluded                        auto
ring_002.jpg       jewellery  READY                                    auto
saree_001.jpg      apparel    blocked: not jewellery                   review: domain is apparel, not jewellery
watch_001.jpg      other      blocked: not jewellery                   review: domain is other, not jewellery
```

Against hand labels, 6 of 8 catalog decisions match. Misses: `bangle_003`
(a bridal set in a bowl with petals) passes because no check asks about props,
and `earrings_002` is a 347 px source, upscaled to the 280 px minimum, so Jev
calls it blurry. Add a "props or decorations around the product" Noul to catch
the first; reject undersized sources in code for the second.

## `auto_crop.py` — crop to the product

A Box question returns the product's edges as fractions of the image. A Box
always answers, even when the target is missing, so a Noul in the same request
checks the target is there before cropping. Edges get 5% padding.

```bash
python examples/auto_crop.py examples/images/ring_001.jpg --target "the gold ring"
# examples/images/ring_001.crop.jpg  present=0.91  box_confidence=0.93  edges={...}

python examples/auto_crop.py examples/images/watch_001.jpg --target "the gold ring"
# the gold ring not found (p=0.11); not cropping.
```

## Images

Openly licensed photos from Wikimedia Commons; source, license and author
for each are in [`images/SOURCES.csv`](images/SOURCES.csv).
