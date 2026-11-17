#!/usr/bin/env python3
"""Colour a figurine from the approved photo itself, not only from the 3D model's texture.

The image-to-3D texture (Tripo/Meshy) is a re-painting of the approved render: it shifts hues
(Meshy skin comes out orange next to the photo), bakes its own shading, and invents what the
photo never showed. This tool projects the approved PNG onto every surface the photo actually
shows, and falls back to the texture only where the photo cannot see.

    approved PNG ──┐
                   ├─ register front silhouette (scale/shift, IoU)  ─┐
    geometry ──────┤                                                ├─ visible verts: photo colour
                   └─ Blender BVH ray cast toward camera (visibility)┘   → snap to --palette
                   └─ dense optical flow: texture front render → photo (feature alignment)
    textured GLB ───────────────────────────────────────────────────── hidden verts: texture colour
                                                                         → snap to --texture-palette
                                                                         (same slots, same order)

Why the flow step exists: image-to-3D does not rebuild the photo pixel-for-pixel. On family-of-3
the silhouettes matched at IoU 0.96 yet glasses, beards and collars sat a median 29 px (p90 56 px)
away from where the photo has them, so a rigid projection painted skin onto hair and ghosted the
glasses. The model's own texture *is* aligned to its geometry and looks like the photo, so
optical flow from a front render of the texture to the photo recovers the per-pixel
correspondence (grey NCC 0.58 -> 0.90). --no-flow turns it off for comparison.

Both palettes name the SAME filament slots in the same order. --palette is the filament colour
as it appears in the photo (and is what gets written); --texture-palette is where that filament
sits in the texture's colour space, used only to snap the hidden vertices. Slot i is slot i.

Example (family-of-3):
    python3 scripts/photo_project_colorize.py projects/fam/source/family_b.glb \
      --geometry projects/fam/models/family_b_geometry.ply --photo projects/fam/approved/family.png \
      --palette "#C98250,#1E1915,#EDE3D8,#282D48,#A6BDBD" \
      --texture-palette "#D98A50,#1C1814,#EFE9E1,#1C1E4E,#8BA8B5" \
      --up-axis y --geometry-up-axis y --height 120 -o projects/fam/models/family_b_photo.3mf --obj

Then verify with render_3mf.py as usual (never with a splat preview).
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from colorize_3mf import (assign_nearest, hex_to_rgb, reorient, rgb_to_hex,  # noqa: E402
                          srgb_to_lab, to_feature, write_3mf, write_obj_mtl)

HERE = Path(__file__).parent


def find_blender(explicit):
    for c in [explicit, shutil.which("blender"), "/Applications/Blender.app/Contents/MacOS/Blender"]:
        if c and Path(c).exists():
            return c
    sys.exit("Blender not found — pass --blender /path/to/blender")


def load_normalized(args):
    """Same normalisation as colorize_3mf.py: reorient, scale to --height, centre X/Y, z=0."""
    scene = trimesh.load(args.input, process=False)
    mesh = scene.to_geometry() if isinstance(scene, trimesh.Scene) else scene
    reorient(mesh, args.up_axis, "input")
    if args.height:
        mesh.apply_scale(args.height / mesh.extents[2])
    mesh.apply_translation([-(mesh.bounds[0][0] + mesh.bounds[1][0]) / 2,
                            -(mesh.bounds[0][1] + mesh.bounds[1][1]) / 2, -mesh.bounds[0][2]])
    vcol = np.asarray(mesh.visual.to_color().vertex_colors)[:, :3].astype(np.float64)
    if not args.geometry:
        return mesh, vcol
    g = trimesh.load(args.geometry, process=False)
    geom = g.to_geometry() if isinstance(g, trimesh.Scene) else g
    reorient(geom, args.geometry_up_axis, "geometry")
    geom.apply_scale(mesh.extents[2] / geom.extents[2])
    geom.apply_translation([-(geom.bounds[0][0] + geom.bounds[1][0]) / 2,
                            -(geom.bounds[0][1] + geom.bounds[1][1]) / 2, -geom.bounds[0][2]])
    d, idx = cKDTree(mesh.vertices).query(geom.vertices, k=1)
    print(f"Texture colour -> geometry: {len(geom.vertices):,} verts, NN dist mean {d.mean():.4f} "
          f"max {d.max():.4f} mm, watertight={geom.is_watertight}")
    return geom, vcol[idx]


def photo_mask(img, thresh):
    a = np.asarray(img).astype(np.int16)
    fg = a.min(axis=2) < thresh
    fg = ndimage.binary_closing(fg, iterations=2)
    fg = ndimage.binary_fill_holes(fg)
    lab, n = ndimage.label(fg)
    if n > 1:
        fg = lab == (np.bincount(lab.ravel())[1:].argmax() + 1)
    return fg


def silhouette(xz, p, shape, ds):
    """Rasterise projected vertices into a filled mask at 1/ds resolution."""
    sx, sz, tx, ty = p
    H, W = shape
    c = ((sx * xz[:, 0] + tx) / ds).astype(np.int32)
    r = ((ty - sz * xz[:, 1]) / ds).astype(np.int32)
    ok = (c >= 0) & (c < W) & (r >= 0) & (r < H)
    m = np.zeros(shape, bool)
    m[r[ok], c[ok]] = True
    m = ndimage.binary_closing(m, iterations=2)
    return ndimage.binary_fill_holes(m)


def register(xz, fg, ds=4, verbose=True):
    """Fit photo_px = (sx*x + tx, ty - sz*z) by maximising silhouette IoU (coordinate descent)."""
    rows, cols = np.nonzero(fg)
    r0, r1, c0, c1 = rows.min(), rows.max(), cols.min(), cols.max()
    x0, x1 = xz[:, 0].min(), xz[:, 0].max()
    z0, z1 = xz[:, 1].min(), xz[:, 1].max()
    sx, sz = (c1 - c0) / (x1 - x0), (r1 - r0) / (z1 - z0)
    p = np.array([sx, sz, c0 - sx * x0, r1 + sz * z0], float)
    small = fg[::ds, ::ds]
    shape = small.shape

    def iou(q):
        m = silhouette(xz, q, shape, ds)
        return (m & small).sum() / max((m | small).sum(), 1)

    best = iou(p)
    if verbose:
        print(f"Registration init IoU {best:.4f}")
    steps = np.array([0.02 * p[0], 0.02 * p[1], 8.0, 8.0])
    for _ in range(6):
        improved = True
        while improved:
            improved = False
            for k in range(4):
                for sgn in (+1, -1):
                    q = p.copy()
                    q[k] += sgn * steps[k]
                    v = iou(q)
                    if v > best + 1e-5:
                        p, best, improved = q, v, True
        steps /= 2
    if verbose:
        print(f"Registration final IoU {best:.4f}  (sx={p[0]:.3f} sz={p[1]:.3f} px/mm, "
              f"aniso {p[0] / p[1]:.3f}, tx={p[2]:.1f} ty={p[3]:.1f})")
    return p, best


def bilinear(img, c, r):
    H, W = img.shape[:2]
    c = np.clip(c, 0, W - 1.001)
    r = np.clip(r, 0, H - 1.001)
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = (c - c0)[:, None], (r - r0)[:, None]
    return (img[r0, c0] * (1 - fc) * (1 - fr) + img[r0, c0 + 1] * fc * (1 - fr)
            + img[r0 + 1, c0] * (1 - fc) * fr + img[r0 + 1, c0 + 1] * fc * fr)


def snap(col, palette, cs, lw, black_chroma):
    """Nearest palette slot, with the darkest slot gated on low chroma (EXP-022)."""
    lab = srgb_to_lab(col)
    lbl = assign_nearest(to_feature(col, cs, lw), to_feature(palette, cs, lw))
    if black_chroma > 0:
        dark = int(np.argmin(srgb_to_lab(palette)[:, 0]))
        keep = [i for i in range(len(palette)) if i != dark]
        alt = np.array(keep)[assign_nearest(to_feature(col, cs, lw), to_feature(palette[keep], cs, lw))]
        lbl = np.where((lbl == dark) & (np.hypot(lab[:, 1], lab[:, 2]) >= black_chroma), alt, lbl)
    return lbl


def slot_of(palette, hexc):
    hit = np.where((np.round(palette) == np.round(hex_to_rgb(hexc))).all(1))[0]
    if not len(hit):
        sys.exit(f"{hexc} is not in --palette")
    return int(hit[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="textured GLB — colour source for surfaces the photo can't see")
    ap.add_argument("--geometry", help="watertight mesh to write (same model, any trimesh format)")
    ap.add_argument("--photo", required=True, help="approved front-view PNG (white background)")
    ap.add_argument("--palette", required=True, help="filament hexes as they look in the PHOTO")
    ap.add_argument("--texture-palette", help="the same slots as they look in the TEXTURE "
                    "(defaults to --palette)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--height", type=float, default=120)
    ap.add_argument("--up-axis", default="auto", choices=["auto", "x", "y", "z"])
    ap.add_argument("--geometry-up-axis", default="auto", choices=["auto", "x", "y", "z"])
    ap.add_argument("--color-space", default="lab", choices=["rgb", "lab"])
    ap.add_argument("--luma-weight", type=float, default=0.5)
    ap.add_argument("--photo-black-chroma", type=float, default=12,
                    help="photo verts may take the darkest slot only below this LAB chroma")
    ap.add_argument("--texture-black-chroma", type=float, default=20,
                    help="same gate for texture-coloured (hidden) verts")
    ap.add_argument("--min-facing", type=float, default=0.3,
                    help="photo colour only where the normal faces the camera by at least this "
                         "(cos of angle). Grazing surfaces are smeared in the photo.")
    ap.add_argument("--mask-erode", type=int, default=4,
                    help="px to stay inside the photo silhouette (registration slop near the edge)")
    ap.add_argument("--bg-thresh", type=int, default=235, help="photo pixel is background if min "
                    "channel >= this")
    ap.add_argument("--photo-blur", type=float, default=1.0, help="gaussian sigma (px) on the photo")
    ap.add_argument("--open", action="append", default=[], metavar="#HEX=N",
                    help="morphological opening on one palette colour (see colorize_3mf.py)")
    ap.add_argument("--no-flow", action="store_true",
                    help="skip optical-flow feature alignment (rigid silhouette fit only)")
    ap.add_argument("--fb-tol", type=float, default=3.0,
                    help="px: forward-backward flow error above which the photo is not trusted")
    ap.add_argument("--texture-decides", action="append", default=[], metavar="#A/#B",
                    help="two palette colours the photo can't separate (e.g. navy vs black in "
                         "shadow): where photo and texture disagree between them, texture wins")
    ap.add_argument("--keep-small", action="append", default=[], metavar="#HEX=N",
                    help="faces turned HEX by the photo against the texture survive only in "
                         "pieces of <=N faces that touch the darkest slot (keeps eye whites, "
                         "drops forehead shine)")
    ap.add_argument("--obj", action="store_true", help="also write OBJ+MTL")
    ap.add_argument("--blender", help="path to blender (default: on PATH)")
    ap.add_argument("--debug-dir", help="write registration overlay + source masks here")
    args = ap.parse_args()

    palette = np.array([hex_to_rgb(h) for h in args.palette.split(",")], float)
    tpal = (np.array([hex_to_rgb(h) for h in args.texture_palette.split(",")], float)
            if args.texture_palette else palette)
    assert len(tpal) == len(palette), "--texture-palette must have the same slots as --palette"

    mesh, vcol = load_normalized(args)
    V, F = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    N = np.asarray(mesh.vertex_normals)

    # 1. visibility toward a front orthographic camera — Blender BVH ray cast
    blender = find_blender(args.blender)
    with tempfile.TemporaryDirectory() as td:
        np.savez(Path(td) / "m.npz", V=V, F=F, N=N)
        cmd = [blender, "-b", "--factory-startup", "--python", str(HERE / "blender_visibility.py"),
               "--", str(Path(td) / "m.npz"), str(Path(td) / "vis.npy"), "0.0"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if line.startswith("[blender]"):
                print(line)
        if res.returncode or not (Path(td) / "vis.npy").exists():
            sys.exit("Blender visibility pass failed:\n" + res.stdout[-2000:] + res.stderr[-2000:])
        seen = np.load(Path(td) / "vis.npy")          # unoccluded & facing at all
    visible = seen & ((-N[:, 1]) > args.min_facing)    # ...and facing enough to trust the photo

    # 2. register photo <-> model front silhouette
    img = Image.open(args.photo).convert("RGB")
    fg = photo_mask(img, args.bg_thresh)
    xz = V[:, [0, 2]]
    p, iou = register(xz, fg)
    if iou < 0.85:
        print(f"WARNING: silhouette IoU {iou:.3f} is low — the photo may not be the image this "
              "model was generated from, or the pose differs. Check the overlay.", file=sys.stderr)

    # 3. where each vertex lands in the photo: rigid fit, then per-pixel flow correction
    H, W = fg.shape
    cc = p[0] * V[:, 0] + p[2]
    rr = p[3] - p[1] * V[:, 2]
    ci = np.clip(np.round(cc).astype(int), 0, W - 1)
    ri = np.clip(np.round(rr).astype(int), 0, H - 1)
    rend = None
    if not args.no_flow:
        # front render of the model's own texture: splat unoccluded verts, nearest-fill the gaps
        buf = np.zeros((H, W, 3))
        has = np.zeros((H, W), bool)
        buf[ri[seen], ci[seen]] = vcol[seen]
        has[ri[seen], ci[seen]] = True
        sil = silhouette(xz, p, fg.shape, 1)
        _, (ii, jj) = ndimage.distance_transform_edt(~has, return_indices=True)
        rend = buf[ii, jj]
        rend[~sil] = 255
        rend = rend.astype(np.uint8)
        clahe = cv2.createCLAHE(2.0, (8, 8))
        g1 = clahe.apply(cv2.cvtColor(rend, cv2.COLOR_RGB2GRAY))
        g2 = clahe.apply(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY))
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        flow = dis.calc(g1, g2, None)    # render(y,x) ~ photo(y+fy, x+fx)
        bflow = dis.calc(g2, g1, None)   # and back, for the consistency check
        mag = np.hypot(flow[..., 0], flow[..., 1])[sil & fg]
        gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        g2w = cv2.remap(g2, gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_LINEAR)
        m = sil & fg

        def ncc(a, b):
            a, b = a[m].astype(float), b[m].astype(float)
            a -= a.mean(); b -= b.mean()
            return (a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum())
        print(f"Feature flow: median {np.median(mag):.1f}px p90 {np.percentile(mag, 90):.1f}px; "
              f"grey NCC rigid {ncc(g1, g2):.3f} -> flow {ncc(g1, g2w):.3f}")
        fxy = bilinear(flow, cc, rr)
        cc, rr = cc + fxy[:, 0], rr + fxy[:, 1]
        # forward-backward check: where the flow can't find its way back (occlusion boundaries,
        # e.g. a hand over an arm), the correspondence is a guess — keep the texture there
        back = bilinear(bflow, cc, rr)
        fb_ok = np.hypot(fxy[:, 0] + back[:, 0], fxy[:, 1] + back[:, 1]) < args.fb_tol
        print(f"Flow forward-backward consistent (<{args.fb_tol}px): "
              f"{100 * fb_ok[visible].mean():.1f}% of visible verts")
        ci = np.clip(np.round(cc).astype(int), 0, W - 1)
        ri = np.clip(np.round(rr).astype(int), 0, H - 1)

    # 4. sample the photo at each visible vertex
    photo = np.asarray(img).astype(float)
    if args.photo_blur > 0:
        photo = ndimage.gaussian_filter(photo, sigma=(args.photo_blur, args.photo_blur, 0))
    inner = ndimage.binary_erosion(fg, iterations=args.mask_erode)
    use_photo = visible & inner[ri, ci]
    if not args.no_flow:
        use_photo &= fb_ok
    pcol = bilinear(photo, cc[use_photo], rr[use_photo])

    # 5. one label per vertex, both sources speaking the same slot indices
    tlabel = snap(vcol, tpal, args.color_space, args.luma_weight, args.texture_black_chroma)
    vlabel = tlabel.copy()
    plab = snap(pcol, palette, args.color_space, args.luma_weight, args.photo_black_chroma)
    # slot pairs the photo cannot tell apart reliably (navy in shadow vs black): texture decides
    tl = tlabel[use_photo]
    for spec in args.texture_decides:
        a, b = (slot_of(palette, h) for h in spec.split("/"))
        swap = ((plab == a) & (tl == b)) | ((plab == b) & (tl == a))
        plab = np.where(swap, tl, plab)
        print(f"Texture decides {spec}: {int(swap.sum()):,} photo verts deferred to texture")
    vlabel[use_photo] = plab
    print(f"Photo-coloured verts: {int(use_photo.sum()):,} ({100 * use_photo.mean():.1f}%); "
          f"texture fallback: {int((~use_photo).sum()):,}")
    # for --open re-snapping: each vertex's colour in photo space where we have it
    vsrc = vcol.copy()
    vsrc[~use_photo] = palette[vlabel[~use_photo]]  # texture verts: their slot's photo colour
    vsrc[use_photo] = pcol

    def vote(lbl):
        return np.array([np.bincount(row, minlength=len(palette)).argmax() for row in lbl[F]],
                        np.int32)
    face_idx = vote(vlabel)

    # photo specular highlights (forehead shine) read as the light slot. Real light features the
    # photo adds over the texture (eye whites) are small; shine blobs are big. Keep only the
    # small connected pieces of "light slot, where the texture said otherwise".
    if args.keep_small:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        tface = vote(tlabel)
        adj = mesh.face_adjacency
        for spec in args.keep_small:
            hexc, _, n_s = spec.partition("=")
            t, nmax = slot_of(palette, hexc), int(n_s)
            cand = (face_idx == t) & (tface != t)
            e = adj[cand[adj[:, 0]] & cand[adj[:, 1]]]
            g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(F), len(F)))
            _, comp = connected_components(g, directed=False)
            sizes = np.bincount(comp[cand])
            big = cand & (sizes[np.where(cand, comp, 0)] > nmax) if len(sizes) else cand & False
            # an eye white touches a pupil; forehead shine touches only skin
            dark = int(np.argmin(srgb_to_lab(palette)[:, 0]))
            touch = np.zeros(comp.max() + 1, bool)
            for x, y in ((adj[:, 0], adj[:, 1]), (adj[:, 1], adj[:, 0])):
                hit = cand[x] & (face_idx[y] == dark)
                touch[comp[x[hit]]] = True
            lonely = cand & ~big & ~touch[comp]
            print(f"  ...and {int(lonely.sum()):,} faces in small pieces touching no "
                  f"{rgb_to_hex(palette[dark])} (shine, not eyes) reverted")
            big |= lonely
            face_idx[big] = tface[big]
            ids = np.unique(comp[cand])
            top = np.sort(sizes[ids])[::-1][:12] if len(ids) else []
            print(f"Keep-small {hexc}<={nmax}: {len(ids)} pieces (largest: {list(map(int, top))}); "
                  f"reverted {int(big.sum()):,} faces in pieces >{nmax}")

    for spec in args.open:  # same opening as colorize_3mf.py
        hexc, _, n_s = spec.partition("=")
        t = int(np.where((np.round(palette) == np.round(hex_to_rgb(hexc))).all(1))[0][0])
        adj = mesh.face_adjacency
        mask = face_idx == t
        cur = mask.copy()
        for _ in range(int(n_s)):
            out = np.zeros(len(face_idx), bool)
            np.logical_or.at(out, adj[:, 0], ~cur[adj[:, 1]])
            np.logical_or.at(out, adj[:, 1], ~cur[adj[:, 0]])
            cur &= ~out
        for _ in range(int(n_s)):
            grow = np.zeros(len(face_idx), bool)
            np.logical_or.at(grow, adj[:, 0], cur[adj[:, 1]])
            np.logical_or.at(grow, adj[:, 1], cur[adj[:, 0]])
            cur = (cur | grow) & mask
        gone = mask & ~cur
        if gone.any():
            keep = [i for i in range(len(palette)) if i != t]
            fv = vsrc[F[gone]].mean(axis=1)
            face_idx[gone] = np.array(keep)[assign_nearest(
                to_feature(fv, args.color_space, args.luma_weight),
                to_feature(palette[keep], args.color_space, args.luma_weight))]
        print(f"Opening {hexc} radius {n_s}: removed {int(gone.sum())} faces")

    counts = np.bincount(face_idx, minlength=len(palette))
    print("Face distribution per color:")
    for i, (c, n) in enumerate(zip(palette, counts)):
        print(f"  [{i}] {rgb_to_hex(c)}  {n:>8} faces ({100 * n / len(face_idx):4.1f}%)")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_3mf(mesh, face_idx, palette, out, encoding="colorgroup")
    if args.obj:
        write_obj_mtl(mesh, face_idx, palette, out)
    print(f"Wrote {out} ({len(F):,} triangles, {len(palette)} colors)"
          + (f" + {out.with_suffix('.obj').name}" if args.obj else ""))

    if args.debug_dir:
        dd = Path(args.debug_dir)
        dd.mkdir(parents=True, exist_ok=True)
        sil = silhouette(xz, p, fg.shape, 1)
        edge = sil ^ ndimage.binary_erosion(sil, iterations=2)
        ov = np.asarray(img).copy()
        ov[edge] = [255, 0, 255]
        ov[fg ^ ndimage.binary_erosion(fg, iterations=2)] = [0, 200, 255]
        im = Image.fromarray(ov)
        ImageDraw.Draw(im).text((10, 10), f"IoU {iou:.3f}  magenta=model  cyan=photo", fill=(0, 0, 0))
        im.save(dd / f"{out.stem}_registration.png")
        if rend is not None:
            Image.fromarray(rend).save(dd / f"{out.stem}_texture_front.png")
        print(f"Registration overlay -> {dd / (out.stem + '_registration.png')}")


if __name__ == "__main__":
    main()
