#!/usr/bin/env python3
"""Tripo texturing/segmentation experiment runner.

texture_model needs an `original_model_task_id` from a prior Tripo task — it can't texture an
arbitrary external mesh. So we (re)generate a base model from an image, cache its task_id, then
run texture/segmentation experiments against it. Each run downloads every output URL + preview
render so we can eyeball the result.

Usage:
  # one-time: create (or reuse cached) base model from an image
  python scripts/texture_experiments.py base --image <img.png> --name person_1 --out <dir>

  # run a texture experiment against the cached base
  python scripts/texture_experiments.py texture --name person_1 --out <dir> --exp pbr_false \
      --pbr false --texture-quality standard [--image <ref.png>] [--text "..."] [--parts "hair,shirt"]

  # segment the base model into parts
  python scripts/texture_experiments.py segment --name person_1 --out <dir> --exp seg
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

import requests

API_BASE = "https://api.tripo3d.ai/v2/openapi"
POLL_INTERVAL = 5


def headers(json_body=False):
    h = {"Authorization": f"Bearer {os.environ['TRIPO_API_KEY']}"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def upload_image(image_path: Path) -> str:
    ext = image_path.suffix.lstrip(".").replace("jpg", "jpeg")
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/upload",
            headers=headers(),
            files={"file": (image_path.name, f, f"image/{ext}")},
            timeout=300,
        )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Upload failed: {data}")
    return data["data"]["image_token"]


def create_task(body: dict) -> str:
    resp = requests.post(f"{API_BASE}/task", headers=headers(json_body=True), json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Task creation failed: {data}")
    return data["data"]["task_id"]


def poll(task_id: str, timeout_secs: int = 900) -> dict:
    start = time.time()
    while (time.time() - start) < timeout_secs:
        resp = requests.get(f"{API_BASE}/task/{task_id}", headers=headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data["status"]
        if status == "success":
            print(f"  + {task_id} success")
            return data
        if status in ("failed", "failure", "banned", "expired"):
            raise RuntimeError(f"Task {task_id} {status}: {json.dumps(data)[:500]}")
        elapsed = int(time.time() - start)
        prog = data.get("progress", "?")
        print(f"    ... {status} {prog}% ({elapsed}s)")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Task {task_id} timed out")


# ----- base model task_id cache -----

def cache_path(out: Path) -> Path:
    return out / "base_models.json"


def load_cache(out: Path) -> dict:
    p = cache_path(out)
    return json.loads(p.read_text()) if p.exists() else {}


def save_cache(out: Path, cache: dict):
    cache_path(out).write_text(json.dumps(cache, indent=2))


def get_base_task_id(out: Path, name: str) -> str:
    cache = load_cache(out)
    if name not in cache:
        print(f"Error: no cached base model for '{name}'. Run the `base` command first.", file=sys.stderr)
        sys.exit(1)
    return cache[name]["task_id"]


# ----- output download -----

def download_outputs(result: dict, exp_dir: Path, result_name: str = "result.json"):
    """Save the raw result JSON and download every URL in `output`."""
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / result_name).write_text(json.dumps(result, indent=2))
    output = result.get("output", {}) or {}
    saved = []
    for key, val in output.items():
        if isinstance(val, str) and val.startswith("http"):
            # derive extension from URL path (strip query)
            url_path = val.split("?", 1)[0]
            ext = Path(url_path).suffix or ".bin"
            dest = exp_dir / f"{key}{ext}"
            try:
                r = requests.get(val, timeout=300)
                r.raise_for_status()
                dest.write_bytes(r.content)
                saved.append(dest.name)
            except Exception as e:
                print(f"  ! could not download {key}: {e}")
    print(f"  saved: {', '.join(saved) if saved else '(no downloadable urls)'} -> {exp_dir}")
    return saved


# ----- commands -----

def cmd_base(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = load_cache(out)
    if args.name in cache and not args.force:
        print(f"Base model '{args.name}' already cached: {cache[args.name]['task_id']} (use --force to regen)")
        return
    token = upload_image(Path(args.image))
    body = {
        "type": "image_to_model",
        "model_version": "v3.1-20260211",
        "texture": args.texture,
        "pbr": args.pbr,
        "file": {"type": "png", "file_token": token},
    }
    task_id = create_task(body)
    print(f"Base image_to_model task: {task_id}")
    poll(task_id)
    cache[args.name] = {"task_id": task_id, "image": str(args.image)}
    save_cache(out, cache)
    print(f"Cached base model '{args.name}' -> {task_id}")


def cmd_texture(args):
    out = Path(args.out)
    base_id = get_base_task_id(out, args.name)
    body: Dict[str, Any] = {"type": "texture_model", "original_model_task_id": base_id}

    if args.texture is not None:
        body["texture"] = args.texture
    if args.pbr is not None:
        body["pbr"] = args.pbr
    if args.texture_quality:
        body["texture_quality"] = args.texture_quality
    if args.texture_alignment:
        body["texture_alignment"] = args.texture_alignment
    if args.parts:
        body["part_names"] = [p.strip() for p in args.parts.split(",") if p.strip()]

    texture_prompt = {}
    if args.image:
        token = upload_image(Path(args.image))
        texture_prompt["image"] = {"type": "png", "file_token": token}
    if args.text:
        texture_prompt["text"] = args.text
    if texture_prompt:
        body["texture_prompt"] = texture_prompt

    print(f"texture_model request:\n{json.dumps(body, indent=2)}")
    task_id = create_task(body)
    print(f"texture task: {task_id}")
    result = poll(task_id)
    download_outputs(result, out / args.exp)


def cmd_convert(args):
    """Convert a prior task (texture/base/segment) to a 3MF that slicers can open.

    Pulls the task_id from <out>/<exp>/result.json (or --task-id), runs convert_model with the
    texture baked in, and downloads the 3MF next to the experiment.
    """
    out = Path(args.out)
    if args.task_id:
        task_id = args.task_id
        exp_dir = out / args.exp
    else:
        rj = out / args.exp / "result.json"
        if not rj.exists():
            print(f"Error: {rj} not found and no --task-id given", file=sys.stderr)
            sys.exit(1)
        task_id = json.loads(rj.read_text())["task_id"]
        exp_dir = out / args.exp

    body = {
        "type": "convert_model",
        "format": "3mf",
        "original_model_task_id": task_id,
        "texture_size": 4096,
        "texture_format": "PNG",
        "bake": True,
        "pivot_to_center_bottom": True,
    }
    print(f"convert_model request:\n{json.dumps(body, indent=2)}")
    conv_id = create_task(body)
    print(f"convert task: {conv_id}")
    result = poll(conv_id)
    download_outputs(result, exp_dir, result_name="convert_result.json")


def cmd_segment(args):
    out = Path(args.out)
    base_id = get_base_task_id(out, args.name)
    body = {
        "type": "mesh_segmentation",
        "original_model_task_id": base_id,
        "model_version": "v1.0-20250506",
    }
    print(f"mesh_segmentation request:\n{json.dumps(body, indent=2)}")
    task_id = create_task(body)
    print(f"segmentation task: {task_id}")
    result = poll(task_id)
    download_outputs(result, out / args.exp)
    # cache the segmented model's task_id so we can texture its parts later
    cache = load_cache(out)
    cache[f"{args.name}__seg"] = {"task_id": task_id, "from": base_id}
    save_cache(out, cache)
    print(f"Cached segmented model -> {args.name}__seg")


def str2bool(v):
    return str(v).lower() in ("1", "true", "yes", "y")


def main():
    p = argparse.ArgumentParser(description="Tripo texturing/segmentation experiments")
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("base", help="create/cache a base model from an image")
    pb.add_argument("--image", required=True)
    pb.add_argument("--name", required=True)
    pb.add_argument("--out", required=True)
    pb.add_argument("--texture", type=str2bool, default=False, help="generate with texture (default false)")
    pb.add_argument("--pbr", type=str2bool, default=False, help="generate with PBR maps (default false)")
    pb.add_argument("--force", action="store_true")
    pb.set_defaults(func=cmd_base)

    pt = sub.add_parser("texture", help="run a texture_model experiment")
    pt.add_argument("--name", required=True)
    pt.add_argument("--out", required=True)
    pt.add_argument("--exp", required=True, help="experiment label (subfolder name)")
    pt.add_argument("--pbr", type=str2bool, default=None)
    pt.add_argument("--texture", type=str2bool, default=None)
    pt.add_argument("--texture-quality", choices=["standard", "detailed"], default=None)
    pt.add_argument("--texture-alignment", choices=["original_image", "geometry"], default=None)
    pt.add_argument("--image", help="reference image to guide texture")
    pt.add_argument("--text", help="text prompt to guide texture")
    pt.add_argument("--parts", help="comma-separated part_names (requires a segmented base)")
    pt.set_defaults(func=cmd_texture)

    pc = sub.add_parser("convert", help="convert a prior task to a slicer-ready 3MF (texture baked)")
    pc.add_argument("--out", required=True)
    pc.add_argument("--exp", required=True, help="experiment folder holding result.json (also output dir)")
    pc.add_argument("--task-id", help="override: convert this task_id instead of reading result.json")
    pc.set_defaults(func=cmd_convert)

    ps = sub.add_parser("segment", help="run mesh_segmentation on the base model")
    ps.add_argument("--name", required=True)
    ps.add_argument("--out", required=True)
    ps.add_argument("--exp", default="segmentation")
    ps.set_defaults(func=cmd_segment)

    args = p.parse_args()
    if not os.environ.get("TRIPO_API_KEY"):
        print("Error: TRIPO_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
