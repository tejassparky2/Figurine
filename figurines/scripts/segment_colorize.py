#!/usr/bin/env python3
"""Color a figurine by SEGMENT, not by per-pixel color — the robust path.

Blind per-face quantization can't (a) keep a shaded region (skin) together or (b) separate parts
that share a color (hair/shirt/shoes all near-black). Segmentation fixes both: each Tripo part is
one solid geometric region, so we give it ONE color sampled from the texture, then group the parts
into N filament colors. See docs/auto_coloring.md (EXP-009/010).

Inputs:
  --segmented  GLB from Tripo mesh_segmentation (parts as separate sub-meshes)
  --textured   GLB with the texture (color source; pbr=false recommended)

Each part's color = median of the nearest textured vertices. Parts are then merged into N filament
colors by weighted k-means over part colors (or kept separate with --no-merge).

Usage:
  python scripts/segment_colorize.py --segmented seg.glb --textured tex.glb \
      -o out.3mf -n 5 --height 120 --obj --preview out_preview.png
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(__file__))
from colorize_3mf import write_3mf, write_obj_mtl, render_preview, rgb_to_hex  # noqa: E402  # type: ignore


def farthest_first(X, k):
    """Deterministic seed indices: start from the global-mean-nearest, then farthest points."""
    idx = [int(np.argmin(((X - X.mean(0)) ** 2).sum(1)))]
    for _ in range(k - 1):
        d = np.min([((X - X[i]) ** 2).sum(1) for i in idx], axis=0)
        idx.append(int(np.argmax(d)))
    return idx


def weighted_kmeans(X, w, k, iters=100):
    C = X[farthest_first(X, k)].astype(float)
    lab = np.zeros(len(X), int)
    for _ in range(iters):
        lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
        newC = np.array([
            np.average(X[lab == j], axis=0, weights=w[lab == j]) if np.any(lab == j) else C[j]
            for j in range(k)
        ])
        if np.allclose(newC, C):
            break
        C = newC
    return lab


def is_skin(col, min_r=130):
    """Skin: warm (R clearly > B), reasonably bright R. Excludes dark facial hair / fabric."""
    r, g, b = col
    return (r > min_r) and (r - b > 0.28 * r) and (r >= g)


def classify_semantic3(part_col, part_z, head_line=0.45, skin_min_r=130):
    """Map each part to 0=hair, 1=skin, 2=clothes.
    skin = warm color; otherwise hair if in the head region (high normalized height) else clothes."""
    labels = np.empty(len(part_col), int)
    for i, (col, z) in enumerate(zip(part_col, part_z)):
        if is_skin(col, skin_min_r):
            labels[i] = 1
        elif z > head_line:
            labels[i] = 0
        else:
            labels[i] = 2
    return labels


def classify_semantic4(part_col, part_z, head_line=0.45, face_line=0.60, warm_min_r=105):
    """Map each part to 0=hair, 1=skin, 2=top, 3=bottom.
    Warm parts (skin OR colored clothing) split by height: high=skin (face), low=top.
    Dark parts split by height: high=hair, low=bottom. Good for two-tone outfits."""
    labels = np.empty(len(part_col), int)
    for i, (col, z) in enumerate(zip(part_col, part_z)):
        r, g, b = col
        warm = (r > warm_min_r) and (r - b > 0.28 * r) and (r >= g)
        if warm:
            labels[i] = 1 if z > face_line else 2
        else:
            labels[i] = 0 if z > head_line else 3
    return labels


def reorient_scale(mesh, height):
    tallest = int(np.argmax(mesh.extents))
    if tallest == 1:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    elif tallest == 0:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    if height:
        mesh.apply_scale(height / mesh.extents[2])
    b = mesh.bounds
    mesh.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])


def main():
    ap = argparse.ArgumentParser(description="Segment-based figurine colorizer")
    ap.add_argument("--segmented", required=True, help="GLB from mesh_segmentation")
    ap.add_argument("--textured", required=True, help="textured GLB (color source)")
    ap.add_argument("-o", "--output", required=True, help="output 3MF")
    ap.add_argument("-n", "--n-colors", type=int, default=5, help="number of filament colors (kmeans scheme)")
    ap.add_argument("--scheme", choices=["kmeans", "semantic3", "semantic4"], default="kmeans",
                    help="kmeans: group part colors into N. semantic3: hair/skin/clothes. "
                         "semantic4: hair/skin/top/bottom (two-tone outfits)")
    ap.add_argument("--head-line", type=float, default=0.45,
                    help="(semantic) normalized height splitting hair (above) from bottom/clothes (below)")
    ap.add_argument("--face-line", type=float, default=0.60,
                    help="(semantic4) height splitting warm regions: face skin (above) vs top (below)")
    ap.add_argument("--skin-min-r", type=float, default=130,
                    help="min red for a part to count as skin/warm. Lower (~105) to include "
                         "darker colored tops in semantic4")
    ap.add_argument("--no-override", action="store_true",
                    help="(semantic3) disable the within-skin beard/eyebrow recolor")
    ap.add_argument("--hair-dark-max", type=float, default=95,
                    help="(semantic3) faces in skin parts darker than this (max RGB) -> hair")
    ap.add_argument("--override-min-faces", type=int, default=400,
                    help="(semantic3) min connected dark-face count to keep as facial hair; "
                         "smaller dark blobs (shadow specks) are dropped. Lower = more aggressive")
    ap.add_argument("--smooth", type=int, default=0,
                    help="majority-vote passes to clean jagged region boundaries (try 3-6)")
    ap.add_argument("--no-merge", action="store_true", help="keep every part as its own color")
    ap.add_argument("--height", type=float, help="scale to this Z height (mm)")
    ap.add_argument("--encoding", choices=["colorgroup", "basematerials"], default="colorgroup")
    ap.add_argument("--obj", action="store_true", help="also write OBJ+MTL (best in Bambu)")
    ap.add_argument("--preview", help="front|back preview PNG path")
    args = ap.parse_args()

    # color source
    tex = trimesh.load(args.textured, process=False)
    tm = tex.to_geometry() if isinstance(tex, trimesh.Scene) else tex
    tcol = np.asarray(tm.visual.to_color().vertex_colors)[:, :3].astype(float)  # type: ignore[union-attr]
    tree = cKDTree(tm.vertices)

    # segmented parts
    seg = trimesh.load(args.segmented, process=False)
    if not isinstance(seg, trimesh.Scene):
        raise SystemExit("Segmented GLB has no parts (not a Scene).")
    parts = list(seg.geometry.values())

    # per-part dominant color, size, normalized height (Z-up)
    Rz = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])[:3, :3]
    allz = np.vstack([g.vertices @ Rz.T for g in parts])[:, 2]
    zlo, zhi = allz.min(), allz.max()
    part_col = np.zeros((len(parts), 3))
    part_size = np.zeros(len(parts))
    part_z = np.zeros(len(parts))
    for i, geom in enumerate(parts):
        _, idx = tree.query(geom.vertices, k=1)
        part_col[i] = np.median(tcol[idx], axis=0)
        part_size[i] = len(geom.faces)
        part_z[i] = ((geom.vertices @ Rz.T)[:, 2].mean() - zlo) / (zhi - zlo)

    # group parts -> filament colors
    names = None
    if args.scheme in ("semantic3", "semantic4"):
        if args.scheme == "semantic3":
            names = ["hair", "skin", "clothes"]
            part_to_fil = classify_semantic3(part_col, part_z, args.head_line, args.skin_min_r)
        else:
            names = ["hair", "skin", "top", "bottom"]
            part_to_fil = classify_semantic4(part_col, part_z, args.head_line, args.face_line, args.skin_min_r)
        palette = np.array([
            np.average(part_col[part_to_fil == j], axis=0, weights=part_size[part_to_fil == j])
            if np.any(part_to_fil == j) else np.array([128, 128, 128.])
            for j in range(len(names))
        ])
        print(f"{len(parts)} parts -> {len(names)} semantic colors: "
              + ", ".join(f"{names[j]}={rgb_to_hex(palette[j])}" for j in range(len(names))))
    elif args.no_merge or args.n_colors >= len(parts):
        part_to_fil = np.arange(len(parts))
        palette = part_col.copy()
    else:
        part_to_fil = weighted_kmeans(part_col, part_size, args.n_colors)
        palette = np.array([
            np.average(part_col[part_to_fil == j], axis=0, weights=part_size[part_to_fil == j])
            if np.any(part_to_fil == j) else part_col[0]
            for j in range(args.n_colors)
        ])
        print(f"{len(parts)} parts -> {len(palette)} filament colors")
    fil_names = names
    for i, geom in enumerate(parts):
        fil = int(part_to_fil[i])
        tag = fil_names[fil] if fil_names else f"filament {fil}"
        print(f"  part {i:>2} ({int(part_size[i]):>7} faces) z={part_z[i]:.2f} {rgb_to_hex(part_col[i])} "
              f"-> {tag} {rgb_to_hex(palette[fil])}")

    # merge parts into one mesh, tracking per-face filament + which part each face came from
    Vs, Fs, fl, vl, fp = [], [], [], [], []
    off = 0
    for i, geom in enumerate(parts):
        fil = int(part_to_fil[i])
        Vs.append(geom.vertices)
        Fs.append(geom.faces + off)
        fl.append(np.full(len(geom.faces), fil))
        vl.append(np.full(len(geom.vertices), fil))
        fp.append(np.full(len(geom.faces), i))
        off += len(geom.vertices)
    mesh = trimesh.Trimesh(np.vstack(Vs), np.vstack(Fs), process=False)
    face_idx = np.concatenate(fl).astype(np.int32)
    vlabel = np.concatenate(vl).astype(np.int32)
    face_part = np.concatenate(fp)

    # within-skin override: beard/eyebrows/mustache are texture-only (no separate geometry),
    # so faces inside a SKIN part whose actual texture color is dark -> reassign to hair.
    # The raw darkness test is noisy (catches nostril/eye-socket SHADOW specks). Real facial hair
    # forms a few LARGE connected dark masses; shadows are many SMALL ones. So we keep only dark
    # connected-components above a face-count threshold.
    if args.scheme == "semantic3" and not args.no_override:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        HAIR, SKIN = 0, 1
        nf = len(mesh.faces)
        skin_parts = np.where(part_to_fil == SKIN)[0]
        sel = np.isin(face_part, skin_parts)
        cent = mesh.vertices[mesh.faces].mean(axis=1)
        _, idx = tree.query(cent, k=1)
        cand = sel & (tcol[idx].max(axis=1) < args.hair_dark_max)
        raw = int(cand.sum())

        # connected components among candidate faces (edges where both faces are candidates)
        adj = mesh.face_adjacency
        e = adj[cand[adj[:, 0]] & cand[adj[:, 1]]]
        g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nf, nf))
        _, comp = connected_components(g, directed=False)
        sizes = np.bincount(comp)
        big = np.zeros(nf, bool)
        big[cand] = sizes[comp[cand]] >= args.override_min_faces  # keep only large dark masses

        face_idx[big] = HAIR
        for f in mesh.faces[big]:
            vlabel[f] = HAIR
        print(f"  skin->hair override: {raw} dark faces -> kept {int(big.sum())} "
              f"in masses >= {args.override_min_faces} faces (dropped {raw - int(big.sum())} shadow specks)")

    # boundary smoothing: color edges follow Tripo's (jagged) segmentation seams. Weld the mesh so
    # parts actually share edges, then majority-vote relabel each face from its neighbors a few
    # times to straighten the zigzags (very visible on high-contrast boundaries like pink/skin).
    if args.smooth > 0:
        mesh.merge_vertices()
        adj = mesh.face_adjacency
        a, b = adj[:, 0], adj[:, 1]
        nf = len(mesh.faces)
        K = len(palette)
        idx_self = np.arange(nf)
        for _ in range(args.smooth):
            counts = np.zeros((nf, K))
            for k in range(K):
                mk = (face_idx == k).astype(float)
                counts[:, k] = (np.bincount(a, weights=mk[b], minlength=nf)
                                + np.bincount(b, weights=mk[a], minlength=nf))
            counts[idx_self, face_idx] += 0.5  # slight self-bias to avoid flip-flop
            face_idx = counts.argmax(1).astype(np.int32)
        vlabel = np.zeros(len(mesh.vertices), np.int32)
        vlabel[mesh.faces.reshape(-1)] = np.repeat(face_idx, 3)
        print(f"  boundary smoothing: {args.smooth} majority-vote pass(es) on welded mesh")

    reorient_scale(mesh, args.height)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_3mf(mesh, face_idx, palette, out, encoding=args.encoding)
    print(f"\nWrote {out} ({out.stat().st_size/1e6:.1f} MB, {len(mesh.faces)} tris, "
          f"{len(palette)} colors, encoding={args.encoding})")
    if args.obj:
        write_obj_mtl(mesh, face_idx, palette, out)
    if args.preview:
        render_preview(mesh, vlabel, palette, Path(args.preview))


if __name__ == "__main__":
    main()
