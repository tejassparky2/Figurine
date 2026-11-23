#!/usr/bin/env python3
"""Find and remove colour LEAKS: patches whose border does not follow the sculpt.

    python3 scripts/leak_fix.py in.3mf -o out.3mf [--max-area 60] [--max-crease 0.35] \
        [--keep-box x0:x1,y0:y1,z0:z1 ...] [--mark marked.3mf] [--report leaks.json] [--obj]

Every connected single-colour region is measured:
  area (mm2), the colour that borders it most and the share of its border that colour has, and the
  CREASE FRACTION: the share of its border length that runs along a sculpted edge (dihedral angle
  between the two faces > --crease-deg). A real painted part — a border, a bangle, a bead, a cuff, a
  bindi — ends where the sculpt changes; a leak (texture shading, a stray blotch) ends on smooth
  surface. A region is a LEAK when
      area <= --max-area  and  crease fraction <= --max-crease  and  one colour borders >= --min-share
  Leaks are recoloured to that bordering colour (repeat until stable). --keep-box protects areas
  (faces, which are painted separately). --mark writes a copy with every leak in magenta for review.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, str(Path(__file__).parent))
from colorize_3mf import hex_to_rgb, write_3mf, write_obj_mtl  # noqa: E402
from printable_cleanup import load  # noqa: E402


def analyse(mesh, lab, k, crease_cos):
    adj = mesh.face_adjacency
    elen = np.linalg.norm(mesh.vertices[mesh.face_adjacency_edges[:, 0]] -
                          mesh.vertices[mesh.face_adjacency_edges[:, 1]], axis=1)
    N = mesh.face_normals
    creased = (N[adj[:, 0]] * N[adj[:, 1]]).sum(1) < crease_cos
    same = lab[adj[:, 0]] == lab[adj[:, 1]]
    e = adj[same]
    n, comp = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])),
                                              shape=(len(lab),) * 2), directed=False)
    area = np.bincount(comp, weights=mesh.area_faces, minlength=n)
    clab = np.zeros(n, np.int64); clab[comp] = lab
    b = ~same
    border = np.zeros((n, k)); crease_len = np.zeros(n); tot = np.zeros(n)
    for x, y in ((adj[b, 0], adj[b, 1]), (adj[b, 1], adj[b, 0])):
        np.add.at(border, (comp[x], lab[y]), elen[b])
        np.add.at(tot, comp[x], elen[b])
        np.add.at(crease_len, comp[x], elen[b] * creased[b])
    cent = np.zeros((n, 3)); np.add.at(cent, comp, mesh.triangles_center * mesh.area_faces[:, None])
    cent /= np.maximum(area, 1e-9)[:, None]
    return comp, n, area, clab, border, crease_len / np.maximum(tot, 1e-9), tot, cent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--max-area", type=float, default=60.0)
    ap.add_argument("--max-crease", type=float, default=0.35)
    ap.add_argument("--min-share", type=float, default=0.6)
    ap.add_argument("--crease-deg", type=float, default=22.0)
    ap.add_argument("--keep-box", action="append", default=[])
    ap.add_argument("--mark")
    ap.add_argument("--report")
    ap.add_argument("--obj", action="store_true")
    a = ap.parse_args()

    mesh, lab, pal = load(a.input)
    k = len(pal)
    C = mesh.triangles_center
    keep = np.zeros(len(lab), bool)
    for s in a.keep_box:
        (x0, x1), (y0, y1), (z0, z1) = (map(float, p.split(":")) for p in s.split(","))
        keep |= (C[:, 0] >= x0) & (C[:, 0] <= x1) & (C[:, 1] >= y0) & (C[:, 1] <= y1) & (C[:, 2] >= z0) & (C[:, 2] <= z1)
    cc = np.cos(np.radians(a.crease_deg))
    found, first_mark = [], None
    for it in range(6):
        comp, n, area, clab, border, cfrac, tot, cent = analyse(mesh, lab, k, cc)
        share = border.max(1) / np.maximum(border.sum(1), 1e-9)
        tgt = border.argmax(1)
        kept = np.bincount(comp, weights=keep.astype(float), minlength=n) > 0
        leak = (area <= a.max_area) & (cfrac <= a.max_crease) & (share >= a.min_share) & (tot > 0) & ~kept
        if it == 0:
            first_mark = leak[comp].copy()
        if not leak.any():
            break
        for r in np.flatnonzero(leak):
            found.append({"pass": it + 1, "colour": pal[clab[r]], "into": pal[tgt[r]],
                          "area_mm2": round(float(area[r]), 2), "crease_frac": round(float(cfrac[r]), 2),
                          "at_mm": [round(float(x), 1) for x in cent[r]]})
        mv = leak[comp]
        lab[mv] = tgt[comp[mv]]
        print(f"pass {it + 1}: {int(leak.sum())} leak regions, {area[leak].sum():.1f} mm2 recoloured")
    by = {}
    for f in found:
        key = f"{f['colour']} -> {f['into']}"
        by.setdefault(key, [0, 0.0]); by[key][0] += 1; by[key][1] += f["area_mm2"]
    for key, (c, s) in sorted(by.items(), key=lambda x: -x[1][1]):
        print(f"  {key}: {c} regions, {s:.1f} mm2")
    palette = np.array([hex_to_rgb(h) for h in pal], float)
    out = Path(a.output)
    write_3mf(mesh, lab.astype(np.int32), palette, out, encoding="colorgroup")
    if a.obj:
        write_obj_mtl(mesh, lab.astype(np.int32), palette, out)
    if a.mark:
        m_lab = np.where(first_mark, k, load(a.input)[1])
        write_3mf(mesh, m_lab.astype(np.int32), np.vstack([palette, [255, 0, 220]]), Path(a.mark), encoding="colorgroup")
    if a.report:
        Path(a.report).write_text(json.dumps(found, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
