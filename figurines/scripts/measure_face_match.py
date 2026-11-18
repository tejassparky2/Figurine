#!/usr/bin/env python3
"""Measure how exactly a painted 3MF reproduces the target face labels, feature by feature.

    python3 scripts/measure_face_match.py painted.3mf labels.npz --map skin=#.. --map black=#.. \
        --map red=#.. --map cream=#.. -o report_dir/

Projects the painted mesh into the same front view and pixel grid as labels.npz (z-buffer: nearest
triangle per pixel), then for every feature region (eyes, brows, mouths) reports:
  * pixel accuracy (share of the region where painted class == target class);
  * IoU per filament class (black / cream / red / skin) inside the region.
Writes face_match.png (bar charts), face_match_overlay.png (target | painted | mismatch in magenta,
zoomed per feature) and face_match.json.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from printable_cleanup import load  # noqa: E402

NAMES = ["skin", "black", "red", "cream"]
COLORS = np.array([[240, 170, 120], [30, 25, 22], [220, 20, 10], [246, 224, 196]], np.uint8)


def painted_label_image(mesh, lab, slot2cls, window, ppmm, shape):
    u0, u1, v0, v1 = window
    H, W = shape
    F, V = mesh.faces, mesh.vertices
    cls = slot2cls[lab]
    pix, dep, val = [], [], []
    for P in (mesh.triangles_center, V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]):
        qx = np.floor((P[:, 0] - u0) * ppmm).astype(np.int64)
        qy = np.floor((v1 - P[:, 2]) * ppmm).astype(np.int64)
        ok = (qx >= 0) & (qx < W) & (qy >= 0) & (qy < H)
        pix.append(qy[ok] * W + qx[ok]); dep.append(P[ok, 1]); val.append(cls[ok])
    pix = np.concatenate(pix); dep = np.concatenate(dep); val = np.concatenate(val)
    o = np.lexsort((dep, pix))
    pix, val = pix[o], val[o]
    first = np.r_[True, pix[1:] != pix[:-1]]
    img = np.full(H * W, -2, np.int64)
    img[pix[first]] = val[first]
    return img.reshape(H, W)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("labels")
    ap.add_argument("--map", action="append", required=True)
    ap.add_argument("-o", "--outdir", required=True)
    ap.add_argument("--id-render", help="PNG from blender_render_label_front.py of the painted OBJ (exact raster); "
                    "without it a point projection is used (gappy, only for a quick look)")
    a = ap.parse_args()
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)

    mesh, lab, pal = load(a.model)
    pl = [h.lower() for h in pal]
    slot2cls = np.full(len(pal), -1)
    for m in a.map:
        n, h = m.split("=")
        slot2cls[pl.index(h.lower())] = NAMES.index(n)
    d = np.load(a.labels)
    T = d["label"].astype(np.int64)
    window, ppmm = d["window"], float(d["ppmm"])
    if a.id_render:
        ir = np.asarray(Image.open(a.id_render).convert("RGBA")).astype(float)
        r = ir[..., 0] / 255.0
        lin = np.where(r <= 0.04045, r / 12.92, ((r + 0.055) / 1.055) ** 2.4)
        n = np.rint(16 * lin).astype(np.int64)            # material ColorN -> palette slot N-1
        slot = n - 1
        Pimg = np.where((ir[..., 3] > 127) & (slot >= 0) & (slot < len(pal)),
                        slot2cls[np.clip(slot, 0, len(pal) - 1)], -2)
        assert Pimg.shape == T.shape, (Pimg.shape, T.shape)
    else:
        Pimg = painted_label_image(mesh, lab, slot2cls, window, ppmm, T.shape)
    regions = {k[7:]: d[k] for k in d.files if k.startswith("region_")}

    rep = {}
    for rn, m in regions.items():
        m = m & (T >= 0)
        if not m.any():
            continue
        acc = float((Pimg[m] == T[m]).mean())
        ious = {}
        for c in range(4):
            t, p = (T == c) & m, (Pimg == c) & m
            if t.sum() + p.sum() == 0:
                continue
            ious[NAMES[c]] = float((t & p).sum() / max((t | p).sum(), 1))
        rep[rn] = {"accuracy": round(acc, 4), "iou": {k: round(v, 4) for k, v in ious.items()},
                   "area_mm2": round(float(m.sum()) / ppmm ** 2, 2)}
        print(f"{rn:14s} accuracy {100*acc:5.1f}%  " + "  ".join(f"{k} IoU {100*v:5.1f}%" for k, v in ious.items()))
    Path(out / "face_match.json").write_text(json.dumps(rep, indent=2))

    # bar chart: accuracy per feature + IoU of the feature's main class
    names = list(rep)
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6))
    axs[0].barh(names, [100 * rep[n]["accuracy"] for n in names], color="#4C72B0")
    axs[0].set_xlim(0, 100); axs[0].set_xlabel("% of feature pixels painted with the target filament")
    axs[0].set_title("Pixel accuracy per feature")
    for i, n in enumerate(names):
        axs[0].text(100 * rep[n]["accuracy"] + 0.5, i, f"{100*rep[n]['accuracy']:.1f}", va="center", fontsize=8)
    w = 0.2
    y = np.arange(len(names))
    for k, c in enumerate(["black", "cream", "red"]):
        vals = [100 * rep[n]["iou"].get(c, np.nan) for n in names]
        axs[1].barh(y + (k - 1) * w, vals, height=w, label=c, color=["#222", "#e8d6b8", "#d62020"][k],
                    edgecolor="#555", linewidth=0.4)
    axs[1].set_yticks(y); axs[1].set_yticklabels(names); axs[1].set_xlim(0, 100)
    axs[1].set_xlabel("IoU % (overlap of painted vs target shape)"); axs[1].set_title("Shape overlap per filament")
    axs[1].legend(loc="lower right", fontsize=8)
    plt.tight_layout(); plt.savefig(out / "face_match.png", dpi=130); plt.close()

    # overlay zooms per feature: target | painted | mismatch
    tiles = []
    for rn, m in regions.items():
        ys, xs = np.nonzero(m)
        if not len(ys):
            continue
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        def col(img):
            c = np.full(img.shape + (3,), 255, np.uint8)
            k = img >= 0
            c[k] = COLORS[img[k]]
            return c
        t = col(np.where(m, T, -1))[y0:y1, x0:x1]
        p = col(np.where(m, Pimg, -1))[y0:y1, x0:x1]
        mis = np.full(t.shape, 255, np.uint8)
        bad = (m & (Pimg != T))[y0:y1, x0:x1]
        mis[m[y0:y1, x0:x1]] = [225, 225, 225]
        mis[bad] = [255, 0, 200]
        row = np.concatenate([t, np.full((t.shape[0], 6, 3), 255, np.uint8), p,
                              np.full((t.shape[0], 6, 3), 255, np.uint8), mis], 1)
        im = Image.fromarray(row)
        im = im.resize((900, max(1, int(900 * im.height / im.width))))
        tiles.append((rn, im))
    Hh = sum(t.height + 24 for _, t in tiles)
    S = Image.new("RGB", (900, Hh), "white")
    from PIL import ImageDraw
    dr = ImageDraw.Draw(S); y_ = 0
    for rn, t in tiles:
        dr.text((4, y_ + 4), f"{rn}: target | painted | mismatch (magenta)  acc {100*rep[rn]['accuracy']:.1f}%", fill=(0, 0, 0))
        S.paste(t, (0, y_ + 20)); y_ += t.height + 24
    S.save(out / "face_match_overlay.png")
    print(f"wrote {out/'face_match.png'}, {out/'face_match_overlay.png'}, {out/'face_match.json'}")


if __name__ == "__main__":
    main()
