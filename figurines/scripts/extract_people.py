#!/usr/bin/env python3
"""Extract individual people from group photos using Moondream2 detection via fal.ai."""

import argparse
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fal_client
from PIL import Image

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
CONVERTIBLE = {".heic", ".heif"}
PDF_EXT = {".pdf"}
MAX_WORKERS = 3
PADDING_FRAC = 0.05  # 5% padding around each detected person


def convert_pdf(src: Path) -> Path:
    """Convert first page of PDF to PNG using pymupdf."""
    import pymupdf
    tmp = Path(tempfile.mktemp(suffix=".png"))
    doc = pymupdf.open(str(src))
    page = doc[0]
    pix = page.get_pixmap(dpi=300)
    pix.save(str(tmp))
    doc.close()
    return tmp


def convert_heic(src: Path) -> Path:
    """Convert HEIC/HEIF to PNG using macOS sips."""
    tmp = Path(tempfile.mktemp(suffix=".png"))
    subprocess.run(
        ["sips", "-s", "format", "png", str(src), "--out", str(tmp)],
        check=True, capture_output=True,
    )
    return tmp


OVERLAP_THRESHOLD = 0.3  # if >30% of a bbox overlaps with neighbor, trim it


def detect_people(image_url: str, object_name: str = "person") -> list[dict]:
    """Detect objects in an image using Moondream2. Returns list of normalized bboxes,
    sorted left-to-right with overlapping bboxes trimmed."""
    result = fal_client.subscribe(
        "fal-ai/moondream2/object-detection",
        arguments={
            "image_url": image_url,
            "object": object_name,
        },
    )
    # Sort left-to-right by x_min
    objects = sorted(result.get("objects", []), key=lambda o: o["x_min"])
    return resolve_overlaps(objects)


def resolve_overlaps(bboxes: list[dict]) -> list[dict]:
    """Trim horizontally overlapping bboxes so each person gets a clean crop.
    When two adjacent bboxes overlap, the wider one is trimmed at the midpoint
    of the overlap region."""
    if len(bboxes) <= 1:
        return bboxes

    resolved = [dict(b) for b in bboxes]  # deep copy

    for i in range(len(resolved) - 1):
        curr = resolved[i]
        nxt = resolved[i + 1]

        overlap = curr["x_max"] - nxt["x_min"]
        if overlap <= 0:
            continue

        curr_w = curr["x_max"] - curr["x_min"]
        nxt_w = nxt["x_max"] - nxt["x_min"]

        # Trim the wider bbox at the narrower bbox's near edge
        if curr_w > nxt_w:
            curr["x_max"] = nxt["x_min"]
        else:
            nxt["x_min"] = curr["x_max"]

    return resolved


MAX_ASPECT_RATIO = 2.8  # keep under GPT-image-2's 3:1 limit


def crop_person(img: Image.Image, bbox: dict, padding: float = PADDING_FRAC) -> Image.Image:
    """Crop a person from the image using normalized bbox coordinates with padding.
    Ensures the crop doesn't exceed MAX_ASPECT_RATIO by expanding the shorter side."""
    w, h = img.size
    pad_x = (bbox["x_max"] - bbox["x_min"]) * padding * w
    pad_y = (bbox["y_max"] - bbox["y_min"]) * padding * h

    x_min = max(0, int(bbox["x_min"] * w - pad_x))
    y_min = max(0, int(bbox["y_min"] * h - pad_y))
    x_max = min(w, int(bbox["x_max"] * w + pad_x))
    y_max = min(h, int(bbox["y_max"] * h + pad_y))

    crop_w = x_max - x_min
    crop_h = y_max - y_min

    # Expand the shorter side if aspect ratio exceeds limit
    if crop_h > crop_w * MAX_ASPECT_RATIO:
        needed_w = int(crop_h / MAX_ASPECT_RATIO)
        expand = needed_w - crop_w
        x_min = max(0, x_min - expand // 2)
        x_max = min(w, x_min + needed_w)
        x_min = max(0, x_max - needed_w)  # re-adjust if x_max hit the edge
    elif crop_w > crop_h * MAX_ASPECT_RATIO:
        needed_h = int(crop_w / MAX_ASPECT_RATIO)
        expand = needed_h - crop_h
        y_min = max(0, y_min - expand // 2)
        y_max = min(h, y_min + needed_h)
        y_min = max(0, y_max - needed_h)

    return img.crop((x_min, y_min, x_max, y_max))


def process_one(img_path: Path, output_dir: Path, padding: float = PADDING_FRAC,
                object_name: str = "person", base_name: str | None = None) -> tuple[str, int, str]:
    """Process a single group image. Returns (name, num_extracted, message).

    object_name: what to detect (e.g. "person", "dog").
    base_name: if set, crops are saved as <base_name>.png (single) or
               <base_name>_<i>.png (multiple); otherwise <stem>_person_<i>.png.
    """
    name = img_path.stem
    tmp_converted = None
    try:
        # Convert if needed
        ext = img_path.suffix.lower()
        if ext in PDF_EXT:
            process_path = convert_pdf(img_path)
            tmp_converted = process_path
        elif ext in CONVERTIBLE:
            process_path = convert_heic(img_path)
            tmp_converted = process_path
        else:
            process_path = img_path

        # Upload and detect
        url = fal_client.upload_file(process_path)
        people = detect_people(url, object_name=object_name)

        if not people:
            return (name, 0, f"no {object_name} detected")

        # Open image and crop each detection
        img = Image.open(process_path).convert("RGB")
        single = len(people) == 1
        for i, bbox in enumerate(people, 1):
            cropped = crop_person(img, bbox, padding=padding)
            if base_name:
                fname = f"{base_name}.png" if single else f"{base_name}_{i}.png"
            else:
                fname = f"{name}_person_{i}.png"
            out_path = output_dir / fname
            cropped.save(out_path)

        return (name, len(people), "ok")

    except Exception as e:
        return (name, 0, str(e))
    finally:
        if tmp_converted and tmp_converted.exists():
            tmp_converted.unlink()


def main():
    parser = argparse.ArgumentParser(description="Extract individual people from group photos using Moondream2 via fal.ai")
    parser.add_argument("input_dir", help="Directory containing group photos")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: <input_dir>_extracted)")
    parser.add_argument("-n", "--limit", type=int, help="Only process first N images")
    parser.add_argument("-w", "--workers", type=int, default=MAX_WORKERS, help=f"Parallel workers (default: {MAX_WORKERS})")
    parser.add_argument("--padding", type=float, default=PADDING_FRAC, help=f"Padding fraction around each person (default: {PADDING_FRAC})")
    parser.add_argument("--object", dest="object_name", default="person", help="Object to detect, e.g. 'person', 'dog' (default: person)")
    parser.add_argument("--name", dest="base_name", help="Base name for output crops (default: <stem>_person_<i>)")
    args = parser.parse_args()

    if not os.environ.get("FAL_KEY"):
        print("Error: FAL_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else input_dir.parent / f"{input_dir.name}_extracted"
    output_dir.mkdir(parents=True, exist_ok=True)

    padding = args.padding

    # Collect images
    images = []
    for p in sorted(input_dir.iterdir()):
        ext = p.suffix.lower()
        if ext in SUPPORTED or ext in CONVERTIBLE or ext in PDF_EXT:
            images.append(p)

    if not images:
        print("No images found.", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        images = images[:args.limit]

    # Skip images that already have extractions
    to_process = []
    for img in images:
        if args.base_name:
            existing = [p for p in [output_dir / f"{args.base_name}.png"] if p.exists()]
            existing += list(output_dir.glob(f"{args.base_name}_*.png"))
        else:
            existing = list(output_dir.glob(f"{img.stem}_person_*.png"))
        if existing:
            print(f"  Skipping {img.name} ({len(existing)} {args.object_name}(s) already extracted)")
        else:
            to_process.append(img)

    if not to_process:
        print("Nothing to do — all images already processed.")
        return

    print(f"Extracting people from {len(to_process)} image(s) [{args.workers} workers] → {output_dir}\n")

    total_people = 0
    failed = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_one, img, output_dir, padding, args.object_name, args.base_name): img
            for img in to_process
        }
        for future in as_completed(futures):
            name, count, msg = future.result()
            if count > 0:
                print(f"  ✓ {name}: {count} person(s)")
                total_people += count
            else:
                print(f"  ✗ {name}: {msg}", file=sys.stderr)
                failed.append(name)

    print(f"\nDone: {total_people} person(s) extracted from {len(to_process) - len(failed)} image(s)")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
