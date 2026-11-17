"""
Add watermark to images using the Everything3D logo.

Usage:
    python scripts/add_watermark.py [--level 1|2] <input_image> [output_image]
    python scripts/add_watermark.py [--level 1|2] <input_directory> [output_directory]

If no output path is given, watermarked files are saved with a '_watermarked' suffix.
Levels:
    1 (default) - Visible tiled watermark
    2 - Aggressive, dense, full-opacity watermark
"""

import sys
from pathlib import Path
from PIL import Image


LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo_white.png"

WATERMARK_LEVELS = {
    1: {"scale": 0.18, "opacity": 180, "angle": -30, "spacing": 10},
    2: {"scale": 0.25, "opacity": 255, "angle": -30, "spacing": -10},
}


def add_watermark(image_path: Path, output_path: Path, level: int = 1) -> None:
    cfg = WATERMARK_LEVELS[level]
    base = Image.open(image_path).convert("RGBA")
    logo = Image.open(LOGO_PATH).convert("RGBA")

    # Scale logo relative to image width
    logo_width = int(base.width * cfg["scale"])
    logo_height = int(logo.height * (logo_width / logo.width))
    logo = logo.resize((logo_width, logo_height), Image.LANCZOS)

    # Apply opacity
    r, g, b, a = logo.split()
    a = a.point(lambda p: min(p, cfg["opacity"]))
    logo = Image.merge("RGBA", (r, g, b, a))

    # Rotate the logo
    logo = logo.rotate(cfg["angle"], expand=True, resample=Image.BICUBIC)

    # Create a tiled watermark overlay the size of the image
    tile_w = logo.width + cfg["spacing"]
    tile_h = logo.height + cfg["spacing"]
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))

    for y in range(-tile_h, base.height + tile_h, tile_h):
        for x in range(-tile_w, base.width + tile_w, tile_w):
            overlay.paste(logo, (x, y), logo)

    # Composite and save
    base = Image.alpha_composite(base, overlay)
    base = base.convert("RGB")
    base.save(output_path)
    print(f"  {image_path.name} -> {output_path.name}")


def default_output_path(input_path: Path) -> Path:
    return input_path.with_stem(input_path.stem + "_watermarked")


def main() -> None:
    args = sys.argv[1:]
    level = 1

    if "--level" in args:
        idx = args.index("--level")
        level = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]
        if level not in WATERMARK_LEVELS:
            print(f"Error: level must be one of {list(WATERMARK_LEVELS.keys())}")
            sys.exit(1)

    if len(args) < 1:
        print(__doc__.strip())
        sys.exit(1)

    input_path = Path(args[0])
    output_arg = Path(args[1]) if len(args) > 1 else None

    if not input_path.exists():
        print(f"Error: {input_path} does not exist")
        sys.exit(1)

    if not LOGO_PATH.exists():
        print(f"Error: Logo not found at {LOGO_PATH}")
        print("Place your logo at assets/logo_white.png")
        sys.exit(1)

    if input_path.is_file():
        out = output_arg or default_output_path(input_path)
        add_watermark(input_path, out, level)
    elif input_path.is_dir():
        out_dir = output_arg or input_path
        if output_arg:
            out_dir.mkdir(parents=True, exist_ok=True)
        extensions = {".jpg", ".jpeg", ".png", ".webp"}
        files = [f for f in input_path.iterdir() if f.suffix.lower() in extensions]
        if not files:
            print(f"No images found in {input_path}")
            sys.exit(1)
        print(f"Watermarking {len(files)} images (level {level})...")
        for f in sorted(files):
            if "_watermarked" in f.stem:
                continue
            if output_arg:
                out = out_dir / f.name
            else:
                out = default_output_path(f)
            add_watermark(f, out, level)
        print("Done.")


if __name__ == "__main__":
    main()
