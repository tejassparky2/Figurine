#!/usr/bin/env python3
"""Same two outputs as gen_textured_for_color.py -- a textured GLB (colour source) plus a
convert_model 3MF (watertight geometry) -- but driven by up to four orthographic
ELEVATIONS instead of a single three-quarter view.

Usage:
    python3 scripts/gen_textured_multiview.py <out_dir> <stem> \
        --front F.png [--left L.png] [--back B.png] [--right R.png]

Tripo wants the views in the fixed order [front, left, back, right]; a view you don't
have is sent as an empty object. `--front` is mandatory and Tripo needs at least two
views total.

"Left" is the view you get standing at the subject's left flank. For a vehicle that puts
the nose on the LEFT of the frame -- a car pointing north has its left side facing west,
so an observer to the west sees the nose on their left. Get this backwards and the model
comes out mirrored.

Worth the extra image generations whenever the back of the subject carries detail the
front cannot imply -- a car's tail lamps and tailgate badging, say, which a single front
three-quarter view leaves Tripo to invent, and it invents them flat.

Task ids hit disk in <out_dir>/<stem>_tasks.json before any polling starts, same as the
single-image script: Tripo has no task-listing endpoint, so an id that never reached disk
is a paid-for orphan. Re-run the same command to resume.
"""
import argparse
import json
import os
import time
from pathlib import Path

import requests

API_BASE = "https://api.tripo3d.ai/v2/openapi"
POLL = 5
TASK_TIMEOUT = 3600
VIEWS = ("front", "left", "back", "right")


def H():
    return {"Authorization": f"Bearer {os.environ['TRIPO_API_KEY']}"}


def upload(image: Path) -> str:
    ext = image.suffix.lstrip(".").lower().replace("jpg", "jpeg")
    with open(image, "rb") as f:
        r = requests.post(f"{API_BASE}/upload", headers=H(),
                          files={"file": (image.name, f, f"image/{ext}")}, timeout=300)
    r.raise_for_status()
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(d)
    return d["data"]["image_token"]


def task(payload: dict) -> str:
    r = requests.post(f"{API_BASE}/task", headers={**H(), "Content-Type": "application/json"},
                      json=payload, timeout=30)
    r.raise_for_status()
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(d)
    return d["data"]["task_id"]


def wait(task_id: str, label: str, timeout=TASK_TIMEOUT) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{API_BASE}/task/{task_id}", headers=H(), timeout=30)
        r.raise_for_status()
        d = r.json()["data"]
        st = d["status"]
        if st == "success":
            print(f"  + {label} done")
            return d
        if st in ("failed", "failure", "cancelled", "banned", "expired", "unknown"):
            raise RuntimeError(f"{label} {st}: consumed_credit={d.get('consumed_credit')} "
                               f"progress={d.get('progress')} output={d.get('output')}")
        print(f"  ... {label} {st} ({int(time.time()-start)}s)")
        time.sleep(POLL)
    raise RuntimeError(f"{label} timed out")


def submit_once(store: Path, key: str, payload: dict) -> str:
    saved = json.loads(store.read_text()) if store.exists() else {}
    if key in saved:
        print(f"  reusing {key} {saved[key]} from {store.name}")
        return saved[key]
    tid = task(payload)
    saved[key] = tid
    store.write_text(json.dumps(saved, indent=2))
    print(f"  {key} {tid}  (saved to {store.name})")
    return tid


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("stem", help="basename for the outputs, e.g. 'seltos'")
    for v in VIEWS:
        ap.add_argument(f"--{v}", type=Path, help=f"{v} elevation" +
                        (" (required)" if v == "front" else ""))
    ap.add_argument("--model-version", default="v3.1-20260211")
    args = ap.parse_args()

    paths = {v: getattr(args, v) for v in VIEWS}
    if paths["front"] is None:
        ap.error("--front is required; Tripo will not accept a multiview task without it")
    supplied = [v for v in VIEWS if paths[v] is not None]
    if len(supplied) < 2:
        ap.error("Tripo needs at least two views; with only a front view use "
                 "gen_textured_for_color.py instead")
    for v in supplied:
        if not paths[v].exists():
            ap.error(f"{paths[v]} does not exist")

    out: Path = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    store = out / f"{args.stem}_tasks.json"

    if store.exists():
        print(f"Resuming from {store.name}")
        files = None
    else:
        print(f"Uploading {len(supplied)} view(s): {', '.join(supplied)}")
        files = []
        for v in VIEWS:
            p = paths[v]
            if p is None:
                files.append({})
            else:
                ext = p.suffix.lstrip(".").lower().replace("jpg", "jpeg")
                files.append({"type": ext, "file_token": upload(p)})

    print("Submitting textured multiview_to_model (texture=True, pbr=False)...")
    model_task = submit_once(store, "model_task", {
        "type": "multiview_to_model",
        "model_version": args.model_version,
        "texture": True,
        "pbr": False,
        "files": files,
    })
    model = wait(model_task, "model")

    glb_path = out / f"{args.stem}_textured.glb"
    if not glb_path.exists():
        print(f"Downloading textured GLB -> {glb_path.name}")
        glb_path.write_bytes(requests.get(model["output"]["model"], timeout=600).content)

    print("Submitting convert_model -> 3mf (texture=True) for watertight geometry...")
    conv_task = submit_once(store, "convert_task", {
        "type": "convert_model",
        "format": "3mf",
        "texture": True,
        "original_model_task_id": model_task,
    })
    conv = wait(conv_task, "convert")
    mf_path = out / f"{args.stem}_geometry.3mf"
    print(f"Downloading watertight 3MF -> {mf_path.name}")
    mf_path.write_bytes(requests.get(conv["output"]["model"], timeout=600).content)

    print(f"\nDone.\n  color source: {glb_path}\n  geometry:     {mf_path}")
    print(f"  model_task_id={model_task}")


if __name__ == "__main__":
    main()
