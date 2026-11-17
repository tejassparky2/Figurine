#!/usr/bin/env python3
"""Remove backgrounds from images using fal.ai BiRefNet API (parallel)."""

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
CONVERTIBLE = {".heic", ".heif"}  # converted via sips on macOS
PDF_EXT = {".pdf"}
MAX_WORKERS = 5

API_KEY_ENV = "FAL_KEY"


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


def process_one(img: Path, output_dir: Path) -> tuple[str, bool, str]:
    """Process a single image: convert if needed, remove BG, download. Returns (name, success, message)."""
    name = img.stem
    tmp_converted = None
    try:
        # Convert if needed
        if img.suffix.lower() in PDF_EXT:
            process_path = convert_pdf(img)
            tmp_converted = process_path
        elif img.suffix.lower() in CONVERTIBLE:
            process_path = convert_heic(img)
            tmp_converted = process_path
        else:
            process_path = img

        # Upload and remove BG
        url = fal_client.upload_file(process_path)
        result = fal_client.subscribe(
            "fal-ai/birefnet/v2",
            arguments={
                "image_url": url,
                "model": "Portrait",
                "operating_resolution": "1024x1024",
                "output_format": "png",
            },
        )
        image_url = result["image"]["url"]

        # Download, white BG, crop
        import requests
        from io import BytesIO

        resp = requests.get(image_url, timeout=120)
        resp.raise_for_status()

        rgba = Image.open(BytesIO(resp.content)).convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        white.paste(rgba, mask=rgba.split()[3])
        rgb = white.convert("RGB")

        bbox = rgba.split()[3].getbbox()
        if bbox:
            rgb = rgb.crop(bbox)

        # Pad to square (center the image on white background)
        w_img, h_img = rgb.size
        if w_img != h_img:
            side = max(w_img, h_img)
            square = Image.new("RGB", (side, side), (255, 255, 255))
            square.paste(rgb, ((side - w_img) // 2, (side - h_img) // 2))
            rgb = square

        out_path = output_dir / f"{name}.png"
        rgb.save(out_path)
        return (name, True, "ok")

    except Exception as e:
        return (name, False, str(e))
    finally:
        if tmp_converted and tmp_converted.exists():
            tmp_converted.unlink()


def main():
    parser = argparse.ArgumentParser(description="Remove backgrounds using fal.ai BiRefNet (parallel)")
    parser.add_argument("input_dir", help="Directory containing input images")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: <input_dir>_nobg)")
    parser.add_argument("-n", "--limit", type=int, help="Only process first N images")
    parser.add_argument("-w", "--workers", type=int, default=MAX_WORKERS, help=f"Parallel workers (default: {MAX_WORKERS})")
    args = parser.parse_args()

    if not os.environ.get(API_KEY_ENV):
        print(f"Error: {API_KEY_ENV} environment variable not set", file=sys.stderr)
        sys.exit(1)

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else input_dir.parent / f"{input_dir.name}_nobg"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect images
    images = []
    skipped_formats = []
    for p in sorted(input_dir.iterdir()):
        ext = p.suffix.lower()
        if ext in SUPPORTED or ext in CONVERTIBLE or ext in PDF_EXT:
            images.append(p)
        elif p.is_file():
            skipped_formats.append(p.name)

    if skipped_formats:
        print(f"Skipping unsupported: {', '.join(skipped_formats)}")

    if not images:
        print("No images found.", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        images = images[:args.limit]

    # Skip existing
    to_process = []
    for img in images:
        out_path = output_dir / f"{img.stem}.png"
        if out_path.exists():
            print(f"  Skipping {img.name} (output exists)")
        else:
            to_process.append(img)

    if not to_process:
        print("Nothing to do — all outputs exist.")
        return

    print(f"Processing {len(to_process)} image(s) [{args.workers} workers] → {output_dir}\n")

    success = 0
    failed = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_one, img, output_dir): img
            for img in to_process
        }
        for future in as_completed(futures):
            name, ok, msg = future.result()
            if ok:
                print(f"  ✓ {name}.png")
                success += 1
            else:
                print(f"  ✗ {name}: {msg}", file=sys.stderr)
                failed.append(name)

    print(f"\nDone: {success}/{len(to_process)} succeeded")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
