#!/usr/bin/env python3
"""Segmentation-guided coloring: one flat filament color per Tripo mesh part.

The colorize_3mf.py path decides each *vertex* independently, so Tripo's baked ambient
occlusion drags shaded creases onto whatever palette color happens to be nearest — usually
black (EXP-022). Here the decision is made once per *part*, on the part's median color, so
shading inside a part cannot change its color and boundaries land on real geometric seams.

Key difference from split_painted_3mf.py: we use the segmentation only as a **face label map**
and keep the original watertight mesh completely untouched. Nothing is physically split, so
there is nothing to recombine, the mesh stays watertight/single-body, and we skip the
`mesh_completion` (quick_cap) call entirely — 30 credits cheaper and one task faster.

Usage:
  python3 scripts/segment_paint_3mf.py <textured.glb> --geometry <geom.3mf> -o <out.3mf> \
      --palette "#RRGGBB,..." --height 150 --granularity detailed --obj

Cost: one v3 mesh_segmentation task (40 credits, ~2-5 min). Cached in --cache, so re-runs
with different palettes or --mixed-frac are free.
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
import requests
import trimesh
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from colorize_3mf import (assign_nearest, hex_to_rgb, reorient, rgb_to_hex,  # noqa: E402
                          srgb_to_lab, to_feature, write_3mf, write_obj_mtl)
from split_painted_3mf import BASE, api, load_parts, make_transform, poll  # noqa: E402


def seat(m):
    """Center X/Y, sit on Z=0."""
    m.apply_translation([-(m.bounds[0][0] + m.bounds[1][0]) / 2,
                         -(m.bounds[0][1] + m.bounds[1][1]) / 2, -m.bounds[0][2]])
    return m


def segment(mesh, cache: Path, granularity: str, H):
    """Upload the geometry and run v3 /mesh/segment. No /mesh/complete — we only need labels.
    Every artifact is cached, so a second run costs nothing."""
    cache.mkdir(parents=True, exist_ok=True)
    glb = cache / "seg_input.glb"
    if not glb.exists():
        trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False).export(glb)
    print(f"  seg_input.glb {glb.stat().st_size / 1e6:.1f} MB")

    tok_f = cache / "file_token.txt"
    if not tok_f.exists():
        with open(glb, "rb") as f:
            r = requests.post(f"{BASE}/files", headers=H, files={"file": (glb.name, f)}, timeout=1800)
        j = r.json()
        if j.get("code") != 0:
            sys.exit(f"upload failed ({r.status_code}): {j}")
        tok_f.write_text(j["data"]["file_token"])

    seg_f = cache / f"seg_task_{granularity}.txt"
    if not seg_f.exists():
        body = {"input": tok_f.read_text().strip(), "model": "v2.0-20260430",
                "segmentation_granularity": granularity, "split_by_connectivity": False}
        j = requests.post(f"{BASE}/mesh/segment", headers={**H, "Content-Type": "application/json"},
                          json=body, timeout=120).json()
        if j.get("code") != 0:
            sys.exit(f"segment failed: {j}")
        seg_f.write_text(j["data"]["task_id"])
        print(f"  segment task {seg_f.read_text().strip()} (saved)")
    d = poll(seg_f.read_text().strip(), H, "segment")

    parts = cache / f"parts_{granularity}.glb"
    if not parts.exists():
        url = d["output"].get("model_url") or d["output"].get("model")
        parts.write_bytes(requests.get(url, timeout=1800).content)
    print(f"  parts_{granularity}.glb {parts.stat().st_size / 1e6:.1f} MB")
    return parts


def label_faces(mesh, parts: dict):
    """Map every original face to a part id, via nearest part-face centroid.

    EXP-021 measured Tripo segmentation as a lossless partition of the same surface
    (face count -0.03%, 99.9% of part verts within 1e-6 of an original), so a centroid
    KDTree round-trips at ~0mm. Faces no part claims fall back to their nearest labelled
    neighbour.

    Tripo returns the parts renormalized into a unit box, so they must be mapped back to
    mm first -- with ONE global affine (per-part would inflate each part). Skipping this
    collapses every part onto a handful of faces near the origin and the whole label map
    silently degenerates.
    """
    xf = make_transform(parts, mesh.vertices)
    oc = mesh.triangles_center
    tree = cKDTree(oc)
    lab = np.full(len(mesh.faces), -1, dtype=np.int64)
    dist = np.full(len(mesh.faces), np.inf)
    for pid, (_, pm) in enumerate(parts.items()):
        d, idx = tree.query(xf(pm.triangles_center), k=1)
        # a part face claims an original face only if it is the closest claimant so far
        order = np.argsort(-d)          # write best-last so nearest claimant wins duplicates
        idx, d = idx[order], d[order]
        better = d < dist[idx]
        lab[idx[better]] = pid
        dist[idx[better]] = d[better]
    miss = lab < 0
    if miss.any():
        known = ~miss
        _, nn = cKDTree(oc[known]).query(oc[miss], k=1)
        lab[miss] = lab[known][nn]
    return lab, int(miss.sum())


def main():
    ap = argparse.ArgumentParser(description="Segmentation-guided flat-color 3MF")
    ap.add_argument("input", help="textured GLB (color source)")
    ap.add_argument("--geometry", required=True, help="watertight geometry 3MF (convert_model)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--palette", required=True, help="comma-separated filament hexes")
    ap.add_argument("--height", type=float, required=True,
                    help="target size along the up axis (see --up-axis)")
    ap.add_argument("--up-axis", choices=["auto", "x", "y", "z"], default="auto",
                    help="which axis of the INPUT (textured GLB) is 'up' and should become +Z. "
                         "'auto' (default) guesses the longest axis, which is right for a standing "
                         "figure but WRONG for anything longer than it is tall (a vehicle): the "
                         "length gets stood on end. glTF is Y-up, so pass 'y' for those. Note the "
                         "guess is made per-mesh, so on a long subject the GLB and the geometry "
                         "3MF can land in DIFFERENT frames -- then the colour transfer samples the "
                         "wrong surface and the model comes out miscoloured, not just tipped.")
    ap.add_argument("--geometry-up-axis", choices=["auto", "x", "y", "z"], default="auto",
                    help="same, for --geometry. Tripo's convert_model 3MF is already Z-up, so pass "
                         "'z' when the auto guess would rotate it (i.e. long subjects).")
    ap.add_argument("--granularity", default="detailed", choices=["simple", "balanced", "detailed"])
    ap.add_argument("--cache", help="dir for Tripo artifacts (default: <output dir>/seg_cache)")
    ap.add_argument("--mixed-frac", type=float, default=0.70,
                    help="if the flat color covers less than this fraction of a part's vertices, "
                         "the part genuinely spans two colors -- keep per-vertex snapping inside "
                         "it instead of flattening (rescues glasses fused into a face part)")
    ap.add_argument("--color-space", choices=["rgb", "lab"], default="rgb")
    ap.add_argument("--luma-weight", type=float, default=1.0)
    ap.add_argument("--black-chroma", type=float, default=0.0,
                    help="a vertex may take the darkest palette slot only if its Lab chroma is "
                         "below this. Baked shading is multiplicative, so a shaded garment stays "
                         "chromatic while real black sits at chroma ~0 (EXP-022: horse/snake dark "
                         "px chroma 1.2/0.0, doctor's shaded px 8.3). 0 disables the gate.")
    ap.add_argument("--part", action="append", default=[], metavar="IDX=#HEX",
                    help="force part IDX to this colour, overriding everything else. Repeatable. "
                         "Read the indices off --parts-map. This is the hand-painting escape "
                         "hatch: 'part 12 is the moustache, make it white'.")
    ap.add_argument("--parts-map", metavar="PATH.3mf",
                    help="also write a 3MF coloured by part index (one distinct colour per part) "
                         "so you can see which index is which. Render it with render_3mf.py.")
    ap.add_argument("--obj", action="store_true")
    ap.add_argument("--encoding", choices=["colorgroup", "basematerials"], default="colorgroup")
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache) if args.cache else out.parent / "seg_cache"
    palette = np.array([hex_to_rgb(h) for h in args.palette.split(",") if h.strip()], dtype=np.float64)

    # ---- color source, normalized
    s = trimesh.load(args.input, process=False)
    cm = s.to_geometry() if isinstance(s, trimesh.Scene) else s
    reorient(cm, args.up_axis, "input")
    cm.apply_scale(args.height / cm.extents[2])
    seat(cm)
    vcol_src = np.asarray(cm.visual.to_color().vertex_colors)[:, :3].astype(np.float64)

    # ---- watertight geometry, identical normalization, colors transferred on
    gs = trimesh.load(args.geometry, process=False)
    mesh = gs.to_geometry() if isinstance(gs, trimesh.Scene) else gs
    reorient(mesh, args.geometry_up_axis, "geometry")
    mesh.apply_scale(cm.extents[2] / mesh.extents[2])
    seat(mesh)
    _, idx = cKDTree(cm.vertices).query(mesh.vertices, k=1)
    vcol = vcol_src[idx]
    print(f"Geometry {Path(args.geometry).name}: {len(mesh.vertices)} verts, "
          f"{len(mesh.faces)} faces, watertight={mesh.is_watertight}, bodies={mesh.body_count}")

    # ---- per-vertex baseline (what colorize_3mf.py would do) — used for the mixed-part fallback
    feat = to_feature(vcol, args.color_space, args.luma_weight)
    cent = to_feature(palette, args.color_space, args.luma_weight)
    vlabel = assign_nearest(feat, cent)
    if args.black_chroma > 0:
        lab = srgb_to_lab(vcol)
        chroma = np.hypot(lab[:, 1], lab[:, 2])
        di = int(np.argmin(srgb_to_lab(palette)[:, 0]))
        keep = [i for i in range(len(palette)) if i != di]
        bright = np.array(keep)[assign_nearest(feat, to_feature(palette[keep], args.color_space,
                                                                args.luma_weight))]
        gated = chroma >= args.black_chroma          # still colourful => cannot be black
        moved = int((gated & (vlabel == di)).sum())
        vlabel = np.where(gated, bright, vlabel)
        print(f"Black chroma gate <{args.black_chroma}: {moved} verts "
              f"({100*moved/len(vcol):.1f}%) pulled out of black")
    base_face = np.array([np.bincount(r, minlength=len(palette)).argmax() for r in vlabel[mesh.faces]])

    # ---- segmentation -> face labels
    print(f"Segmenting (granularity={args.granularity})...")
    parts = load_parts(segment(mesh, cache, args.granularity, api(os.environ["TRIPO_API_KEY"])))
    plab, missed = label_faces(mesh, parts)
    print(f"  {len(parts)} parts; {missed} faces ({100*missed/len(mesh.faces):.2f}%) "
          f"unclaimed -> nearest neighbour")

    # ---- one decision per part, on its median color
    face_idx = base_face.copy()
    flat = mixed = 0
    rows = []
    for pid in range(len(parts)):
        fsel = plab == pid
        if not fsel.any():
            continue
        vsel = np.unique(mesh.faces[fsel])
        med = np.median(vcol[vsel], axis=0)
        slot = int(assign_nearest(to_feature(med[None, :], args.color_space, args.luma_weight),
                                 to_feature(palette, args.color_space, args.luma_weight))[0])
        homog = float((vlabel[vsel] == slot).mean())
        if homog >= args.mixed_frac:
            face_idx[fsel] = slot
            flat += 1
            mode = "flat"
        else:
            mixed += 1
            mode = "per-vertex"
        rows.append((int(fsel.sum()), rgb_to_hex(med), rgb_to_hex(palette[slot]), homog, mode))

    rows.sort(key=lambda r: -r[0])
    print(f"\n{'faces':>9} {'%':>6}  {'median':8} -> {'slot':8} {'homog':>6}  mode")
    for n, med, slotc, homog, mode in rows:
        print(f"{n:9d} {100*n/len(mesh.faces):5.1f}%  {med:8} -> {slotc:8} {homog:5.0%}  {mode}")
    print(f"\n{flat} parts flattened, {mixed} kept per-vertex (mixed-frac={args.mixed_frac})")

    # ---- parts map: one distinct colour per part, for reading indices off a render
    if args.parts_map:
        pm = Path(args.parts_map)
        golden = 0.61803398875
        wheel = np.array([[*(255 * np.array(__import__("colorsys").hsv_to_rgb(
            (i * golden) % 1.0, 0.55 + 0.35 * (i % 2), 0.95 - 0.30 * (i % 3))))]
            for i in range(len(parts))])
        write_3mf(mesh, plab, wheel, pm, encoding=args.encoding)
        print(f"Wrote parts map {pm} ({len(parts)} parts)")
        for pid in range(len(parts)):
            fsel = plab == pid
            if fsel.any():
                zc = mesh.triangles_center[fsel][:, 2]
                print(f"  part {pid:2d}  {rgb_to_hex(wheel[pid])}  {int(fsel.sum()):8d} faces  "
                      f"z {zc.min():6.1f}-{zc.max():6.1f} mm")

    # ---- explicit per-part overrides (hand painting)
    for spec in args.part:
        k, _, v = spec.partition("=")
        pid = int(k)
        c = np.array(hex_to_rgb(v), dtype=np.float64)
        hit = np.where((np.round(palette) == np.round(c)).all(1))[0]
        if len(hit):
            slot = int(hit[0])
        else:
            palette = np.vstack([palette, c])
            slot = len(palette) - 1
        n = int((plab == pid).sum())
        face_idx[plab == pid] = slot
        print(f"Override: part {pid} -> {rgb_to_hex(c)} ({n} faces)")

    print("\nFace distribution per color:")
    for i in range(len(palette)):
        n = int((face_idx == i).sum())
        print(f"  [{i}] {rgb_to_hex(palette[i])}  {n:8d} faces ({100*n/len(face_idx):5.1f}%)")
    changed = 100 * (face_idx != base_face).mean()
    print(f"\n{changed:.1f}% of faces differ from the per-vertex (colorize_3mf) result")

    write_3mf(mesh, face_idx, palette, out, encoding=args.encoding)
    print(f"Wrote {out}")
    if args.obj:
        write_obj_mtl(mesh, face_idx, palette, out)
        print(f"Wrote {out.with_suffix('.obj')} + .mtl")


if __name__ == "__main__":
    main()
