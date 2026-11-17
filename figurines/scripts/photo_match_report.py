#!/usr/bin/env python3
"""Pixel-by-pixel comparison of a finished colorgroup 3MF against the approved photo.

Projects the model's per-face filament labels onto the photo (front orthographic view, z-buffered
splat of face centroids, silhouette registration + dense optical flow, same alignment as
photo_project_colorize.py), then for every photo pixel inside the figure compares:

  * the filament the MODEL puts there, vs
  * the filament the PHOTO pixel is nearest to (CIEDE2000, against the same palette).

Reports, per filament: the photo's median colour over the pixels the model gives that filament
(i.e. what that filament SHOULD be to match the photo 1:1), its Delta E to the current hex, and
the % of pixels where model and photo agree. Writes a side-by-side image: photo | model labels
warped onto the photo | mismatch map (magenta = model and photo disagree).

    python3 scripts/photo_match_report.py model_colored.3mf --photo approved.png -o report.png [--json out.json]
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.color import deltaE_ciede2000, rgb2lab

sys.path.insert(0, str(Path(__file__).parent))
from photo_project_colorize import bilinear, photo_mask, register  # noqa: E402


def load(path):
    xml = zipfile.ZipFile(path).read("3D/3dmodel.model").decode()
    pal = re.findall(r'<m:color color="(#[0-9a-fA-F]{6})', xml)
    V = np.array(re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', xml), float)
    T = re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"(?: p1="(\d+)")?', xml)
    F = np.array([t[:3] for t in T], np.int64)
    lab = np.array([int(t[3] or 0) for t in T], np.int64)
    return V, F, lab, pal


def hex2rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)


def splat(C, lab, p, shape, rad=2):
    """z-buffered label image. Each face centroid covers a (2*rad+1)^2 footprint so the FRONT
    surface has no gaps for back faces to leak through; per pixel the nearest face (smallest y) wins."""
    H, W = shape
    c0 = np.round(p[0] * C[:, 0] + p[2]).astype(np.int64)
    r0 = np.round(p[3] - p[1] * C[:, 2]).astype(np.int64)
    pix, dep, lb = [], [], []
    for dr in range(-rad, rad + 1):
        for dc in range(-rad, rad + 1):
            r, c = r0 + dr, c0 + dc
            ok = (c >= 0) & (c < W) & (r >= 0) & (r < H)
            pix.append(r[ok] * W + c[ok]); dep.append(C[ok, 1]); lb.append(lab[ok])
    pix = np.concatenate(pix); dep = np.concatenate(dep); lb = np.concatenate(lb)
    order = np.lexsort((dep, pix))                 # by pixel, then nearest first
    pix, lb = pix[order], lb[order]
    first = np.r_[True, pix[1:] != pix[:-1]]
    img = np.full(H * W, -1, np.int64)
    img[pix[first]] = lb[first]
    return img.reshape(H, W)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--photo", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--json")
    ap.add_argument("--write-matched", metavar="OUT.3mf",
                    help="also write a copy of the model whose filament colours are replaced by the photo's "
                         "median colour for each filament (labels untouched); updates a sibling .mtl too")
    ap.add_argument("--erode", type=int, default=4, help="px to stay inside the photo silhouette")
    ap.add_argument("--luma-weight", type=float, default=0.35,
                    help="weight on L* when deciding which filament a photo pixel is nearest to. A filament is "
                         "one flat colour; the photo's light and shadow are not. 1.0 = plain CIEDE2000.")
    a = ap.parse_args()

    V, F, lab, pal = load(a.model)
    K = len(pal)
    P = np.array([hex2rgb(h) for h in pal])
    C = V[F].mean(1)
    img = Image.open(a.photo).convert("RGB")
    photo = np.asarray(img).astype(float)
    fg = photo_mask(img, 235)
    H, W = fg.shape
    p, iou = register(C[:, [0, 2]], fg, verbose=False)
    L = splat(C, lab, p, (H, W))

    # flow: flat palette render of the model -> photo (both CLAHE grey)
    rend = np.where(L[..., None] >= 0, P[np.clip(L, 0, None)], 255).astype(np.uint8)
    cl = cv2.createCLAHE(2.0, (8, 8))
    g1 = cl.apply(cv2.cvtColor(rend, cv2.COLOR_RGB2GRAY))
    g2 = cl.apply(cv2.cvtColor(photo.astype(np.uint8), cv2.COLOR_RGB2GRAY))
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(g2, g1, None)  # photo -> render
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    Lw = cv2.remap(L.astype(np.float32), gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=-1).astype(np.int64)

    inside = ndimage.binary_erosion(fg, iterations=a.erode) & (Lw >= 0)
    plab = rgb2lab(photo / 255.0)
    pal_lab = rgb2lab(P[None] / 255.0)[0]
    if a.luma_weight >= 1.0:
        d = np.stack([deltaE_ciede2000(plab, np.broadcast_to(pal_lab[k], plab.shape)) for k in range(K)], -1)
    else:
        w = np.array([a.luma_weight, 1.0, 1.0])
        d = np.stack([np.linalg.norm((plab - pal_lab[k]) * w, axis=-1) for k in range(K)], -1)
    Lp = d.argmin(-1)                            # filament each photo pixel is nearest to
    agree = (Lp == Lw) & inside
    rep = {"iou": round(float(iou), 4), "agreement_pct": round(100 * agree.sum() / max(inside.sum(), 1), 2), "filaments": []}
    print(f"silhouette IoU {iou:.3f}; model vs photo filament agreement {rep['agreement_pct']}% of {int(inside.sum()):,} px")
    print(f"{'filament':9s} {'px':>8s} {'agree%':>7s} {'photo median':>13s} {'dE00':>6s}   most-confused-with")
    for k in range(K):
        m = inside & (Lw == k)
        if not m.any():
            continue
        med = np.median(photo[m], 0)
        de = float(deltaE_ciede2000(rgb2lab(med[None, None] / 255.0), pal_lab[k][None, None]).item())
        conf = np.bincount(Lp[m], minlength=K); conf[k] = 0
        cw = int(conf.argmax()); cp = 100 * conf[cw] / m.sum()
        hexmed = "#%02X%02X%02X" % tuple(np.round(med).astype(int))
        print(f"{pal[k]:9s} {int(m.sum()):8,d} {100 * agree[m].mean():6.1f}% {hexmed:>13s} {de:6.1f}   {pal[cw]} ({cp:.1f}%)")
        rep["filaments"].append({"hex": pal[k], "pixels": int(m.sum()), "agree_pct": round(100 * float(agree[m].mean()), 2),
                                 "photo_median": hexmed, "dE00_current_vs_photo": round(de, 2),
                                 "confused_with": pal[cw], "confused_pct": round(float(cp), 2)})
    # image: photo | warped labels | mismatch
    lw_rgb = np.where(Lw[..., None] >= 0, P[np.clip(Lw, 0, None)], 255).astype(np.uint8)
    mis = photo.copy().astype(np.uint8)
    mis = (0.35 * mis + 0.65 * 255).astype(np.uint8)
    mis[inside & ~agree] = [255, 0, 200]
    out = np.concatenate([photo.astype(np.uint8), lw_rgb, mis], 1)
    Image.fromarray(out).save(a.output)
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2))
    if a.write_matched:
        new = {f["hex"].lower(): f["photo_median"] for f in rep["filaments"]}
        with zipfile.ZipFile(a.model) as zi, zipfile.ZipFile(a.write_matched, "w", zipfile.ZIP_DEFLATED) as zo:
            for n in zi.namelist():
                data = zi.read(n)
                if n == "3D/3dmodel.model":
                    data = re.sub(r'(<m:color color=")(#[0-9a-fA-F]{6})',
                                  lambda m: m.group(1) + new.get(m.group(2).lower(), m.group(2)), data.decode()).encode()
                zo.writestr(n, data)
        mtl_in, mtl_out = Path(a.model).with_suffix(".mtl"), Path(a.write_matched).with_suffix(".mtl")
        obj_in, obj_out = Path(a.model).with_suffix(".obj"), Path(a.write_matched).with_suffix(".obj")
        if mtl_in.exists():
            lines, order = [], [h for h in pal]
            mi = -1
            for ln in mtl_in.read_text().splitlines():
                if ln.startswith("newmtl"):
                    mi += 1
                if ln.startswith("Kd") and 0 <= mi < len(order) and order[mi].lower() in new:
                    rgb = hex2rgb(new[order[mi].lower()]) / 255.0
                    ln = "Kd %.4f %.4f %.4f" % tuple(rgb)
                lines.append(ln)
            mtl_out.write_text("\n".join(lines) + "\n")
            if obj_in.exists() and obj_in != obj_out:
                txt = obj_in.read_text()
                obj_out.write_text(re.sub(r"^mtllib .*$", f"mtllib {mtl_out.name}", txt, count=1, flags=re.M))
        print("matched palette: " + ", ".join(f"{k} -> {v}" for k, v in new.items()))
        print(f"wrote {a.write_matched}")
    print(f"wrote {a.output}")


if __name__ == "__main__":
    main()
