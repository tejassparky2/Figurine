#!/usr/bin/env python3
"""Paint a front-view label image (from face_feature_labels.py) onto a colorgroup 3MF.

    python3 scripts/apply_face_labels.py in.3mf labels.npz -o out.3mf \
        --map skin=#CB9360 --map black=#19100A --map red=#CE0A08 --map cream=#F4DBB4 [--obj]

Every triangle is projected into the label image (front orthographic view: u = x, v = z, depth = y,
same frame and px/mm as the render). A z-buffer keeps, per pixel, only the triangle nearest the
camera; a triangle is painted when its own centroid pixel shows it in front (within --eps mm of the
nearest surface there) and it faces the camera, and the label there is >= 0. Labels: 0 skin,
1 black, 2 red, 3 cream; each maps to an existing palette entry (--map). Geometry is untouched.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from colorize_3mf import hex_to_rgb, write_3mf, write_obj_mtl  # noqa: E402
from printable_cleanup import load  # noqa: E402

NAMES = ["skin", "black", "red", "cream"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("labels")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--map", action="append", required=True, metavar="NAME=#HEX")
    ap.add_argument("--eps", type=float, default=0.12, help="mm behind the nearest surface still counted visible")
    ap.add_argument("--min-facing", type=float, default=0.05)
    ap.add_argument("--obj", action="store_true")
    a = ap.parse_args()

    mesh, lab, pal = load(a.model)
    pl = [h.lower() for h in pal]
    cls2slot = np.full(4, -1)
    for m in a.map:
        name, hexc = m.split("=")
        cls2slot[NAMES.index(name)] = pl.index(hexc.lower())
    d = np.load(a.labels)
    L = d["label"]
    u0, u1, v0, v1 = d["window"]
    ppmm = float(d["ppmm"])
    H, W = L.shape

    C = mesh.triangles_center
    N = mesh.face_normals
    px = np.floor((C[:, 0] - u0) * ppmm).astype(np.int64)
    py = np.floor((v1 - C[:, 2]) * ppmm).astype(np.int64)
    inside = (px >= 0) & (px < W) & (py >= 0) & (py < H)
    # z-buffer over every triangle's vertices AND centroid, so thin faces don't leave holes
    V = mesh.vertices
    zb = np.full(H * W, np.inf)
    for P in (C, V[mesh.faces[:, 0]], V[mesh.faces[:, 1]], V[mesh.faces[:, 2]]):
        qx = np.floor((P[:, 0] - u0) * ppmm).astype(np.int64)
        qy = np.floor((v1 - P[:, 2]) * ppmm).astype(np.int64)
        ok = (qx >= 0) & (qx < W) & (qy >= 0) & (qy < H)
        np.minimum.at(zb, qy[ok] * W + qx[ok], P[ok, 1])
    idx = np.flatnonzero(inside)
    pix = py[idx] * W + px[idx]
    vis = (C[idx, 1] <= zb[pix] + a.eps) & (-N[idx, 1] > a.min_facing)
    idx, pix = idx[vis], pix[vis]
    want = L.ravel()[pix]
    sel = want >= 0
    idx, want = idx[sel], want[sel]
    new = cls2slot[want]
    changed = int((lab[idx] != new).sum())
    lab[idx] = new
    print(f"{len(idx):,} visible faces under the labels; {changed:,} recoloured")
    for c in range(4):
        print(f"  {NAMES[c]:6s} -> {pal[cls2slot[c]]}: {int((want == c).sum()):,} faces")

    palette = np.array([hex_to_rgb(h) for h in pal], float)
    out = Path(a.output)
    write_3mf(mesh, lab.astype(np.int32), palette, out, encoding="colorgroup")
    if a.obj:
        write_obj_mtl(mesh, lab.astype(np.int32), palette, out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
