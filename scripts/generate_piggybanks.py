#!/usr/bin/env python3
"""
Generate name-sign piggy banks for a list of names, and combine them into one file.

Two designs are supported — customers pick one or the other:

  2color  (default)  Baby Donuts font, box + name in 2 colors.
                     openscad/piggybankGenerator_veera.scad
  3layer             Spicy Sale font, name built from a darker outline rim +
                     lighter letter face on the plate (3 colors). That font is
                     wide, so the name is condensed in X (nameXScale) to keep
                     the sign on one plate without shrinking letter height.
                     openscad/piggybankGenerator_veera_3layer.scad

Names with 4 or fewer characters get their letter spacing nudged up (1.2 by
default, --short-spacing to change) so the bank body isn't too small. This
replaced the old "<< NAME >>" bracket padding, which blew a 4-letter bank out to
~218mm — wider than a normal 6-letter name — and didn't print well.

Usage:
    # 2-color Baby Donuts (the default design)
    python scripts/generate_piggybanks.py names.txt -o out/

    # 3-layer Spicy Sale
    python scripts/generate_piggybanks.py names.txt -o out/ --design 3layer

    # colored 3MF is the default; STL if you only need geometry
    python scripts/generate_piggybanks.py names.txt -o out/ --format stl

    # bake this group's colors into the combined 3MF (swatch order)
    python scripts/generate_piggybanks.py names.txt -o out/ --colors "#7A3FAE,#F07DB0"
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OPENSCAD_CANDIDATES = [
    "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    "/Users/apoorv/Desktop/OpenSCAD.app/Contents/MacOS/OpenSCAD",
]

DESIGNS = {
    "2color": REPO_ROOT / "openscad" / "piggybankGenerator_veera.scad",
    "3layer": REPO_ROOT / "openscad" / "piggybankGenerator_veera_3layer.scad",
}

GAP_MM = 20  # gap between models in the combined file

SHORT_NAME_LEN = 4        # names this long or shorter get the spacing nudge
SHORT_NAME_SPACING = 1.2  # letter spacing used for those names


def find_openscad() -> str:
    for c in OPENSCAD_CANDIDATES:
        if Path(c).exists():
            return c
    found = shutil.which("openscad")
    if found:
        return found
    sys.exit(
        "Could not find the OpenSCAD binary. Pass it explicitly with --openscad "
        f"(looked in: {', '.join(OPENSCAD_CANDIDATES)})"
    )


def name_spacing(name: str, short_spacing: float) -> float:
    """Very short names get their letters nudged apart so the bank body isn't
    too small. This replaces the old '<< NAME >>' bracket padding, which pushed
    a 4-letter bank out to ~218mm — wider than a normal 6-letter name."""
    if len(name) <= SHORT_NAME_LEN:
        return short_spacing
    return 1.0


def export(name: str, out_path: Path, openscad: str, scad_file: Path,
           fmt: str, font: str | None, spacing: float,
           back_text: str | None = None) -> bool:
    cmd = [openscad, "--enable=textmetrics"]
    if fmt == "3mf":
        # lazy-union keeps the parts separate and basematerial carries the
        # colors, so the slicer gets them without any hand painting.
        cmd += ["--enable=lazy-union", "-O", "export-3mf/material-type=basematerial"]
    else:
        cmd += ["--render"]
    cmd += ["-D", f'name="{name}"', "-D", 'mode="preview"',
            "-D", f"letterSpacing={spacing}"]
    if font:
        cmd += ["-D", f'font="{font}"']
    if back_text:
        # {name} lets one flag cover a whole batch, e.g. "From {name}"
        cmd += ["-D", f'backText="{back_text.format(name=name)}"']
    cmd += ["-o", str(out_path), str(scad_file)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def combine_stls(stl_paths: list[Path], out_path: Path) -> None:
    import numpy as np
    from stl import mesh

    meshes = []
    x_offset = 0.0
    for path in stl_paths:
        m = mesh.Mesh.from_file(str(path))
        min_x = float(m.vectors[:, :, 0].min())
        max_x = float(m.vectors[:, :, 0].max())
        m.translate([x_offset - min_x, 0, 0])
        x_offset += (max_x - min_x) + GAP_MM
        meshes.append(m)

    combined = mesh.Mesh(np.concatenate([m.data for m in meshes]))
    combined.save(str(out_path))


def main():
    parser = argparse.ArgumentParser(
        description="Generate name-sign piggy banks for a list of names")
    parser.add_argument("names_file", help="Text file with one name per line")
    parser.add_argument("-o", "--output", default="output_banks", help="Output directory")
    parser.add_argument("--design", choices=sorted(DESIGNS), default="2color",
                        help="Which bank design to build (default: 2color)")
    parser.add_argument("--format", choices=["3mf", "stl"], default="3mf",
                        help="3mf keeps colors (default); stl is geometry only")
    parser.add_argument("--colors", help="Comma-separated hex colors to bake into the "
                                         "combined 3MF, in swatch order")
    parser.add_argument("--short-spacing", type=float, default=SHORT_NAME_SPACING,
                        help=f"Letter spacing for names <= {SHORT_NAME_LEN} chars "
                             f"(default: {SHORT_NAME_SPACING})")
    parser.add_argument("--back-text", help="Engrave this line into the underside "
                                            "(3layer design only). '{name}' is "
                                            "substituted per bank, e.g. 'From {name}'")
    parser.add_argument("--font", help="Override the design's font")
    parser.add_argument("--openscad", help="Path to the OpenSCAD binary")
    args = parser.parse_args()

    openscad = args.openscad or find_openscad()
    scad_file = DESIGNS[args.design]
    if not scad_file.exists():
        sys.exit(f"Design file missing: {scad_file}")

    # Only the 3-layer .scad has a backText parameter. Passing -D backText to the
    # 2-color one would just define an unused variable and silently engrave
    # nothing, so fail loudly instead.
    if args.back_text and args.design != "3layer":
        sys.exit(f"--back-text is only supported by the 3layer design "
                 f"(got --design {args.design})")

    names_path = Path(args.names_file)
    if not names_path.exists():
        sys.exit(f"Error: {names_path} not found")

    names = [n.strip() for n in names_path.read_text().splitlines() if n.strip()]
    if not names:
        sys.exit("No names found in file")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Design : {args.design}  ({scad_file.name})")
    print(f"Format : {args.format}")
    print(f"Output : {out_dir}/\n")

    paths = []
    for name in names:
        spacing = name_spacing(name, args.short_spacing)
        label = repr(name) + (f"  (spacing {spacing})" if spacing != 1.0 else "")
        out = out_dir / f"{name.replace(' ', '_')}.{args.format}"
        print(f"  {label} ... ", end="", flush=True)
        if export(name, out, openscad, scad_file, args.format, args.font, spacing,
                  args.back_text):
            print("done")
            paths.append(out)
        else:
            print("FAILED")

    if len(paths) > 1:
        combined = out_dir / f"combined.{args.format}"
        print(f"\nCombining {len(paths)} models -> {combined} ... ", end="", flush=True)
        if args.format == "stl":
            combine_stls(paths, combined)
        else:
            from merge_3mf import merge
            colors = [c.strip() for c in args.colors.split(",")] if args.colors else None
            merge(paths, combined, colors)
        print("done")

    print(f"\nDone. {len(paths)}/{len(names)} succeeded.")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
