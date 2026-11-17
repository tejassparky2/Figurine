"""
Batch-render Xcelerate award nameplates from a CSV with a 'Name' column.

Uses xcelerate_nameplate.scad — only name_text changes per row.
Logo, award line, and all layout settings come from the SCAD file.

Usage
-----
    uv run scripts/build_xcelerate_batch.py xcelerate_names.csv
    uv run scripts/build_xcelerate_batch.py xcelerate_names.csv --limit 3
    uv run scripts/build_xcelerate_batch.py xcelerate_names.csv --only "Sapan,Sara"
"""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

from build_3mf import OPENSCAD, patch_object_pindex

PROJECT = Path(__file__).parent.parent
SCAD    = PROJECT / "xcelerate_nameplate.scad"
OUT_DIR = PROJECT / "exports" / "xcelerate_batch"


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[\s_-]+", "_", s) or "unnamed"


def scad_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_row(name: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        OPENSCAD,
        "--enable=lazy-union",
        "--enable=textmetrics",
        "-D", f"name_text={scad_str(name)}",
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
        out_path = OUT_DIR / f"{slugify(name)}.3mf"
        print(f"\n=== {name} ===")
        print(f"  out:  {out_path.relative_to(PROJECT)}")
        render_row(name, out_path)
        processed += 1
        if args.limit and processed >= args.limit:
            break

    print(f"\nDone. {processed} nameplate(s) written to {OUT_DIR.relative_to(PROJECT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
