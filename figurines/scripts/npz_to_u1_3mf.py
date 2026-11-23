#!/usr/bin/env python3
"""Write a Snapmaker U1 / Orca painted 3MF from a Blender-built part (V, F, M npz).

    python3 scripts/npz_to_u1_3mf.py part.npz out.3mf --palette "#4C2C21,#EFC13A,#E6BAA8" \
        --map 0,1,0,-,-,-,2,0 [--obj] [--preview-palette "#4C2C21,#EFC13A,#DEA485"]

--map gives, for each Blender material index, the filament slot (0-based) it prints with ("-" =
material not used in this part). The package is the minimal one the U1 jobs use: 3D/3dmodel.model
with per-triangle paint_color (slot 1 = "4", 2 = "8", 3 = "0C", 4 = "1C") and
Metadata/project_settings.config holding {"filament_colour": [...]}. The mesh must be watertight
and one shell; the script refuses otherwise. --obj also writes OBJ+MTL (in the preview colours) for
renders.
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).parent))
from colorize_3mf import hex_to_rgb, write_obj_mtl  # noqa: E402

CODES = ["4", "8", "0C", "1C", "2C", "3C", "4C", "5C"]
CT = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
      'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships'
      '+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
      '<Default Extension="png" ContentType="image/png"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/'
        '3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("npz")
    ap.add_argument("output")
    ap.add_argument("--palette", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--preview-palette")
    ap.add_argument("--obj", action="store_true")
    a = ap.parse_args()

    d = np.load(a.npz)
    V, F, M = d["V"], d["F"], d["M"]
    pal = [h.strip().upper() for h in a.palette.split(",")]
    mp = [(-1 if t.strip() == "-" else int(t)) for t in a.map.split(",")]
    mp += [-1] * (int(M.max()) + 1 - len(mp))
    slot = np.array(mp)[M]
    if (slot < 0).any():
        sys.exit(f"materials {sorted(set(M[slot < 0].tolist()))} have no slot in --map")
    mesh = trimesh.Trimesh(V, F, process=False)
    if not (mesh.is_watertight and mesh.is_winding_consistent and mesh.body_count == 1):
        sys.exit(f"not printable: watertight={mesh.is_watertight} winding={mesh.is_winding_consistent} "
                 f"bodies={mesh.body_count}")
    used = np.bincount(slot, minlength=len(pal))
    vx = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in V)
    tx = "".join(f'<triangle v1="{i}" v2="{j}" v3="{k}" paint_color="{CODES[s]}"/>' for (i, j, k), s in zip(F, slot))
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1" '
             f'type="model"><mesh><vertices>{vx}</vertices><triangles>{tx}</triangles></mesh></object></resources>'
             '<build><item objectid="1"/></build></model>')
    out = Path(a.output)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/project_settings.config", json.dumps({"filament_colour": pal}))
    ext = mesh.extents
    print(f"wrote {out}: {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm, {mesh.volume / 1000:.1f} cm3, "
          f"{len(F):,} triangles, watertight, 1 shell")
    for i, h in enumerate(pal):
        print(f"  head {i + 1}: {h}  {used[i]:,} triangles")
    if a.obj:
        pp = [h.strip() for h in (a.preview_palette or a.palette).split(",")]
        write_obj_mtl(mesh, slot.astype(np.int32), np.array([hex_to_rgb(h) for h in pp], float), out)


if __name__ == "__main__":
    main()
