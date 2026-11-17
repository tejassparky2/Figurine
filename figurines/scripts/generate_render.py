#!/usr/bin/env python3
"""Generate styled renders from BG-removed images using GPT-image-2 via fal.ai (parallel)."""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fal_client
import requests

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
MAX_WORKERS = 5

PROMPTS = {
    "funko": """make a cute funko pop like figurine of this person. Simple smile expression.
Present the figurine full-length on a pure white background. No base/platform/stand, no text, no logos, no names. use solid colored clothes no pattern or text. simple standing pose with arms folded. No sunglasses. No tika on forehead.""",
    "pixar": """Priority: the figurine must be immediately recognizable as the person in the source images
Transform the subject into a DreamWorks-style 3D figurine that clearly reads as a stylized animated character (not a real person). Use bold, playful proportions with an oversized head (~45–50% of the figure's height) and a compact, sturdy body with a cohesive DreamWorks silhouette. Ensure strong visual resemblance to the character(s) in the source image by faithfully matching key facial features, hairstyle, proportions, and overall likeness, while maintaining DreamWorks-style stylization. Preserve the subject's recognizable facial identity while exaggerating expressiveness: large animated eyes, thick brows, a simplified rounded nose, and a warm smile. Render smooth, clean 3D surfaces with flat colors—no pores, no lifelike skin texture. Keep facial planes soft, rounded, and lively. Model hair and any facial hair as solid stylized volumes with smooth contours and clear shape separation (no individual strands). Keep all geometry solid and 3D-printable. For sarees and dresses, use a single color in the clothing. If relevant, add a golden/silver border but no other pattern. Present the figurine full-length on a pure white background. No base/platform/stand, no text, no logos, no names. use solid colored clothes no pattern or text. simple standing pose""",
    "proportion_fix": """now try changing the proportions - head should be larger about 40% of image, and body smaller. DO NOT CHANGE ANYTHING ELSE""",
    "proportion_fix_pet": """now refine the proportions for a cute collectible pet figurine. Keep the head at a natural, realistic size relative to the body - do NOT enlarge the head or make it oversized. Maintain a sturdy, slightly chunky 3D-printable body in a stable standing pose. DO NOT CHANGE ANYTHING ELSE - keep the same colors, fur markings, collar, expression, and style.""",
    "fix_spectacles": """make the spectacles black in color and slightly thick, do not change anything else.""",
}


def generate_one(image_path: Path, out_path: Path, style: str, quality: str, extra: str = "") -> tuple[str, bool, str]:
    """Generate a single render. Returns (out_name, success, message)."""
    out_name = out_path.stem
    prompt = PROMPTS[style]
    if extra:
        prompt = f"{prompt}\n{extra}"
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            url = fal_client.upload_file(image_path)
            result = fal_client.subscribe(
                "openai/gpt-image-2/edit",
                arguments={
                    "prompt": prompt,
                    "image_urls": [url],
                    "quality": quality,
                    "output_format": "png",
                },
            )
            image_url = result["images"][0]["url"]
            resp = requests.get(image_url, timeout=120)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
            return (out_name, True, "ok")
        except Exception as e:
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
            return (out_name, False, str(e))
    return (out_name, False, "max attempts exceeded")


def main():
    parser = argparse.ArgumentParser(description="Generate styled renders using GPT-image-2 via fal.ai")
    parser.add_argument("input_dir", help="Directory containing BG-removed images")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: <input_dir>_renders)")
    parser.add_argument("-s", "--style", default="funko", choices=list(PROMPTS.keys()), help="Style prompt to use")
    parser.add_argument("-q", "--quality", default="medium", choices=["low", "medium", "high"], help="Quality tier (default: medium). Use 'high' only for the final approved pose — it costs ~3-4x more.")
    parser.add_argument("-n", "--limit", type=int, help="Only process first N images")
    parser.add_argument("-v", "--variants", type=int, default=1, help="Number of variants per image (default: 1)")
    parser.add_argument("-e", "--extra", default="", help="Extra text appended to the style prompt (e.g. clothing details)")
    parser.add_argument("-w", "--workers", type=int, default=MAX_WORKERS, help=f"Parallel workers (default: {MAX_WORKERS})")
    args = parser.parse_args()

    if not os.environ.get("FAL_KEY"):
        print("Error: FAL_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else input_dir.parent / f"{input_dir.name}_renders"
    output_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in SUPPORTED
    )

    if not images:
        print("No images found.", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        images = images[:args.limit]

    num_variants = args.variants

    # Build list of (input_path, output_path) jobs, skipping existing
    jobs: list[tuple[Path, Path]] = []
    for img in images:
        if num_variants == 1:
            out_path = output_dir / f"{img.stem}.png"
            if out_path.exists():
                print(f"  Skipping {img.name} (output exists)")
            else:
                jobs.append((img, out_path))
        else:
            for v in range(1, num_variants + 1):
                out_path = output_dir / f"{img.stem}_v{v}.png"
                if out_path.exists():
                    print(f"  Skipping {img.stem}_v{v}.png (output exists)")
                else:
                    jobs.append((img, out_path))

    if not jobs:
        print("Nothing to do — all outputs exist.")
        return

    label = f"{len(jobs)} render(s)"
    if num_variants > 1:
        label += f" ({len(images)} images × {num_variants} variants)"
    print(f"Generating {label} [{args.style}, {args.quality} quality, {args.workers} workers] → {output_dir}\n")

    success = 0
    failed = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(generate_one, img, out, args.style, args.quality, args.extra): out
            for img, out in jobs
        }
        for future in as_completed(futures):
            name, ok, msg = future.result()
            if ok:
                print(f"  ✓ {name}.png")
                success += 1
            else:
                print(f"  ✗ {name}: {msg}", file=sys.stderr)
                failed.append(name)

    print(f"\nDone: {success}/{len(jobs)} succeeded")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
