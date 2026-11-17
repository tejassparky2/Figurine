#!/usr/bin/env python3
"""Bridge: colorize_3mf.py output -> a real Bambu project 3MF with per-triangle MMU paint.

`colorize_3mf.py` writes a bare 3MF whose colors live in an `<m:colorgroup>` and a per-triangle
`p1` index. That is what Bambu *displays*, but `split_painted_3mf.py` reads the other encoding —
Bambu's own `paint_color` attribute, plus the filament palette in `Metadata/project_settings.config`.
This converts the first into the second, so the colorize -> split chain works without a manual
round-trip through Bambu Studio.

    python3 scripts/colorgroup_to_painted.py <colored.3mf> -o <painted.3mf>

Slot i of the palette becomes filament slot i+1, and the paint code table is the one verified in
split_painted_3mf.py (slot 1 = "4", slot 2 = "8", slot 3 = "0C", ...). Geometry is copied
verbatim — the mesh is untouched, only the color encoding changes.

The project shell (printer profile, filament types, plate settings) is cloned from a template
Bambu project so the result opens as a normal project. Only the filament colours are rewritten.
"""

import argparse
import copy
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

# Same table as split_painted_3mf.py — paint codes map monotonically onto filament slots 1..N.
SLOT_CODES = ["4", "8", "0C", "1C", "2C", "3C", "4C", "5C"]

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "projects/juthikasis/models/sister_v1_n5.3mf"

V_RE = re.compile(r'<vertex x="([-\d.eE+]+)" y="([-\d.eE+]+)" z="([-\d.eE+]+)"')
T_RE = re.compile(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"(?:\s+p1="(\d+)")?')
C_RE = re.compile(r'<m:color color="(#[0-9a-fA-F]{6})"')

OBJ_HDR = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
           'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
           'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
           'requiredextensions="p">\n')


def load_colorgroup(path: Path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("3D/3dmodel.model").decode()
    palette = C_RE.findall(xml)
    if not palette:
        raise SystemExit(f"{path.name}: no <m:colorgroup> — run colorize_3mf.py with "
                         "--encoding colorgroup (the default)")
    verts = np.array(V_RE.findall(xml), dtype=np.float64)
    tris = T_RE.findall(xml)
    faces = np.array([[int(a), int(b), int(c)] for a, b, c, _ in tris], dtype=np.int64)
    pidx = np.array([int(p) if p else 0 for *_, p in tris], dtype=np.int64)
    return verts, faces, pidx, palette


def resize_filament_lists(cfg: dict, n: int, palette) -> dict:
    """Every per-filament list in project_settings must have the same length as the palette."""
    cfg = copy.deepcopy(cfg)
    ref = cfg.get("filament_colour", [])
    for key, val in list(cfg.items()):
        if isinstance(val, list) and len(val) == len(ref) and len(ref):
            cfg[key] = [val[i] if i < len(val) else val[-1] for i in range(n)]
    cfg["filament_colour"] = list(palette)
    return cfg


def build_object_model(verts, faces, codes) -> bytes:
    vx = "\n".join(f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in verts)
    tr = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{p}"/>'
                   for (a, b, c), p in zip(faces, codes))
    return (OBJ_HDR + ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
            '  <object id="1" p:UUID="00010000-81cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
            '   <mesh>\n    <vertices>\n' + vx + '\n    </vertices>\n'
            '    <triangles>\n' + tr + '\n    </triangles>\n'
            '   </mesh>\n  </object>\n </resources>\n <build/>\n</model>\n').encode()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("colored", type=Path, help="colorgroup 3MF from colorize_3mf.py")
    ap.add_argument("-o", "--out", type=Path, required=True, help="painted Bambu project 3MF")
    ap.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE,
                    help="Bambu project 3MF to clone printer/filament settings from")
    ap.add_argument("--name", default=None, help="object name in Bambu (default: output stem)")
    args = ap.parse_args()

    if not args.template.exists():
        raise SystemExit(f"template not found: {args.template} — pass --template")

    verts, faces, pidx, palette = load_colorgroup(args.colored)
    n = len(palette)
    if n > len(SLOT_CODES):
        raise SystemExit(f"{n} colors exceeds the {len(SLOT_CODES)} slots this encoding covers")
    codes = np.array(SLOT_CODES, dtype=object)[pidx]
    name = args.name or args.out.stem

    print(f"{args.colored.name}: {len(verts):,} verts, {len(faces):,} faces, {n} colors")
    hist = Counter(pidx.tolist())
    for i, hexcol in enumerate(palette):
        print(f"  slot{i+1} {hexcol}  code {SLOT_CODES[i]:>2}  "
              f"{hist.get(i, 0):>9,} faces  {hist.get(i, 0)/len(faces)*100:5.1f}%")

    with zipfile.ZipFile(args.template) as z:
        data = {n_: z.read(n_) for n_ in z.namelist()}
    obj_entry = next((k for k in data if re.fullmatch(r"3D/Objects/object_\d+\.model", k)), None)
    if obj_entry is None:
        raise SystemExit(f"{args.template.name}: no 3D/Objects/object_N.model to replace")

    data[obj_entry] = build_object_model(verts, faces, codes)

    cfg = json.loads(data["Metadata/project_settings.config"].decode())
    data["Metadata/project_settings.config"] = json.dumps(
        resize_filament_lists(cfg, n, palette), indent=4).encode()

    # colorize_3mf.py already sits the mesh on z=0 and centres X/Y, so the plate transform is
    # a pure move to the bed centre — no z lift, unlike the template it was cloned from.
    ms = data["Metadata/model_settings.config"].decode()
    ms = re.sub(r'face_count="\d+"', f'face_count="{len(faces)}"', ms)
    ms = re.sub(r'key="source_file" value="[^"]*"', f'key="source_file" value="{args.out.name}"', ms)
    ms = re.sub(r'key="source_offset_z" value="[^"]*"', 'key="source_offset_z" value="0"', ms)
    ms = re.sub(r'key="name" value="[^"]*"', f'key="name" value="{name}"', ms)
    ms = re.sub(r'transform="([-\d. ]+?) [-\d.]+ [-\d.]+ [-\d.]+"',
                r'transform="\1 128 128 0"', ms)
    data["Metadata/model_settings.config"] = ms.encode()

    top = data["3D/3dmodel.model"].decode()
    top = re.sub(r'(<item objectid="\d+"[^>]*transform="(?:[-\d.]+ ){9})[-\d.]+ [-\d.]+ [-\d.]+"',
                 r'\g<1>128 128 0"', top)
    data["3D/3dmodel.model"] = top.encode()

    # stale thumbnails and cut records belong to the template's model, not this one
    drop = [k for k in data if re.match(r"Metadata/(plate_|top_|pick_)", k)]
    drop += [k for k in ("Metadata/cut_information.xml",) if k in data]
    for k in drop:
        del data[k]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for k, v in data.items():
            zo.writestr(k, v)

    ext = verts.max(0) - verts.min(0)
    print(f"\nWrote {args.out}  ({args.out.stat().st_size/1e6:.1f} MB)")
    print(f"  {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm, {n} filaments: {', '.join(palette)}")


if __name__ == "__main__":
    main()
