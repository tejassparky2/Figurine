#!/usr/bin/env python3
"""Structural check on a 3MF before you hand it over. Exits non-zero if it would not open.

Written after shipping two split parts that Bambu opened blank with "no geometry data". The
mesh was present and correct, so every triangle-level check passed -- including a hand-rolled
parser. What was missing was the `<build>` item that places the object on the plate, which no
amount of reading vertices will reveal. The lesson generalised: verify with something that has
to agree with a slicer, not with the same code that wrote the file.

    python3 scripts/verify_3mf.py <file.3mf> [more.3mf ...]

Checks, in the order they bite:
  1. `[Content_Types].xml` is the first zip entry (OPC requires it; some readers reject it
     otherwise, and it is easy to break by rewriting a zip in sorted order).
  2. `<build>` contains at least one `<item>`, and each references a declared object.
  3. trimesh can load it -- an independent reader that walks the build graph, so it fails
     exactly where a hand parser succeeds.
  4. Geometry sanity: bodies, boundary edges, dimensions, volume.
  5. Colour: filament count from `paint_color` codes or an `<m:colorgroup>`/basematerials index.
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh

SLOT_CODES = ["4", "8", "0C", "1C", "2C", "3C", "4C", "5C"]


def check(path: Path) -> list[str]:
    fails = []
    ok = lambda m: print(f"    \033[32mok\033[0m   {m}")
    bad = lambda m: (fails.append(m), print(f"    \033[31mFAIL\033[0m {m}"))

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        model = next((n for n in ("3D/3dmodel.model",) if n in names), None)
        if model is None:
            bad("no 3D/3dmodel.model in the archive")
            return fails
        top = z.read(model).decode("utf-8", "ignore")
        objs = {n: z.read(n).decode("utf-8", "ignore")
                for n in names if n.startswith("3D/Objects/") and n.endswith(".model")}

    if names[0] == "[Content_Types].xml":
        ok("[Content_Types].xml is first in the zip")
    else:
        bad(f"[Content_Types].xml is not first (got {names[0]!r}) — OPC readers may reject it")

    items = re.findall(r'<item[^>]*objectid="(\d+)"', top)
    declared = set(re.findall(r'<object id="(\d+)"', top))
    for x in objs.values():
        declared |= set(re.findall(r'<object id="(\d+)"', x))
    if not items:
        bad("<build> has no <item> — nothing is placed on the plate, opens blank")
    elif not set(items) <= declared:
        bad(f"<build> references objects {sorted(set(items) - declared)} that are not declared")
    else:
        ok(f"<build> places {len(items)} object(s): {items}")

    try:
        m = trimesh.load(path, force="mesh")
        if m is None or len(m.faces) == 0:
            bad("trimesh loaded no geometry")
            return fails
        ok(f"trimesh loads it: {len(m.faces):,} faces")
    except Exception as e:
        bad(f"trimesh cannot load it: {type(e).__name__}: {e}")
        return fails

    m.merge_vertices()
    e = m.extents
    _, cnt = np.unique(m.edges_sorted, axis=0, return_counts=True)
    b = int((cnt == 1).sum())
    ok(f"{e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm, {m.volume / 1000:.1f} cm3, "
       f"{m.body_count} shell(s), {b} boundary edge(s)")
    if b:
        print(f"    note boundary edges are usually auto-repaired by the slicer; "
              f"thousands would not be")

    codes = re.findall(r'paint_color="([^"]*)"', top) or [
        c for x in objs.values() for c in re.findall(r'paint_color="([^"]*)"', x)]
    if codes:
        used = {c if len(c) <= 2 else c[:2] for c in codes if c}
        slots = sorted(SLOT_CODES.index(c) + 1 for c in used if c in SLOT_CODES)
        ok(f"{len(slots)} filament(s) via paint_color, slots {slots}")
    else:
        pal = re.findall(r'<m:color[^>]*color="(#[0-9A-Fa-f]{6,8})"', top) or \
              re.findall(r'<base[^>]*displaycolor="(#[0-9A-Fa-f]{6,8})"', top)
        idx = {int(i) for x in [top, *objs.values()]
               for i in re.findall(r'<triangle[^>]*?\sp1="(\d+)"', x)}
        if pal:
            ok(f"{len(idx) or len(pal)} filament(s) via palette index: "
               + ", ".join(pal[i][:7] for i in sorted(idx)) if idx else f"palette {pal}")
        else:
            print("    note no colour information found — this is an uncoloured 3MF")
    return fails


def main():
    ap = argparse.ArgumentParser(description="Structurally verify 3MF files open correctly")
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args()
    total = 0
    for f in args.files:
        print(f"\n{f}")
        if not f.exists():
            print("    \033[31mFAIL\033[0m missing"); total += 1; continue
        total += len(check(f))
    print()
    if total:
        sys.exit(f"{total} problem(s) found")
    print("all files pass")


if __name__ == "__main__":
    main()
