#!/usr/bin/env python3
"""Batch convert images to 3D 3MF files using Tripo3D API (parallel)."""

import argparse
import os
import sys
import time
from pathlib import Path

import requests
import trimesh

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
API_BASE = "https://api.tripo3d.ai/v2/openapi"
POLL_INTERVAL = 5


def get_headers():
    return {"Authorization": f"Bearer {os.environ['TRIPO_API_KEY']}"}


def upload_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/upload",
            headers=get_headers(),
            files={"file": (image_path.name, f, f"image/{image_path.suffix.lstrip('.').replace('jpg', 'jpeg')}")},
            timeout=300,
        )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Upload failed: {data}")
    return data["data"]["image_token"]


def create_model_task(image_token: str) -> str:
    resp = requests.post(
        f"{API_BASE}/task",
        headers={**get_headers(), "Content-Type": "application/json"},
        json={
            "type": "image_to_model",
            "model_version": "v3.1-20260211",
            "texture": False,
            "pbr": False,
            "file": {"type": "png", "file_token": image_token},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Task creation failed: {data}")
    return data["data"]["task_id"]


def create_convert_task(model_task_id: str) -> str:
    resp = requests.post(
        f"{API_BASE}/task",
        headers={**get_headers(), "Content-Type": "application/json"},
        json={
            "type": "convert_model",
            "format": "3mf",
            "original_model_task_id": model_task_id,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Convert task creation failed: {data}")
    return data["data"]["task_id"]


def poll_all_tasks(tasks: dict, timeout_secs: int = 600) -> dict:
    """Poll all tasks until they complete or fail. Returns {name: result_data_or_None}."""
    pending = dict(tasks)
    results = {}
    start = time.time()

    while pending and (time.time() - start) < timeout_secs:
        for name, task_id in list(pending.items()):
            try:
                resp = requests.get(
                    f"{API_BASE}/task/{task_id}",
                    headers=get_headers(),
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                status = data["status"]

                if status == "success":
                    results[name] = data
                    del pending[name]
                    print(f"  + {name} completed")
                elif status in ("failed", "failure"):
                    results[name] = None
                    del pending[name]
                    print(f"  x {name} failed")
            except Exception as e:
                results[name] = None
                del pending[name]
                print(f"  x {name} error: {e}")

        if pending:
            elapsed = int(time.time() - start)
            print(f"    ... {len(pending)} still running ({elapsed}s elapsed)")
            time.sleep(POLL_INTERVAL)

    for name in pending:
        results[name] = None
        print(f"  x {name} timed out")

    return results


def download_and_scale(name: str, download_url: str, output_dir: Path, height_mm: float) -> Path:
    out_path = output_dir / f"{name}.3mf"
    tmp_path = output_dir / f"{name}_tmp.3mf"

    print(f"  Downloading {name}...")
    resp = requests.get(download_url, timeout=300)
    resp.raise_for_status()
    tmp_path.write_bytes(resp.content)

    print(f"  Scaling {name} to {height_mm}mm...")
    scene = trimesh.load(str(tmp_path))
    mesh = scene.to_geometry() if isinstance(scene, trimesh.Scene) else scene
    current_height = mesh.extents[2]
    mesh.apply_scale(height_mm / current_height)
    mesh.export(str(out_path))
    tmp_path.unlink()

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Batch image-to-3D using Tripo3D API (parallel)")
    parser.add_argument("input_dir", help="Directory containing input images")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: <input_dir>/output)")
    parser.add_argument("--height", type=float, default=120.0,
                        help="Target height in mm (default: 120). Couple figurines: man=120, woman=110.")
    parser.add_argument("-n", "--limit", type=int, help="Only process first N images")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("TRIPO_API_KEY"):
        print("Error: TRIPO_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    images = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not images:
        print(f"No images found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        images = images[: args.limit]

    skipped = 0
    to_process = []
    for img in images:
        out_path = output_dir / f"{img.stem}.3mf"
        if out_path.exists():
            skipped += 1
        else:
            to_process.append(img)

    if skipped:
        print(f"Skipping {skipped} image(s) with existing output")

    if not to_process:
        print("Nothing to do — all outputs already exist.")
        return

    print(f"Processing {len(to_process)} image(s)")
    print(f"Output directory: {output_dir}\n")

    # Phase 1: Upload all images and submit model tasks
    print("=== Phase 1: Uploading and submitting model tasks ===")
    model_tasks = {}
    for img in to_process:
        try:
            print(f"  Uploading {img.name}...")
            token = upload_image(img)
            task_id = create_model_task(token)
            model_tasks[img.stem] = task_id
            print(f"  Submitted {img.stem} -> {task_id}")
        except Exception as e:
            print(f"  x {img.name} upload/submit failed: {e}", file=sys.stderr)

    if not model_tasks:
        print("No tasks submitted successfully.", file=sys.stderr)
        sys.exit(1)

    # Phase 2: Wait for all model generation
    print(f"\n=== Phase 2: Waiting for {len(model_tasks)} model(s) to generate ===")
    model_results = poll_all_tasks(model_tasks)

    succeeded_models = {name: data for name, data in model_results.items() if data is not None}
    if not succeeded_models:
        print("All model tasks failed.", file=sys.stderr)
        sys.exit(1)

    # Phase 3: Submit convert tasks for all completed models
    print(f"\n=== Phase 3: Submitting {len(succeeded_models)} convert task(s) ===")
    convert_tasks = {}
    for name, data in succeeded_models.items():
        try:
            task_id = create_convert_task(data["task_id"])
            convert_tasks[name] = task_id
            print(f"  Submitted convert for {name}")
        except Exception as e:
            print(f"  x {name} convert submit failed: {e}", file=sys.stderr)

    # Phase 4: Wait for all conversions
    print(f"\n=== Phase 4: Waiting for {len(convert_tasks)} conversion(s) ===")
    convert_results = poll_all_tasks(convert_tasks)

    # Phase 5: Download and scale
    succeeded_converts = {name: data for name, data in convert_results.items() if data is not None}
    print(f"\n=== Phase 5: Downloading and scaling {len(succeeded_converts)} model(s) ===")
    final = []
    for name, data in succeeded_converts.items():
        try:
            url = data["output"]["model"]
            out = download_and_scale(name, url, output_dir, args.height)
            final.append((name, out, None))
        except Exception as e:
            print(f"  x {name} download/scale failed: {e}", file=sys.stderr)
            final.append((name, None, str(e)))

    failed_names = set(n for n in model_tasks) - set(n for n, p, _ in final if p)
    for name in failed_names:
        final.append((name, None, "generation or conversion failed"))

    print(f"\n{'='*40}")
    print(f"Results: {sum(1 for _, p, _ in final if p)}/{len(final)} succeeded")
    for name, path, err in sorted(final):
        status = f"-> {path.name}" if path else f"FAILED: {err}"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
