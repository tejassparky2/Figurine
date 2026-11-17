#!/usr/bin/env python3
"""Bake a textured GLB into an N-color 3MF that slicers (Bambu / Orca / Snapmaker) can read.

Why: Tripo's `convert_model` to 3MF is geometry-only (drops texture), and trimesh's 3MF export
also drops color. The model's color only lives in the GLB texture. This tool samples that texture,
quantizes it to N flat colors, and writes a 3MF using the standard 3MF Materials extension
(`<m:colorgroup>` with a per-triangle color index) so each region maps to a filament.

The N flat colors come from k-means here, NOT from Tripo — so the result is lighting-independent
and has exactly N solid colors (the project goal). See docs/auto_coloring.md.

Usage:
  python scripts/colorize_3mf.py <input.glb> -o <output.3mf> -n 5
  python scripts/colorize_3mf.py <input.glb> -o <out.3mf> --palette "#1a1a1a,#7a7f86,#c98a5e,#3b2a1d"
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual import TextureVisuals


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore


def rgb_to_hex(c) -> str:
    return "#%02x%02x%02x" % (int(c[0]), int(c[1]), int(c[2]))


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0..255) -> CIE Lab (D65)."""
    a = rgb / 255.0
    lin = np.where(a > 0.04045, ((a + 0.055) / 1.055) ** 2.4, a / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = (lin @ M.T) / np.array([0.95047, 1.0, 1.08883])
    e, k = 0.008856, 903.3
    f = np.where(xyz > e, np.cbrt(xyz), (k * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def to_feature(rgb: np.ndarray, color_space: str, luma_weight: float) -> np.ndarray:
    """Clustering feature space. 'lab' with luma_weight<1 makes clustering ignore shading
    (lit vs shadowed skin stay together) while chroma still separates real colors."""
    if color_space == "lab":
        lab = srgb_to_lab(rgb)
        lab[:, 0] *= luma_weight
        return lab
    return rgb.astype(np.float64)


def kmeans(X: np.ndarray, k: int, iters: int = 30, seed: int = 0) -> np.ndarray:
    """Tiny k-means; returns k centroids. Fit on X (subsample beforehand for speed)."""
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)].astype(np.float64)
    for _ in range(iters):
        d = ((X[:, None, :] - C[None]) ** 2).sum(-1)
        lab = d.argmin(1)
        newC = np.array([X[lab == j].mean(0) if np.any(lab == j) else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return C


def assign_nearest(X: np.ndarray, C: np.ndarray, chunk: int = 100_000) -> np.ndarray:
    """Nearest-centroid label for every row of X, chunked to bound memory."""
    out = np.empty(len(X), dtype=np.int32)
    for i in range(0, len(X), chunk):
        x = X[i:i + chunk]
        d = ((x[:, None, :] - C[None]) ** 2).sum(-1)
        out[i:i + chunk] = d.argmin(1)
    return out


def write_3mf(mesh: trimesh.Trimesh, face_idx: np.ndarray, palette: np.ndarray, out_path: Path,
              encoding: str = "basematerials"):
    """Write a colored 3MF with a per-triangle color index.

    encoding="basematerials" (default): core 3MF <basematerials> — each color is a named print
      material, which Bambu/Orca/Prusa bind to filament slots. This is the multi-material standard.
    encoding="colorgroup": material-extension <m:colorgroup> — arbitrary display colors; less
      reliably mapped to filaments by slicers.
    """
    V = mesh.vertices
    F = mesh.faces
    NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    NS_MAT = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"

    vlines = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in V)
    tlines = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}" p1="{p}"/>'
        for (a, b, c), p in zip(F, face_idx)
    )

    if encoding == "basematerials":
        group = (
            '<basematerials id="2">'
            + "".join(f'<base name="Color{i+1}" displaycolor="{rgb_to_hex(c)}ff"/>'
                      for i, c in enumerate(palette))
            + '</basematerials>'
        )
        model_open = f'<model unit="millimeter" xml:lang="en-US" xmlns="{NS_CORE}">'
    elif encoding == "colorgroup":
        group = (
            '<m:colorgroup id="2">'
            + "".join(f'<m:color color="{rgb_to_hex(c)}"/>' for c in palette)
            + '</m:colorgroup>'
        )
        model_open = f'<model unit="millimeter" xml:lang="en-US" xmlns="{NS_CORE}" xmlns:m="{NS_MAT}">'
    else:
        raise ValueError(f"unknown encoding {encoding!r}")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n' + model_open + '\n'
        '<resources>\n' + group + '\n'
        '<object id="1" type="model" pid="2" pindex="0">\n'
        '<mesh>\n'
        '<vertices>' + vlines + '</vertices>\n'
        '<triangles>' + tlines + '</triangles>\n'
        '</mesh>\n</object>\n</resources>\n'
        '<build><item objectid="1"/></build>\n</model>\n'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    )

    import zipfile
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", xml)


def write_obj_mtl(mesh: trimesh.Trimesh, face_idx: np.ndarray, palette: np.ndarray, out_path: Path):
    """Write OBJ + MTL with N materials (most reliable face-color import in Bambu Studio).
    Faces are grouped by material with `usemtl`. Writes <out>.obj and <out>.mtl."""
    out_path = out_path.with_suffix(".obj")
    mtl_path = out_path.with_suffix(".mtl")
    V = mesh.vertices
    F = mesh.faces

    mtl = ["# generated by colorize_3mf.py"]
    for i, c in enumerate(palette):
        r, g, b = (c / 255.0)
        mtl += [f"newmtl Color{i+1}", f"Kd {r:.4f} {g:.4f} {b:.4f}", "Ka 0 0 0", "d 1", "illum 1"]
    mtl_path.write_text("\n".join(mtl) + "\n")

    lines = [f"mtllib {mtl_path.name}"]
    lines += [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in V]
    order = np.argsort(face_idx, kind="stable")  # group faces by material
    cur = -1
    for fi in order:
        m = int(face_idx[fi])
        if m != cur:
            lines.append(f"usemtl Color{m+1}")
            cur = m
        a, b, c = F[fi] + 1  # OBJ is 1-indexed
        lines.append(f"f {a} {b} {c}")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out_path} + {mtl_path.name} ({len(palette)} materials)")


def render_preview(mesh, vlabel, palette, out_png: Path, W=300, H=440, pad=14, ss=3):
    """Clean software render (front-face | side) — disk-splat each vertex with proper occlusion,
    supersampled then downscaled. Good enough to judge fine detail like beard/eyebrows.
    Assumes the figure faces +X (Tripo convention after Z-up)."""
    from PIL import Image
    V = mesh.vertices
    qcol = palette[vlabel].astype(np.uint8)
    Wf, Hf, P = W * ss, H * ss, pad * ss
    offs = [(ox, oy) for ox in (-1, 0, 1) for oy in (-1, 0, 1)]  # 3x3 disk

    def view(hax, vax, dax, flip_h=False):
        x, y, d = V[:, hax], V[:, vax], V[:, dax]
        sx = -x if flip_h else x
        px = ((sx - sx.min()) / np.ptp(sx) * (Wf - 2 * P) + P).astype(int)
        py = (Hf - 1 - ((y - y.min()) / np.ptp(y) * (Hf - 2 * P) + P)).astype(int)
        PX = np.concatenate([np.clip(px + ox, 0, Wf - 1) for ox, _ in offs])
        PY = np.concatenate([np.clip(py + oy, 0, Hf - 1) for _, oy in offs])
        DD = np.tile(d, len(offs))
        COL = np.tile(qcol, (len(offs), 1))
        order = np.argsort(DD)  # far first, nearest written last (occlusion)
        img = np.full((Hf, Wf, 3), 255, np.uint8)
        img[PY[order], PX[order]] = COL[order]
        return Image.fromarray(img).resize((W, H), Image.LANCZOS)

    front = view(1, 2, 0)        # camera +X: look at the face
    side = view(0, 2, 1)         # camera +Y: side profile
    combo = Image.new("RGB", (2 * W, H), "white")
    combo.paste(front, (0, 0))
    combo.paste(side, (W, 0))
    combo.save(out_png)
    print(f"Wrote preview {out_png} (front-face | side)")


def reorient(m: trimesh.Trimesh, mode: str, label: str):
    """Rotate `m` so that its up-axis becomes +Z, which is what slicers want.

    `mode='auto'` keeps the historical guess: whichever axis is longest is assumed to be up.
    That holds for a standing figure but fails for any subject longer than it is tall — a
    motorcycle's longest axis is its length, so 'auto' lays it on its tail and --height then
    scales the length instead of the height. Pass the axis explicitly for those.
    """
    axis = "xyz"[int(np.argmax(m.extents))] if mode == "auto" else mode
    if axis == "z":
        return  # already Z-up
    rot = [1, 0, 0] if axis == "y" else [0, 1, 0]
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, rot))
    print(f"Reoriented {label} {axis.upper()}-up -> Z-up" + (" (auto)" if mode == "auto" else ""))


def main():
    ap = argparse.ArgumentParser(description="Quantize a textured GLB into an N-color 3MF")
    ap.add_argument("input", help="input GLB (textured) — used as the color source")
    ap.add_argument("-o", "--output", required=True, help="output 3MF path")
    ap.add_argument("--geometry", help="optional watertight mesh (e.g. Tripo convert_model 3MF) to use "
                    "for OUTPUT geometry; colors are transferred onto it from `input` by nearest vertex. "
                    "Use this when the textured GLB is non-watertight but a clean convert 3MF exists.")
    ap.add_argument("-n", "--n-colors", type=int, default=5, help="number of filament colors (default 5)")
    ap.add_argument("--palette", help="comma-separated hex colors to snap to (overrides -n / k-means)")
    ap.add_argument("--height", type=float, help="scale model to this height in mm (Z extent)")
    ap.add_argument("--fit-sample", type=int, default=40_000, help="vertices sampled for k-means fit")
    ap.add_argument("--color-space", choices=["rgb", "lab"], default="rgb",
                    help="clustering space. 'lab' + low --luma-weight reduces shading-induced splits")
    ap.add_argument("--luma-weight", type=float, default=1.0,
                    help="(lab only) weight on lightness; <1 makes clustering ignore shading (try 0.3-0.5)")
    ap.add_argument("--dark-below", type=float,
                    help="(palette only) LAB lightness floor: vertices darker than this snap to the "
                         "darkest palette color regardless of hue. Fixes warm-dark regions (hair, "
                         "boots) wrongly snapping to skin. Try ~38.")
    ap.add_argument("--black-chroma", type=float, default=0.0,
                    help="(palette only) a vertex may take the darkest palette color only if its "
                         "LAB chroma is below this. Baked shading is multiplicative, so it drives "
                         "lightness AND chroma toward zero — a shaded garment stays chromatic while "
                         "real black sits at chroma ~0. Fixes dark creases (chin, armpits, folds) "
                         "bleeding into black on muted mid-tone clothing. Try 8. Combines with "
                         "--dark-below: black then needs to be both dark and achromatic. "
                         "See docs/auto_coloring.md EXP-022.")
    ap.add_argument("--open", action="append", default=[], metavar="#HEX=N",
                    help="morphological opening on one palette colour: delete any region of it "
                         "thinner than 2N faces, keeping thicker regions at their exact original "
                         "boundary. The fix for the light rim that texture filtering and baked "
                         "specular highlights leave along every hairline, brow and edge. Repeatable. "
                         "Try '#F0E9DC=6'. A majority filter does not work here — the band is ~10 "
                         "faces wide, not 1.")
    ap.add_argument("--floor-color", help="hex color to force onto the bottom band of the model "
                    "(see --floor-frac). Use for shoes that Tripo renders skin-toned and so won't "
                    "snap to a shoe color: the feet are the lowest geometry, so a height band catches "
                    "them. Only non-dark (e.g. skin) verts in the band are recolored, so a dark skirt "
                    "hem stays dark. Added to the palette if not already present.")
    ap.add_argument("--floor-frac", type=float, default=0.05,
                    help="fraction of model height (from the bottom) the --floor-color band covers "
                         "(default 0.05). Raise to catch ankles/higher shoes, lower to catch just toes.")
    ap.add_argument("--preview", help="also write a front|back preview PNG to this path")
    ap.add_argument("--encoding", choices=["basematerials", "colorgroup"], default="colorgroup",
                    help="3MF color encoding. colorgroup is what Bambu actually reads (verified); "
                         "basematerials does NOT show color in Bambu Studio.")
    ap.add_argument("--obj", action="store_true",
                    help="also write OBJ+MTL — best face-color import in Bambu (verified, crispest borders)")
    ap.add_argument("--up-axis", choices=["auto", "x", "y", "z"], default="auto",
                    help="which axis of the INPUT (textured GLB) is 'up' and should become +Z. "
                         "'auto' (default) guesses the longest axis, which is right for a standing "
                         "figure but WRONG for anything longer than it is tall (a vehicle): the "
                         "length gets stood on end. glTF is Y-up, so pass 'y' for those.")
    ap.add_argument("--geometry-up-axis", choices=["auto", "x", "y", "z"], default="auto",
                    help="same, for --geometry. Tripo's convert_model 3MF is already Z-up, so pass "
                         "'z' when the auto guess would rotate it (i.e. long subjects).")
    args = ap.parse_args()

    scene = trimesh.load(args.input, process=False)
    mesh = scene.to_geometry() if isinstance(scene, trimesh.Scene) else scene
    assert isinstance(mesh, trimesh.Trimesh), "expected a single triangular mesh"
    if not isinstance(mesh.visual, TextureVisuals):
        print("Warning: input has no texture; colors may be flat.", file=sys.stderr)

    reorient(mesh, args.up_axis, "input")

    if args.height:
        mesh.apply_scale(args.height / mesh.extents[2])

    # sit on the bed (min Z = 0) and center in X/Y
    mn = mesh.bounds[0]
    mesh.apply_translation([-(mesh.bounds[0][0] + mesh.bounds[1][0]) / 2,
                            -(mesh.bounds[0][1] + mesh.bounds[1][1]) / 2,
                            -mn[2]])

    # per-vertex colors from texture
    vcol = np.asarray(mesh.visual.to_color().vertex_colors)[:, :3].astype(np.float64)  # type: ignore[union-attr]

    # Optional: swap to a watertight geometry mesh, transferring the texture colors onto it.
    # The textured GLB is the raw (non-watertight) model; the convert_model 3MF is the repaired,
    # watertight, single-body mesh but arrives flat-gray. They share the same coordinate frame after
    # identical normalization, so a nearest-vertex lookup transfers color losslessly (≈0mm).
    if args.geometry:
        from scipy.spatial import cKDTree
        # process=False: load the convert_model mesh exactly as authored. process=True re-welds
        # near-duplicate vertices, and on some models that weld makes an arriving-watertight mesh
        # non-manifold (krishna: 737893->737892 verts, 6 valence-2 edges -> 3 valence-4 edges out
        # of 2.21M) — and since this mesh is what we write out, that lands in the shipped 3MF.
        # Cosmetic in practice (Bambu auto-repairs it), but free to avoid. See EXP-020.
        gscene = trimesh.load(args.geometry, process=False)
        geom = gscene.to_geometry() if isinstance(gscene, trimesh.Scene) else gscene
        assert isinstance(geom, trimesh.Trimesh), "expected a single triangular geometry mesh"
        reorient(geom, args.geometry_up_axis, "geometry")
        geom.apply_scale(mesh.extents[2] / geom.extents[2])  # match the (already normalized) color mesh
        geom.apply_translation([-(geom.bounds[0][0] + geom.bounds[1][0]) / 2,
                                -(geom.bounds[0][1] + geom.bounds[1][1]) / 2,
                                -geom.bounds[0][2]])
        _, idx = cKDTree(mesh.vertices).query(geom.vertices, k=1)
        vcol = vcol[idx]
        mesh = geom
        print(f"Transferred color onto geometry {Path(args.geometry).name}: "
              f"{len(mesh.vertices)} verts, watertight={mesh.is_watertight}, bodies={mesh.body_count}")

    feat = to_feature(vcol, args.color_space, args.luma_weight)  # clustering metric

    if args.palette:
        palette = np.array([hex_to_rgb(h) for h in args.palette.split(",") if h.strip()], dtype=np.float64)
        centroids = to_feature(palette, args.color_space, args.luma_weight)
        vlabel = assign_nearest(feat, centroids)
        print(f"Snapping to {len(palette)} given colors: {[rgb_to_hex(c) for c in palette]}")

        if args.dark_below is not None or args.black_chroma > 0:
            # Two ways to keep things out of the darkest slot, and they compose.
            #
            # --dark-below is a *forcing* rule: any vertex darker than the cutoff (LAB L) becomes
            # the darkest color regardless of hue, and everything else snaps among the remaining
            # colors. Hue-based snapping can't separate warm-dark regions (hair, boots) from skin —
            # same hue, only darker — so a brightness cutoff is the reliable separator.
            #
            # --black-chroma is a *gating* rule: black stays a normal nearest-neighbour candidate,
            # but only vertices that are genuinely achromatic may take it. Baked ambient occlusion
            # is multiplicative, so it pulls lightness AND chroma toward zero, aiming shaded pixels
            # straight at the black centroid; measured across models, real black sits at chroma ~0-1
            # while shaded garments keep chroma 8-30. Note --luma-weight cannot substitute for this
            # and in fact makes it marginally worse — black is at chroma 0, so down-weighting
            # lightness helps it capture desaturated shadow. EXP-022.
            lab_v = srgb_to_lab(vcol)
            dark_idx = int(np.argmin(srgb_to_lab(palette)[:, 0]))
            keep = [i for i in range(len(palette)) if i != dark_idx]
            cent = to_feature(palette[keep], args.color_space, args.luma_weight)
            bright = np.array(keep)[assign_nearest(feat, cent)]

            if args.dark_below is not None:
                allow = lab_v[:, 0] < args.dark_below
                how = f"dark floor L<{args.dark_below}"
            else:
                allow = vlabel == dark_idx          # whatever nearest-neighbour already chose
                how = "nearest-neighbour"
            if args.black_chroma > 0:
                allow &= np.hypot(lab_v[:, 1], lab_v[:, 2]) < args.black_chroma
                how += f" AND chroma<{args.black_chroma}"

            pulled = int(((vlabel == dark_idx) & ~allow).sum())
            vlabel = np.where(allow, dark_idx, bright)
            print(f"  {rgb_to_hex(palette[dark_idx])} gate ({how}): {int(allow.sum())} verts kept, "
                  f"{pulled} ({100*pulled/len(vcol):.1f}%) pulled out")
    else:
        rng = np.random.default_rng(0)
        sample = feat[rng.choice(len(feat), min(args.fit_sample, len(feat)), replace=False)]
        centroids = kmeans(sample, args.n_colors)
        vlabel = assign_nearest(feat, centroids)
        # displayed color = true mean RGB of each cluster (not the feature-space centroid)
        palette = np.array([vcol[vlabel == k].mean(0) if np.any(vlabel == k) else vcol[0]
                            for k in range(args.n_colors)])
        print(f"k-means ({args.color_space}, luma_weight={args.luma_weight}) -> "
              f"{[rgb_to_hex(c) for c in palette]}")
    # Optional: force the bottom band to a given color (e.g. white shoes that Tripo painted skin-toned).
    # Feet are the lowest geometry; recolor only non-dark verts in the band so a dark skirt hem is kept.
    if args.floor_color:
        fc = np.array(hex_to_rgb(args.floor_color), dtype=np.float64)
        match = np.where((np.round(palette) == np.round(fc)).all(1))[0]
        if len(match):
            floor_idx = int(match[0])
        else:
            palette = np.vstack([palette, fc])
            floor_idx = len(palette) - 1
        z = mesh.vertices[:, 2]
        dark_idx = int(np.argmin(srgb_to_lab(palette)[:, 0]))
        band = (z < args.floor_frac * z.max()) & (vlabel != dark_idx)
        vlabel = np.where(band, floor_idx, vlabel)
        print(f"Floor band z<{args.floor_frac:.2f}*H -> {rgb_to_hex(fc)}: {int(band.sum())} verts recolored")

    # face color = majority label among its 3 vertices
    fl = vlabel[mesh.faces]
    face_idx = np.array([np.bincount(row, minlength=len(palette)).argmax() for row in fl], dtype=np.int32)

    # Optional: morphological opening on one colour, to erase boundary fringes.
    #
    # Every colour boundary carries a band of a third colour. Two causes, both unavoidable upstream:
    # the texture is far lower resolution than the mesh (a 2K texture on a 1.5M-face model is ~3
    # faces per texel, and filtering blends across the seam), and the source art is a glossy render
    # whose baked specular rims sit bright and near-neutral over dark regions. Both land on whichever
    # palette entry is nearest the *midpoint*, which is the lightest low-chroma slot — so worstsister
    # fringed white along every hairline, brow and eye.
    #
    # A majority filter does NOT fix this: the band is ~10 faces wide, not 1, so the filter only
    # roughens its edges (measured: white 312312 -> 312165 faces, components 842 -> 1777, worse).
    # Opening — erode N, then dilate N back within the original mask — deletes any region thinner
    # than 2N faces while restoring thicker ones to their exact original boundary. Small-but-chunky
    # regions like eye whites and teeth survive; long thin rims do not.
    #
    # Removed faces are re-snapped against the palette minus this colour using their own vertex
    # colours, so they take the colour they actually are rather than a neighbour's guess.
    for spec in args.open:
        hexc, _, n_s = spec.partition("=")
        n = int(n_s)
        want = np.array(hex_to_rgb(hexc), dtype=np.float64)
        hit = np.where((np.round(palette) == np.round(want)).all(1))[0]
        if not len(hit):
            sys.exit(f"--open {spec}: {hexc} is not in the palette")
        t = int(hit[0])
        adj = mesh.face_adjacency
        mask = face_idx == t
        cur = mask.copy()
        for _ in range(n):                      # erode: drop faces touching a non-target face
            out = np.zeros(len(face_idx), bool)
            np.logical_or.at(out, adj[:, 0], ~cur[adj[:, 1]])
            np.logical_or.at(out, adj[:, 1], ~cur[adj[:, 0]])
            cur &= ~out
        for _ in range(n):                      # dilate back, never beyond the original region
            grow = np.zeros(len(face_idx), bool)
            np.logical_or.at(grow, adj[:, 0], cur[adj[:, 1]])
            np.logical_or.at(grow, adj[:, 1], cur[adj[:, 0]])
            cur = (cur | grow) & mask
        gone = mask & ~cur
        if gone.any():
            keep = [i for i in range(len(palette)) if i != t]
            fv = vcol[mesh.faces[gone]].mean(axis=1)
            face_idx[gone] = np.array(keep)[assign_nearest(
                to_feature(fv, args.color_space, args.luma_weight),
                to_feature(palette[keep], args.color_space, args.luma_weight))]
        print(f"Opening {rgb_to_hex(palette[t])} radius {n}: removed {int(gone.sum())} faces "
              f"({100*gone.sum()/max(int(mask.sum()),1):.1f}% of that colour) in bands <{2*n} faces wide")

    # report distribution
    counts = np.bincount(face_idx, minlength=len(palette))
    print("Face distribution per color:")
    for i, (c, n) in enumerate(zip(palette, counts)):
        print(f"  [{i}] {rgb_to_hex(c)}  {n:>8} faces ({100*n/len(face_idx):4.1f}%)")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_3mf(mesh, face_idx, palette, out, encoding=args.encoding)
    print(f"\nWrote {out} ({out.stat().st_size/1e6:.1f} MB, {len(mesh.faces)} triangles, "
          f"{len(palette)} colors, encoding={args.encoding})")

    if args.obj:
        write_obj_mtl(mesh, face_idx, palette, out)

    if args.preview:
        render_preview(mesh, vlabel, palette, Path(args.preview))


if __name__ == "__main__":
    main()
