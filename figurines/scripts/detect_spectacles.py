#!/usr/bin/env python3
"""Detect which source images have spectacles using fal.ai VLM."""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fal_client

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}


def check_spectacles(image_path: Path) -> tuple[str, bool]:
    """Returns (stem, has_spectacles)."""
    url = fal_client.upload_file(image_path)
    result = fal_client.subscribe(
        "fal-ai/any-llm/vision",
        arguments={
            "prompt": "Does this person wear spectacles or glasses? Answer only 'yes' or 'no'.",
            "image_urls": [url],
            "model": "google/gemini-2.5-flash-lite",
            "max_tokens": 5,
        },
    )
    answer = result["output"].strip().lower()
    return (image_path.stem, answer.startswith("yes"))


def main():
    parser = argparse.ArgumentParser(description="Detect spectacles in source images")
    parser.add_argument("input_dir", help="Directory with source images (BG-removed)")
    parser.add_argument("-n", "--limit", type=int, help="Only check first N images")
    parser.add_argument("-o", "--output", help="Save results to JSON file")
    args = parser.parse_args()

    if not os.environ.get("FAL_KEY"):
        print("Error: FAL_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    input_dir = Path(args.input_dir)
    images = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED)

    if args.limit:
        images = images[:args.limit]

    print(f"Checking {len(images)} image(s) for spectacles...\n")

    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(check_spectacles, img): img for img in images}
        for future in as_completed(futures):
            name, has_specs = future.result()
            results[name] = has_specs
            icon = "👓" if has_specs else "  "
            print(f"  {icon} {name}: {'yes' if has_specs else 'no'}")

    with_specs = [n for n, v in results.items() if v]
    print(f"\n{len(with_specs)}/{len(results)} have spectacles")
    if with_specs:
        print(f"Names: {', '.join(sorted(with_specs))}")

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
