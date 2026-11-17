"""
Batch-render podium nameplates from a CSV of (Name, Tag1, Tag2) rows.

Two modes:
  - default: one 3MF per row, written to exports/podium_batch/<slug>.3mf
  - --combine: a single 3MF with all rows laid out in a grid

Both modes reuse build_3mf.py's post-processor so each nameplate's color
blocks are pinned to the right filaments on Bambu import.

Usage
-----
    uv run scripts/build_batch.py "ITC Pixar Figurines - Sheet3.csv"
    uv run scripts/build_batch.py path/to/rows.csv --limit 3
    uv run scripts/build_batch.py path/to/rows.csv --only "Harish,Paras"
    uv run scripts/build_batch.py path/to/rows.csv --combine exports/all.3mf
"""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

from build_3mf import OPENSCAD, patch_object_pindex

PROJECT = Path(__file__).parent.parent
SCAD    = PROJECT / "podium_nameplate_itc.scad"
OUT_DIR = PROJECT / "exports" / "podium_batch"


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[\s_-]+", "_", s) or "unnamed"


def scad_str(value: str) -> str:
    # OpenSCAD strings: wrap in double quotes, escape backslash + double quote.
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_row(name: str, tag1: str, tag2: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        OPENSCAD,
        "--enable=lazy-union",
        "--enable=textmetrics",
        "-D", f"name_text={scad_str(name)}",
        "-D", f"sub1_text={scad_str(tag1)}",
        "-D", f"sub2_text={scad_str(tag2)}",
        "-o", str(out_path),
        str(SCAD),
    ]
    subprocess.run(cmd, check=True)
    patch_object_pindex(out_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--limit", type=int, default=None, help="Only process first N rows")
    ap.add_argument("--only", type=str, default=None,
                    help="Comma-separated name substrings (case-insensitive) to include")
    args = ap.parse_args()

    only_filters = (
        [f.strip().lower() for f in args.only.split(",") if f.strip()]
        if args.only else None
    )

    with args.csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    processed = 0
    for row in rows:
        name = (row.get("Name") or "").strip()
        if not name:
            continue
        if only_filters and not any(f in name.lower() for f in only_filters):
            continue
        tag1 = (row.get("Tag1") or "").strip()
        tag2 = (row.get("Tag2") or "").strip()
        out_path = OUT_DIR / f"{slugify(name)}.3mf"
        print(f"\n=== {name} ===")
        print(f"  tag1: {tag1!r}")
        print(f"  tag2: {tag2!r}")
        print(f"  out:  {out_path.relative_to(PROJECT)}")
        render_row(name, tag1, tag2, out_path)
        processed += 1
        if args.limit and processed >= args.limit:
            break

    print(f"\nDone. {processed} nameplate(s) written to {OUT_DIR.relative_to(PROJECT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
