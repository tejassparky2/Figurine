#!/usr/bin/env python3
"""Make a colorgroup 3MF printable: no colour region thinner or smaller than the nozzle can lay down.

FDM can't print salt-and-pepper. A speck of one filament inside another, or a sliver narrower than
one extrusion line, comes out as a blob, a smear or nothing - and every one of them costs a
filament change on that layer. This pass runs on the FINISHED colouring (after the colour pass and
the face paint) and enforces two limits, both in real millimetres on the mesh:

  1. --min-width (mm): morphological OPENING per colour. Faces of a colour that are within
     min_width/2 of that colour's boundary everywhere are deleted (thin bands, spikes, ragged
     fringes); anything thicker is restored to its exact original edge. Distances are measured
     between face centroids with a KD-tree, so the limit is in mm regardless of triangle size.
  2. --min-area (mm2): every connected region of one colour smaller than this merges into the
     colour it shares the longest border with. Repeats until stable (a merge can leave a
     neighbour isolated).

Deleted faces take the majority colour of their kept neighbours (flood fill), so a speck inside
skin becomes skin, never a third colour.

    python3 scripts/printable_cleanup.py in_colored.3mf -o out_colored.3mf --min-width 0.45 --min-area 0.6 --obj

Prints before/after region counts per colour. Geometry is never changed.
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from colorize_3mf import hex_to_rgb, write_3mf, write_obj_mtl  # noqa: E402


def load(path):
    xml = zipfile.ZipFile(path).read("3D/3dmodel.model").decode()
    pal = re.findall(r'<m:color color="(#[0-9a-fA-F]{6})', xml)
    if not pal:
        sys.exit(f"{path}: no <m:colorgroup> (convert paint_color files back first)")
    V = np.array(re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', xml), float)
    T = re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"(?: p1="(\d+)")?', xml)
    F = np.array([t[:3] for t in T], np.int64)
    lab = np.array([int(t[3] or 0) for t in T], np.int64)
    return trimesh.Trimesh(V, F, process=False), lab, pal


def regions(lab, adj, n_faces):
    same = lab[adj[:, 0]] == lab[adj[:, 1]]
    e = adj[same]
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n_faces, n_faces))
    return connected_components(g, directed=False)


def report(tag, lab, adj, area, pal, lim):
    n, comp = regions(lab, adj, len(lab))
    ca = np.bincount(comp, weights=area, minlength=n)
    cl = np.zeros(n, np.int64)
    cl[comp] = lab
    small = ca < lim
    per = ", ".join(f"{pal[c]}:{int((small & (cl == c)).sum())}" for c in range(len(pal)) if (small & (cl == c)).any())
    print(f"{tag}: {n:,} regions, {int(small.sum()):,} smaller than {lim} mm2 ({per or 'none'})")


def fill(lab, kill, adj, k):
    """Give every killed face the majority label of its non-killed neighbours, growing inward."""
    lab = lab.copy()
    todo = kill.copy()
    for _ in range(200):
        if not todo.any():
            break
        votes = np.zeros((len(lab), k), np.int64)
        for a, b in ((adj[:, 0], adj[:, 1]), (adj[:, 1], adj[:, 0])):
            ok = todo[a] & ~todo[b]
            np.add.at(votes, (a[ok], lab[b[ok]]), 1)
        got = votes.sum(1) > 0
        lab[got] = votes[got].argmax(1)
        todo &= ~got
    return lab


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--min-width", type=float, default=0.45, help="mm; ~ nozzle line width")
    ap.add_argument("--min-area", type=float, default=0.6, help="mm2")
    ap.add_argument("--obj", action="store_true")
    a = ap.parse_args()

    mesh, lab, pal = load(a.input)
    k = len(pal)
    adj = mesh.face_adjacency
    area = mesh.area_faces
    C = mesh.triangles_center
    report("before", lab, adj, area, pal, a.min_area)

    # 1. opening per colour, in mm
    r = a.min_width / 2.0
    edge = float(np.median(mesh.edges_unique_length))
    border = np.zeros(len(lab), bool)
    diff = lab[adj[:, 0]] != lab[adj[:, 1]]
    border[adj[diff, 0]] = True
    border[adj[diff, 1]] = True
    kill = np.zeros(len(lab), bool)
    for c in range(k):
        mask = lab == c
        if not mask.any():
            continue
        bc = C[mask & border]
        if not len(bc):
            continue
        d, _ = cKDTree(bc).query(C[mask], k=1)
        core = np.flatnonzero(mask)[d > r]
        keep = np.zeros(len(lab), bool)
        if len(core):
            near = cKDTree(C[core]).query_ball_point(C[mask], r + 0.5 * edge, return_length=True)
            keep[np.flatnonzero(mask)[near > 0]] = True
        kill |= mask & ~keep
    lab = fill(lab, kill, adj, k)
    print(f"opening (width < {a.min_width} mm): {int(kill.sum()):,} faces "
          f"({area[kill].sum():.1f} mm2) reassigned")
    report("after opening", lab, adj, area, pal, a.min_area)

    # 2. merge small regions into the neighbour with the longest shared border
    for it in range(10):
        n, comp = regions(lab, adj, len(lab))
        ca = np.bincount(comp, weights=area, minlength=n)
        small = ca < a.min_area
        if not small.any():
            break
        bd = adj[lab[adj[:, 0]] != lab[adj[:, 1]]]
        votes = np.zeros((n, k), np.int64)
        for x, y in ((bd[:, 0], bd[:, 1]), (bd[:, 1], bd[:, 0])):
            s = small[comp[x]]
            np.add.at(votes, (comp[x[s]], lab[y[s]]), 1)
        target = votes.argmax(1)
        go = small & (votes.sum(1) > 0)
        mv = go[comp]
        lab[mv] = target[comp[mv]]
        print(f"merge pass {it + 1}: {int(go.sum()):,} regions < {a.min_area} mm2 merged")
    report("after", lab, adj, area, pal, a.min_area)

    counts = np.bincount(lab, weights=area, minlength=k)
    print("area per colour: " + "  ".join(f"{pal[i]} {100 * counts[i] / area.sum():.1f}%" for i in range(k)))
    palette = np.array([hex_to_rgb(h) for h in pal], float)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_3mf(mesh, lab.astype(np.int32), palette, out, encoding="colorgroup")
    if a.obj:
        write_obj_mtl(mesh, lab.astype(np.int32), palette, out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
