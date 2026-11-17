#!/usr/bin/env python3
"""Generate a before/after PDF for client review. Supports multiple variants per person."""

import argparse
import sys
from pathlib import Path

import pymupdf
from PIL import Image

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMG_PX = 800  # max dimension for images in PDF

# Page layout (A4 landscape)
PAGE_W, PAGE_H = 842, 595  # A4 landscape in points
MARGIN = 40
NAME_H = 30
GAP = 15  # gap between columns


def name_from_filename(filename: str) -> str:
    """Convert filename to display name: 'Amit sawant' -> 'Amit Sawant'.
    Also strips variant suffixes like '_v1', '_v2'."""
    import re
    clean = re.sub(r"_v\d+$", "", filename)
    return clean.replace("_", " ").replace("-", " ").title().strip()


def fit_image_rect(img_w, img_h, box_w, box_h):
    """Return (w, h) that fits image proportionally in box."""
    scale = min(box_w / img_w, box_h / img_h)
    return int(img_w * scale), int(img_h * scale)


def compress_image(path: Path) -> bytes:
    """Resize and compress image to JPEG bytes for PDF embedding."""
    from io import BytesIO
    with Image.open(path) as img:
        img = img.convert("RGB")
        if max(img.size) > MAX_IMG_PX:
            img.thumbnail((MAX_IMG_PX, MAX_IMG_PX), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()


def insert_image_centered(page, path: Path, x_start, y_start, col_w, area_h):
    """Insert an image centered in a column area. Returns True on success."""
    try:
        img_bytes = compress_image(path)
        with Image.open(path) as img:
            iw, ih = img.size
        fw, fh = fit_image_rect(iw, ih, col_w, area_h)
        x_off = x_start + (col_w - fw) / 2
        y_off = y_start + (area_h - fh) / 2
        page.insert_image(
            pymupdf.Rect(x_off, y_off, x_off + fw, y_off + fh),
            stream=img_bytes,
        )
        return True
    except Exception as e:
        print(f"  Warning: could not insert image {path.name}: {e}")
        return False


def collect_render_groups(render_dir: Path) -> dict[str, list[Path]]:
    """Collect render files grouped by base name (without _v1/_v2 suffix).
    Returns {base_stem: [path1, path2, ...]} sorted by variant number."""
    import re
    groups: dict[str, list[Path]] = {}
    for p in sorted(render_dir.iterdir()):
        if p.suffix.lower() not in SUPPORTED:
            continue
        # Check for variant suffix
        m = re.match(r"^(.+?)_v(\d+)$", p.stem)
        if m:
            base = m.group(1)
        else:
            base = p.stem
        groups.setdefault(base, []).append(p)
    # Sort each group by name (ensures v1, v2, v3 order)
    for base in groups:
        groups[base].sort()
    return groups


def main():
    parser = argparse.ArgumentParser(description="Generate before/after review PDF (supports variants)")
    parser.add_argument("before_dir", help="Directory with before images (BG-removed)")
    parser.add_argument("render_dir", help="Directory with rendered images")
    parser.add_argument("-o", "--output", default="review.pdf", help="Output PDF path")
    parser.add_argument("--title", default="Figurine Renders - Review", help="PDF title")
    parser.add_argument("--source-dir", help="Directory with original source photos (shown on title page)")
    args = parser.parse_args()

    before_dir = Path(args.before_dir)
    render_dir = Path(args.render_dir)

    if not before_dir.is_dir() or not render_dir.is_dir():
        print("Error: both directories must exist", file=sys.stderr)
        sys.exit(1)

    # Collect befores and render groups
    befores = {p.stem: p for p in before_dir.iterdir() if p.suffix.lower() in SUPPORTED}
    render_groups = collect_render_groups(render_dir)

    # Match by stem
    common = sorted(set(render_groups) & set(befores))

    if not common:
        print("No matching before/render pairs found.", file=sys.stderr)
        sys.exit(1)

    max_variants = max(len(render_groups[s]) for s in common)
    print(f"Creating PDF with {len(common)} people, up to {max_variants} variant(s) each...")

    doc = pymupdf.open()

    # Collect source images if provided
    source_images = []
    if args.source_dir:
        source_dir = Path(args.source_dir)
        if source_dir.is_dir():
            source_images = sorted(
                p for p in source_dir.iterdir()
                if p.suffix.lower() in SUPPORTED | {".heic", ".heif"}
            )

    # Title page
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text(
        (MARGIN, MARGIN + 30),
        args.title,
        fontsize=28,
        fontname="helv",
        color=(0.1, 0.1, 0.1),
    )
    page.insert_text(
        (MARGIN, MARGIN + 55),
        f"{len(common)} figurines",
        fontsize=16,
        fontname="helv",
        color=(0.4, 0.4, 0.4),
    )

    # Add source photos to title page
    if source_images:
        src_top = MARGIN + 80
        src_area_h = PAGE_H - src_top - MARGIN
        num_src = len(source_images)
        src_col_w = (PAGE_W - 2 * MARGIN - GAP * (num_src - 1)) / num_src
        for si, src_path in enumerate(source_images):
            x = MARGIN + si * (src_col_w + GAP)
            insert_image_centered(page, src_path, x, src_top, src_col_w, src_area_h)

    for stem in common:
        before_path = befores[stem]
        variants = render_groups[stem]
        num_variants = len(variants)
        display_name = name_from_filename(stem)

        # Number of columns: 1 before + N variants
        num_cols = 1 + num_variants
        col_w = (PAGE_W - 2 * MARGIN - GAP * (num_cols - 1)) / num_cols

        page = doc.new_page(width=PAGE_W, height=PAGE_H)

        # Name at top
        page.insert_text(
            (MARGIN, MARGIN + 25),
            display_name,
            fontsize=22,
            fontname="helv",
            color=(0.1, 0.1, 0.1),
        )

        # Available area for images
        img_top = MARGIN + NAME_H + 10
        img_bottom = PAGE_H - MARGIN
        label_h = 25
        img_area_h = img_bottom - img_top - label_h

        # Column positions
        def col_x(col_idx):
            return MARGIN + col_idx * (col_w + GAP)

        # Labels
        page.insert_text(
            (col_x(0) + col_w / 2 - 20, img_top + 15),
            "Before",
            fontsize=12,
            fontname="helv",
            color=(0.5, 0.5, 0.5),
        )
        for vi in range(num_variants):
            label = "After" if num_variants == 1 else f"Option {vi + 1}"
            label_w = len(label) * 3.5  # rough centering
            page.insert_text(
                (col_x(1 + vi) + col_w / 2 - label_w, img_top + 15),
                label,
                fontsize=12,
                fontname="helv",
                color=(0.5, 0.5, 0.5),
            )

        img_y_start = img_top + label_h

        # Insert before image
        insert_image_centered(page, before_path, col_x(0), img_y_start, col_w, img_area_h)

        # Insert variant images
        for vi, variant_path in enumerate(variants):
            insert_image_centered(page, variant_path, col_x(1 + vi), img_y_start, col_w, img_area_h)

        print(f"  ✓ {display_name} ({num_variants} variant{'s' if num_variants > 1 else ''})")

    output_path = Path(args.output)
    doc.save(str(output_path))
    doc.close()
    print(f"\nSaved: {output_path} ({len(common) + 1} pages)")


if __name__ == "__main__":
    main()
