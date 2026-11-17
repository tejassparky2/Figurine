#!/usr/bin/env python3
"""EXP-019 watertight colored-3MF prep: generate a textured GLB (color source) +
a convert_model 3MF (watertight geometry) for one image, so colorize_3mf.py can
fuse them. Run, then call colorize_3mf.py <glb> --geometry <3mf>.

Usage: python scripts/gen_textured_for_color.py <image> <out_dir>

Task ids are written to <out_dir>/<stem>_tasks.json as soon as they are submitted and
reused on a re-run, so a client-side timeout or a killed terminal costs nothing — run the
same command again and it resumes polling the task already paid for. Tripo has no
task-listing endpoint, so an id that never reached disk is unrecoverable.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://api.tripo3d.ai/v2/openapi"
POLL = 5
# a two-figure sculpture legitimately runs past 15 minutes; the old 900s ceiling
# abandoned tasks that were still progressing
TASK_TIMEOUT = 3600


def H():
    return {"Authorization": f"Bearer {os.environ['TRIPO_API_KEY']}"}


def upload(image: Path) -> str:
    ext = image.suffix.lstrip(".").replace("jpg", "jpeg")
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
        # "expired" is terminal too — Tripo reports progress=100 with an empty output and
        # consumed_credit=0. Leaving it out of this list polls a dead task forever.
        if st in ("failed", "failure", "cancelled", "banned", "expired", "unknown"):
            raise RuntimeError(f"{label} {st}: consumed_credit={d.get('consumed_credit')} "
                               f"progress={d.get('progress')} output={d.get('output')}")
        print(f"  ... {label} {st} ({int(time.time()-start)}s)")
        time.sleep(POLL)
    raise RuntimeError(f"{label} timed out")


def submit_once(store: Path, key: str, payload: dict) -> str:
    """Submit a task, or reuse the id from a previous run. Every task id hits disk before
    we start polling — Tripo cannot list tasks, so an unsaved id is a paid-for orphan."""
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
    image = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    stem = image.stem
    store = out / f"{stem}_tasks.json"

    if store.exists():
        print(f"Resuming from {store.name}")
        token = None
    else:
        print("Uploading image...")
        token = upload(image)

    print("Submitting textured image_to_model (texture=True, pbr=False)...")
    model_task = submit_once(store, "model_task", {
        "type": "image_to_model",
        "model_version": "v3.1-20260211",
        "texture": True,
        "pbr": False,
        "file": {"type": "png", "file_token": token},
    })
    model = wait(model_task, "model")

    glb_url = model["output"]["model"]
    glb_path = out / f"{stem}_textured.glb"
    if not glb_path.exists():
        print(f"Downloading textured GLB -> {glb_path.name}")
        glb_path.write_bytes(requests.get(glb_url, timeout=600).content)

    print("Submitting convert_model -> 3mf (texture=True) for watertight geometry...")
    conv_task = submit_once(store, "convert_task", {
        "type": "convert_model",
        "format": "3mf",
        "texture": True,
        "original_model_task_id": model_task,
    })
    conv = wait(conv_task, "convert")
    mf_url = conv["output"]["model"]
    mf_path = out / f"{stem}_geometry.3mf"
    print(f"Downloading watertight 3MF -> {mf_path.name}")
    mf_path.write_bytes(requests.get(mf_url, timeout=600).content)

    print(f"\nDone.\n  color source: {glb_path}\n  geometry:     {mf_path}")
    print(f"  model_task_id={model_task}")


if __name__ == "__main__":
    main()
