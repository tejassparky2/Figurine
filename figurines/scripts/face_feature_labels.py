#!/usr/bin/env python3
"""Measure the facial features on a flat texture render and turn them into clean filament labels.

Run with the face-tools venv (mediapipe):

    ~/.venvs/facetools/bin/python scripts/face_feature_labels.py tex_front.png --window -25,28,60,100 \
        --ppmm 40 --face bride:-25,2 --face groom:3,28 -o labels.npz --debug-dir faceart/

Input is the output of blender_render_textured_front.py: the model's OWN texture, unshaded, front view,
at a known mm scale. That texture is exactly aligned with the sculpt, so a feature found here lands on
the right relief when it is painted onto the mesh — no warping, no registration error.

Per face (crop given in model mm, u range):
  1. MediaPipe Face Landmarker (478 points) finds eye, iris, brow and lip contours.
  2. Feature REGIONS: each eye contour dilated --eye-pad mm (lashes, liner); each brow hull dilated
     --brow-pad mm; the outer-lip contour dilated --lip-pad mm, split into lips (between outer and
     inner contour) and mouth opening (inside the inner contour).
  3. Pixels in each region are classified with simple, explicit rules in CIELAB:
       eyes:  L < --dark-L -> BLACK (iris, pupil, lashes, liner) | light & neutral -> CREAM (white,
              catchlight) | else SKIN
       brows: L < --dark-L -> BLACK | else SKIN
       lips:  red (a* > --red-a) -> RED | light & neutral -> CREAM (teeth) | dark -> BLACK only
              outside the mouth opening (moustache) | else SKIN
       mouth opening: light -> CREAM (teeth) | everything else -> RED  (never black in a mouth)
  4. Each class mask is cleaned in 2D (opening/closing at --smooth mm, holes filled, specks under
     --min-area mm2 dropped) so edges are smooth curves, not texel noise.

Output labels.npz: `label` (H,W) int8 with -1 = untouched, 0..3 = SKIN, BLACK, RED, CREAM; plus the
window/ppmm and per-feature region masks for measurement. Debug PNGs show landmarks and labels.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage.color import rgb2lab
from skimage.draw import polygon as draw_polygon

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

SKIN, BLACK, RED, CREAM = 0, 1, 2, 3
NAMES = ["skin", "black", "red", "cream"]
COLORS = np.array([[240, 170, 120], [30, 25, 22], [220, 20, 10], [246, 224, 196]], np.uint8)

# MediaPipe face-mesh contour indices (subject's left = image right)
EYE_R = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
EYE_L = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466]
BROW_R = [46, 53, 52, 65, 55, 70, 63, 105, 66, 107]
BROW_L = [276, 283, 282, 295, 285, 300, 293, 334, 296, 336]
LIP_OUT = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
LIP_IN = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]


def poly_mask(pts, shape):
    m = np.zeros(shape, bool)
    rr, cc = draw_polygon(pts[:, 1], pts[:, 0], shape)
    m[rr, cc] = True
    return m


def hull_mask(pts, shape):
    from scipy.spatial import ConvexHull
    h = ConvexHull(pts)
    return poly_mask(pts[h.vertices], shape)


def clean(mask, r_px, min_px):
    if r_px >= 1:
        st = ndimage.generate_binary_structure(2, 1)
        mask = ndimage.binary_opening(mask, st, iterations=r_px)
        mask = ndimage.binary_closing(mask, st, iterations=r_px)
    mask = ndimage.binary_fill_holes(mask) if False else mask
    lab, n = ndimage.label(mask)
    if n:
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        keep = np.isin(lab, np.flatnonzero(sizes >= min_px) + 1)
        mask = mask & keep
    return mask


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render")
    ap.add_argument("--window", required=True, help="u0,u1,v0,v1 mm of the render")
    ap.add_argument("--ppmm", type=float, required=True)
    ap.add_argument("--face", action="append", required=True, metavar="NAME:U0,U1",
                    help="crop for one face, in model mm along u")
    ap.add_argument("--model", default=str(Path.home() / ".cache/figurine-models/face_landmarker.task"))
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--debug-dir")
    ap.add_argument("--eye-box", type=float, default=1.4, help="mm around the eye contour searched")
    ap.add_argument("--brow-box", type=float, default=1.6, help="mm around the brow landmarks searched")
    ap.add_argument("--lip-box", type=float, default=1.2, help="mm around the outer lip contour searched")
    ap.add_argument("--dark-L", type=float, default=42)
    ap.add_argument("--red-a", type=float, default=22)
    ap.add_argument("--light-L", type=float, default=60)
    ap.add_argument("--light-C", type=float, default=16, help="max chroma of whites/teeth (skin is ~30)")
    ap.add_argument("--teeth-C", type=float, default=24, help="max chroma of teeth (inside the mouth only)")
    ap.add_argument("--ensure-catch", action="store_true", help="add a catchlight to eyes whose texture has none")
    ap.add_argument("--catch-r", type=float, default=0.42, help="mm radius of a painted catchlight")
    ap.add_argument("--teeth-L", type=float, default=50)
    ap.add_argument("--corner-max", type=float, default=2.0, help="mm2: dark patch touching a mouth below this = mouth")
    ap.add_argument("--iris-L", type=float, default=58, help="inside an eye, darker than this = iris/lash")
    ap.add_argument("--smooth", type=float, default=0.12, help="mm, 2D opening/closing radius")
    ap.add_argument("--min-area", type=float, default=0.15, help="mm2")
    a = ap.parse_args()

    u0, u1, v0, v1 = map(float, a.window.split(","))
    ppmm = a.ppmm
    rgba = np.asarray(Image.open(a.render).convert("RGBA")).astype(float)
    alpha = rgba[..., 3] / 255.0
    rgb = rgba[..., :3] * alpha[..., None] + 255 * (1 - alpha[..., None])   # composite on white
    H, W = rgb.shape[:2]
    lab = rgb2lab(rgb / 255.0)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    C = np.hypot(A, B)

    lm_opts = FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=a.model),
                                    running_mode=RunningMode.IMAGE, num_faces=1,
                                    min_face_detection_confidence=0.2, min_face_presence_confidence=0.2)
    label = np.full((H, W), -1, np.int8)
    regions = {}
    catches = []
    dbg = Image.fromarray(rgb.astype(np.uint8)).copy()
    draw = ImageDraw.Draw(dbg)
    with FaceLandmarker.create_from_options(lm_opts) as det:
        for spec in a.face:
            name, rng = spec.split(":")
            fu0, fu1 = map(float, rng.split(","))
            x0, x1 = int((fu0 - u0) * ppmm), int((fu1 - u0) * ppmm)
            x0, x1 = max(0, x0), min(W, x1)
            crop = np.ascontiguousarray(rgb[:, x0:x1].astype(np.uint8))
            res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=crop))
            if not res.face_landmarks:
                raise SystemExit(f"{name}: no face found in crop u {fu0}..{fu1}")
            P = np.array([[p.x * crop.shape[1] + x0, p.y * crop.shape[0]] for p in res.face_landmarks[0]])
            print(f"{name}: 478 landmarks, face box x {P[:,0].min():.0f}-{P[:,0].max():.0f} "
                  f"y {P[:,1].min():.0f}-{P[:,1].max():.0f} px")
            for i in range(len(P)):
                draw.point(tuple(P[i]), fill=(0, 255, 0))

            def dil(m, mm):
                return ndimage.binary_dilation(m, iterations=max(1, int(round(mm * ppmm))))
            fg = alpha > 0.5
            dark = (L < a.dark_L) & fg
            light = (L > a.light_L) & (C < a.light_C) & fg            # whites/teeth: bright AND neutral
            red = (A > a.red_a) & (L >= 28) & (L < 78) & (np.degrees(np.arctan2(B, A)) < 55) & fg

            def seeded(cand, box, seed):
                """connected components of cand (inside box) that touch seed"""
                lab_, n = ndimage.label(cand & box)
                ids = np.unique(lab_[seed & (lab_ > 0)])
                return np.isin(lab_, ids[ids > 0])

            reg = {}
            # EYES: dark|light shape connected to the iris; box = eye contour hull + eye_box
            for k, (idx, iris) in enumerate(((EYE_L, 473), (EYE_R, 468))):
                box = dil(hull_mask(P[idx], (H, W)), a.eye_box) & fg
                seed = np.zeros((H, W), bool)
                cy, cx = int(P[iris, 1]), int(P[iris, 0])
                rr = int(0.5 * ppmm)
                seed[max(0, cy-rr):cy+rr, max(0, cx-rr):cx+rr] = True
                eye = seeded(dark | light, box, seed)
                eye = ndimage.binary_fill_holes(ndimage.binary_closing(eye, iterations=2))
                lbl = np.full((H, W), -1, np.int8)
                lbl[box & ~dark & ~red] = SKIN                    # clear stray paint around the eye
                lbl[box & red] = SKIN
                lbl[eye] = np.where(light[eye], CREAM, np.where(L[eye] < a.iris_L, BLACK, SKIN))
                # catchlights: light spots enclosed by the iris -> a printable disc at the same spot
                iris = eye & (lbl == BLACK)
                inner = ndimage.binary_fill_holes(iris) & ~iris & light
                cl, cn = ndimage.label(inner)
                yy, xx = np.mgrid[0:H, 0:W]
                if iris.any():
                    dt_i = ndimage.distance_transform_edt(iris)
                    icy, icx = np.unravel_index(np.argmax(dt_i), dt_i.shape)
                    ir_r = dt_i[icy, icx]
                good = []
                for c in range(1, cn + 1):
                    cy_, cx_ = ndimage.center_of_mass(cl == c)
                    area = (cl == c).sum() / ppmm ** 2
                    if area < 0.8 and iris.any() and np.hypot(cy_ - icy, cx_ - icx) < 0.85 * ir_r:
                        good.append(c)
                cn = len(good)
                for c in good:
                    cy_, cx_ = ndimage.center_of_mass(cl == c)
                    disc = (yy - cy_) ** 2 + (xx - cx_) ** 2 <= (a.catch_r * ppmm) ** 2
                    lbl[disc & eye] = CREAM
                    catches.append((name, k, (cx_ / ppmm) + u0, v1 - cy_ / ppmm))
                if cn == 0 and a.ensure_catch and iris.any():
                    # no catchlight in the texture: place one up-right of the iris centre, like the art
                    dt = ndimage.distance_transform_edt(iris)
                    cy_, cx_ = np.unravel_index(np.argmax(dt), dt.shape)
                    r_iris = dt[cy_, cx_]
                    cy_, cx_ = cy_ - 0.38 * r_iris, cx_ + 0.38 * r_iris
                    disc = (yy - cy_) ** 2 + (xx - cx_) ** 2 <= (a.catch_r * ppmm) ** 2
                    lbl[disc & eye] = CREAM
                    catches.append((name + " (placed)", k, cx_ / ppmm + u0, v1 - cy_ / ppmm))
                reg[f"{name}_eye{k}"] = (box, lbl)
            # BROWS: dark shape connected to the brow landmarks; box = brow hull + brow_box
            eyes_box = reg[f"{name}_eye0"][0] | reg[f"{name}_eye1"][0]
            for k, idx in enumerate((BROW_L, BROW_R)):
                hull = hull_mask(P[idx], (H, W))
                box = dil(hull, a.brow_box) & fg & ~eyes_box
                brow = seeded(dark, box, dil(hull, 0.3))
                brow = ndimage.binary_fill_holes(ndimage.binary_closing(brow, iterations=2))
                lbl = np.full((H, W), -1, np.int8)
                lbl[box & ~dark] = SKIN
                lbl[brow] = BLACK
                reg[f"{name}_brow{k}"] = (box, lbl)
            # LIPS + MOUTH: red|teeth shape connected to the mouth centre, holes filled; inside it
            # nothing is ever black (dark -> red); outside it, stray red -> skin, dark left alone
            box = dil(poly_mask(P[LIP_OUT], (H, W)), a.lip_box) & fg
            seed = dil(poly_mask(P[LIP_IN], (H, W)), 0.1)
            teeth = (L > a.teeth_L) & (C < a.teeth_C) & fg              # warm-white teeth, shaded too
            mouth = seeded(red | teeth, box, seed)
            mouth = ndimage.binary_fill_holes(ndimage.binary_closing(mouth, iterations=3))
            lbl = np.full((H, W), -1, np.int8)
            lbl[box & ~dark] = SKIN
            lbl[mouth] = np.where(teeth[mouth] & ~red[mouth], CREAM, RED)
            # small dark patches touching the mouth (corner shadows) are mouth too -> red; large dark
            # areas (moustache, beard) are left alone
            dl, dn = ndimage.label(dark & box)
            if dn:
                sizes = ndimage.sum(np.ones_like(dl), dl, range(1, dn + 1)) / ppmm ** 2
                near = np.unique(dl[dil(mouth, 0.3) & (dl > 0)])
                small = [i for i in near if sizes[i - 1] < a.corner_max]
                cm = np.isin(dl, small)
                lbl[cm] = RED
                mouth = mouth | cm
            reg[f"{name}_mouth"] = (box, lbl)

            r_px = max(1, int(round(a.smooth * ppmm)))
            min_px = a.min_area * ppmm * ppmm
            for rname, (m, lbl) in reg.items():
                m = m & (lbl >= 0)                                # only pixels this region decides
                sub = np.full((H, W), -1, np.int8)
                for cls in (SKIN, CREAM, RED, BLACK):
                    cm = clean(m & (lbl == cls), r_px, min_px)
                    sub[cm] = cls
                hole = m & (sub < 0)
                if hole.any():
                    known = sub >= 0
                    _, (ii, jj) = ndimage.distance_transform_edt(~known, return_indices=True)
                    sub[hole] = sub[ii[hole], jj[hole]]
                label[m] = sub[m]
                regions[rname] = m
                counts = np.bincount(sub[m].astype(int) + 1, minlength=5)[1:]
                print(f"  {rname:14s} {m.sum()/ppmm**2:6.2f} mm2  " +
                      "  ".join(f"{NAMES[c]} {100*counts[c]/max(m.sum(),1):4.1f}%" for c in range(4)))

    np.savez_compressed(a.output, label=label, window=np.array([u0, u1, v0, v1]), ppmm=ppmm,
                        **{f"region_{k}": v for k, v in regions.items()})
    for c in catches:
        print(f"  catchlight {c[0]} eye{c[1]} at u {c[2]:.2f} v {c[3]:.2f} mm")
    print(f"wrote {a.output}")
    if a.debug_dir:
        d = Path(a.debug_dir); d.mkdir(parents=True, exist_ok=True)
        dbg.save(d / "landmarks.png")
        vis = rgb.astype(np.uint8).copy()
        m = label >= 0
        vis[m] = COLORS[label[m]]
        Image.fromarray(vis).save(d / "labels.png")
        print(f"debug -> {d/'landmarks.png'}, {d/'labels.png'}")


if __name__ == "__main__":
    main()
