#!/usr/bin/env python3
"""Split an already-painted Bambu 3MF into parts WITHOUT losing the paint.

Use when a finished model needs more filaments than the printer has slots. Splitting
it into semantic parts means no single part needs the full palette — e.g. a 5-color
figurine becomes a 4-color head plus a 4-color body.

Why the paint survives: Bambu stores `paint_color` as a per-triangle attribute on the
unmodified mesh, so color is just an array indexed by face. Tripo's segmentation is a
lossless partition (not a resample), so mapping part faces back to source faces by
centroid transfers the paint at ~0.000mm error. See docs/auto_coloring.md EXP-021.

Two passes:

  # 1. segment + close + report what came back, then pick your grouping
  python3 scripts/split_painted_3mf.py painted.3mf -o outdir

  # 2. write the parts
  python3 scripts/split_painted_3mf.py painted.3mf -o outdir \
      --group HEAD=0 --group BODY=1,2,3 --sweep HEAD=1C --sweep BODY=4

Everything after the two Tripo calls is local and cached, so pass 2 is free to re-run.
Needs TRIPO_API_KEY. The input file is only ever read.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import requests
import trimesh
from scipy.spatial import cKDTree

BASE = "https://openapi.tripo3d.ai/v3"
V_RE = re.compile(r'<vertex x="([-\d.eE+]+)" y="([-\d.eE+]+)" z="([-\d.eE+]+)"')
T_RE = re.compile(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"(?:\s+paint_color="([^"]*)")?')
# Bambu paint codes map monotonically onto filament slots 1..N
SLOT_CODES = ["4", "8", "0C", "1C", "2C", "3C", "4C", "5C"]
INHERIT_MM = 0.05   # beyond this a face is new cap geometry, not original surface


# ---------------------------------------------------------------- source parsing

def object_entry(z: zipfile.ZipFile) -> str:
    for n in ("3D/Objects/object_1.model", "3D/3dmodel.model"):
        if n in z.namelist():
            if "paint_color" in z.read(n)[:2_000_000].decode("utf-8", "ignore") or n.endswith("object_1.model"):
                return n
    return "3D/3dmodel.model"


def load_painted(path: Path):
    with zipfile.ZipFile(path) as z:
        name = object_entry(z)
        xml = z.read(name).decode("utf-8", "ignore")
        try:
            cfg = json.loads(z.read("Metadata/project_settings.config").decode())
            palette = cfg.get("filament_colour", [])
        except KeyError:
            palette = []
    verts = np.array(V_RE.findall(xml), dtype=np.float64)
    tris = T_RE.findall(xml)
    faces = np.array([[int(a), int(b), int(c)] for a, b, c, _ in tris], dtype=np.int64)
    paint = np.array([p if p else "" for *_, p in tris], dtype=object)
    return verts, faces, paint, palette, name


def require_bambu_project(path: Path, obj_entry: str):
    """Refuse a bare 3MF, because writing one silently produces a file that opens blank.

    write_3mf() clones the source project and swaps the mesh into `obj_entry`. A real Bambu
    project keeps its mesh in `3D/Objects/object_1.model` and its `<build>` items -- which are
    what place the object on the plate -- in the top-level `3D/3dmodel.model`, so overwriting
    the former leaves the latter intact. A bare 3MF from colorize_3mf.py / segment_paint_3mf.py
    has only the top-level file, so `obj_entry` IS the build-bearing file: it gets replaced by
    a mesh with an empty `<build/>`, and Bambu opens it with "no geometry data" on a blank plate.

    The mesh is genuinely in there, so anything that reads triangles -- including a hand-rolled
    parser -- reports the file as fine. Only a slicer, or a loader that walks the build items,
    notices. Hence a hard stop rather than a warning.
    """
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if obj_entry != "3D/3dmodel.model" or any(n.startswith("3D/Objects/") for n in names):
        return
    sys.exit(
        f"{path.name} is a bare 3MF, not a Bambu project -- it has no 3D/Objects/*.model, so\n"
        f"writing the parts would blank out its <build> items and the output would open empty.\n"
        f"Convert it first, then split the converted file:\n\n"
        f"    python3 scripts/colorgroup_to_painted.py {path} \\\n"
        f"        -o {path.with_name(path.stem + '_painted.3mf')}\n"
    )


def slot_name(code: str, palette) -> str:
    """Human label for a paint code, using the file's own filament list."""
    c = code if len(code) <= 2 else code[:2]
    if c in SLOT_CODES:
        i = SLOT_CODES.index(c)
        if i < len(palette):
            return f"slot{i+1} {palette[i]}"
        return f"slot{i+1}"
    return f"code {c}"


# ---------------------------------------------------------------- tripo calls

def api(key):
    return {"Authorization": f"Bearer {key}"}


def poll(tid, H, label):
    t0 = time.time()
    while True:
        j = requests.get(f"{BASE}/tasks/{tid}", headers=H, timeout=60).json()
        if j.get("code") != 0:
            sys.exit(f"{label} query failed: {j}")
        d = j["data"]
        st = d.get("status")
        if st in ("success", "completed"):
            return d
        if st in ("failed", "cancelled", "banned", "expired", "unknown"):
            sys.exit(f"{label} {st}: {json.dumps(d)[:400]}")
        print(f"    ... {label} {st} ({int(time.time()-t0)}s)")
        time.sleep(6)


def segment_and_close(verts, faces, out: Path, granularity: str, H):
    """Upload geometry -> /mesh/segment -> /mesh/complete(quick_cap). Cached per step."""
    glb = out / "geometry.glb"
    if not glb.exists():
        trimesh.Trimesh(vertices=verts, faces=faces, process=False).export(glb)
    print(f"  geometry.glb {glb.stat().st_size/1e6:.1f} MB")

    tok_f = out / "file_token.txt"
    if not tok_f.exists():
        with open(glb, "rb") as f:
            r = requests.post(f"{BASE}/files", headers=H, files={"file": (glb.name, f)}, timeout=1800)
        j = r.json()
        if j.get("code") != 0:
            sys.exit(f"upload failed ({r.status_code}): {j}")
        tok_f.write_text(j["data"]["file_token"])
    token = tok_f.read_text().strip()

    seg_f = out / "seg_task.txt"
    if not seg_f.exists():
        body = {"input": token, "model": "v2.0-20260430",
                "segmentation_granularity": granularity, "split_by_connectivity": False}
        j = requests.post(f"{BASE}/mesh/segment", headers={**H, "Content-Type": "application/json"},
                          json=body, timeout=120).json()
        if j.get("code") != 0:
            sys.exit(f"segment failed: {j}")
        seg_f.write_text(j["data"]["task_id"])
    seg_task = seg_f.read_text().strip()
    poll(seg_task, H, "segment")

    cap_f = out / "cap_task.txt"
    if not cap_f.exists():
        # quick_cap seals the open boundaries without touching the surface.
        # ai_completion (the default) resamples everything and does NOT close -- EXP-018.
        j = requests.post(f"{BASE}/mesh/complete", headers={**H, "Content-Type": "application/json"},
                          json={"input": seg_task, "completion_mode": "quick_cap"}, timeout=120).json()
        if j.get("code") != 0:
            sys.exit(f"complete failed: {j}")
        cap_f.write_text(j["data"]["task_id"])
    d = poll(cap_f.read_text().strip(), H, "quick_cap")

    dest = out / "parts.glb"
    if not dest.exists():
        url = d["output"].get("model_url") or d["output"].get("model")
        dest.write_bytes(requests.get(url, timeout=1800).content)
    print(f"  parts.glb {dest.stat().st_size/1e6:.1f} MB")
    return dest


def load_parts(path: Path):
    """Parts in world space. scene.geometry alone is LOCAL -- the node transforms matter."""
    s = trimesh.load(path)
    if not isinstance(s, trimesh.Scene):
        return {"part_0": s}
    out = {}
    for node in s.graph.nodes_geometry:
        T, g = s.graph[node]
        m = s.geometry[g].copy()
        m.apply_transform(T)
        out[node] = m
    # stable ordering: biggest first, so --group indices are predictable
    return {f"part_{i}": m for i, m in
            enumerate(sorted(out.values(), key=lambda m: -len(m.faces)))}


# ---------------------------------------------------------------- paint transfer

def make_transform(parts, verts):
    """ONE global affine, part space -> source mm. Per-part would inflate each part."""
    allp = trimesh.util.concatenate(list(parts.values()))
    cmin, cmax = allp.vertices.min(0), allp.vertices.max(0)
    smin, smax = verts.min(0), verts.max(0)
    scale = float(np.mean((smax - smin) / (cmax - cmin)))
    return lambda v: (v - cmin) * scale + smin


def resolve_member(parts, spec):
    """'part_7' -> the whole part; 'part_7#1' -> its 2nd-largest connected component.

    Needed because a Tripo segment sometimes fuses unrelated geometry that is *attached* to the
    figure, so --drop-detached cannot reach it: on manonbike, part_7 was the rider's right arm
    (36,598f) PLUS a lump of engine between his legs (15,240f) PLUS his collar (12,676f). Dropping
    the part would cost the arm. Components are indexed largest-first.
    """
    if "#" not in spec:
        return parts[spec]
    base, _, idx = spec.partition("#")
    comps = sorted(parts[base].split(only_watertight=False), key=lambda c: -len(c.faces))
    j = int(idx)
    if j >= len(comps):
        sys.exit(f"{spec}: {base} has only {len(comps)} component(s)")
    return comps[j]


def _bbox_gap(A, B):
    amin, amax, bmin, bmax = A.min(0), A.max(0), B.min(0), B.max(0)
    return float(np.linalg.norm(np.maximum(0, np.maximum(bmin - amax, amin - bmax))))


def attached_faces(mesh, tol):
    """Face mask keeping only the shells that transitively touch the largest shell.

    `bodies == 1` is the WRONG test for a merged group: every Tripo part is its own closed
    shell, so a grouped figure is legitimately ~10 shells that abut on their shared cut curves
    (all at 0.000mm). What does need dropping is the fragment of neighbouring hardware that a
    segment sometimes carries along — a footpeg stub, a lever, a slice of tank — which floats
    free of the figure. Transitive touching separates the two cleanly; measured on manonbike,
    real shells sat at 0.000mm and every stray at >11mm.
    """
    from trimesh.graph import connected_components
    comps = connected_components(mesh.face_adjacency, min_len=1,
                                 nodes=np.arange(len(mesh.faces)))
    if len(comps) <= 1:
        return np.ones(len(mesh.faces), bool), 0
    vsets = [mesh.vertices[np.unique(mesh.faces[fi])] for fi in comps]
    trees = [cKDTree(v) for v in vsets]
    adj = [[] for _ in comps]
    for a in range(len(comps)):
        for b in range(a + 1, len(comps)):
            if _bbox_gap(vsets[a], vsets[b]) > tol:
                continue
            d, _ = trees[a].query(vsets[b], distance_upper_bound=tol)
            if np.isfinite(d).any():
                adj[a].append(b)
                adj[b].append(a)
    root = int(np.argmax([len(c) for c in comps]))
    seen, stack = {root}, [root]
    while stack:
        for v in adj[stack.pop()]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    mask = np.zeros(len(mesh.faces), bool)
    for i in seen:
        mask[comps[i]] = True
    return mask, len(comps) - len(seen)


def inherit(mesh, xf, tree, paint, sweep):
    """Per-face paint. Real surface inherits verbatim; cap + swept faces take a neighbour."""
    C = xf(mesh.triangles_center) if callable(xf) else mesh.triangles_center
    dist, idx = tree.query(C, workers=-1)
    codes = np.array(paint[idx], dtype=object)
    base = np.array([c if len(c) <= 2 else c[:2] for c in codes])
    known = (dist < INHERIT_MM) & ~np.isin(base, list(sweep))
    n_cap = int((dist >= INHERIT_MM).sum())
    n_sweep = int((dist < INHERIT_MM).sum() - known.sum())
    ki, ui = np.where(known)[0], np.where(~known)[0]
    if len(ui):
        if not len(ki):
            sys.exit("every face was swept or capped - check --sweep")
        _, near = cKDTree(C[ki]).query(C[ui], workers=-1)
        codes[ui] = codes[ki[near]]
    return codes, n_cap, n_sweep


# ---------------------------------------------------------------- writing

def write_3mf(src_3mf: Path, obj_entry: str, out: Path, V, F, codes, n_src_faces):
    """Clone the source project and swap in the new mesh, keeping every Bambu setting."""
    vx = "\n".join(f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in V)
    tr = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{p}"/>'
                   for (a, b, c), p in zip(F, codes))
    obj = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
           'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
           'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
           'requiredextensions="p">\n'
           ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
           '  <object id="1" p:UUID="00010000-81cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
           '   <mesh>\n    <vertices>\n' + vx + '\n    </vertices>\n'
           '    <triangles>\n' + tr + '\n    </triangles>\n'
           '   </mesh>\n  </object>\n </resources>\n <build/>\n</model>\n')
    with zipfile.ZipFile(src_3mf) as zin:
        names = zin.namelist()
        data = {n: zin.read(n) for n in names}
    key = "Metadata/model_settings.config"
    if key in data:
        ms = data[key].decode()
        ms = ms.replace(f'face_count="{n_src_faces}"', f'face_count="{len(F)}"')
        ms = ms.replace(f'value="{src_3mf.name}"', f'value="{out.name}"')
        data[key] = ms.encode()
    data[obj_entry] = obj.encode()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for n in names:
            zo.writestr(n, data[n])


MODEL_HDR = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
             'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
             'requiredextensions="p">\n')


def mesh_xml(oid, V, F, codes):
    vx = "\n".join(f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in V)
    tr = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{p}"/>'
                   for (a, b, c), p in zip(F, codes))
    return (f'  <object id="{oid}" p:UUID="0001{oid:04d}-81cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
            '   <mesh>\n    <vertices>\n' + vx + '\n    </vertices>\n'
            '    <triangles>\n' + tr + '\n    </triangles>\n'
            '   </mesh>\n  </object>\n')


def write_3mf_multi(src_3mf: Path, obj_entry: str, out: Path, groups):
    """One 3MF holding every group as its own object, laid out side by side on the plate.

    groups: list of (name, V, F, codes). Each becomes a separate printable object, so you
    can print them one at a time with only that part's filaments loaded.
    """
    with zipfile.ZipFile(src_3mf) as zin:
        names = zin.namelist()
        data = {n: zin.read(n) for n in names}

    # geometry: all meshes in the one object file, ids 1..N
    body = "".join(mesh_xml(i + 1, V, F, c) for i, (_, V, F, c) in enumerate(groups))
    data[obj_entry] = (MODEL_HDR + ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                       ' <resources>\n' + body + ' </resources>\n <build/>\n</model>\n').encode()

    # plate layout: sit each part on the bed, spread along X so they don't collide
    widths = [float(V[:, 0].max() - V[:, 0].min()) for _, V, _, _ in groups]
    gap, total = 12.0, sum(widths) + 12.0 * (len(groups) - 1)
    x, placements = 128.0 - total / 2, []
    for (name, V, F, c), w in zip(groups, widths):
        cx = x + w / 2 - float((V[:, 0].max() + V[:, 0].min()) / 2)
        placements.append((cx, 128.0, -float(V[:, 2].min())))
        x += w + gap

    # 3dmodel.model: one wrapper object + one build item per group
    oid = lambda i: 100 + i  # noqa: E731 - wrapper ids, kept clear of the mesh ids
    res = "".join(
        f'  <object id="{oid(i)}" p:UUID="00000{oid(i)}-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
        '   <components>\n'
        f'    <component p:path="/{obj_entry}" objectid="{i+1}" '
        f'p:UUID="0001{i+1:04d}-b206-40ff-9872-83e8017abed1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
        '   </components>\n  </object>\n' for i in range(len(groups)))
    items = "".join(
        f'  <item objectid="{oid(i)}" p:UUID="00000{oid(i)}-b1ec-4553-aec9-835e5b724bb4" '
        f'transform="1 0 0 0 1 0 0 0 1 {px:.3f} {py:.3f} {pz:.3f}" printable="1"/>\n'
        for i, (px, py, pz) in enumerate(placements))
    head = data["3D/3dmodel.model"].decode().split("<resources>")[0]
    data["3D/3dmodel.model"] = (head + "<resources>\n" + res + " </resources>\n"
                                ' <build p:UUID="2c7c17d8-22b5-4d84-8835-1976022ea369">\n'
                                + items + " </build>\n</model>\n").encode()

    # model_settings.config: one <object> per group, all instanced on plate 1
    objs = "".join(
        f'  <object id="{oid(i)}">\n'
        f'    <metadata key="name" value="{name}"/>\n'
        '    <metadata key="extruder" value="1"/>\n'
        f'    <metadata face_count="{len(F)}"/>\n'
        '    <part id="1" subtype="normal_part">\n'
        f'      <metadata key="name" value="{name}"/>\n'
        '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
        f'      <metadata key="source_file" value="{out.name}"/>\n'
        f'      <metadata key="source_object_id" value="{i}"/>\n'
        '      <metadata key="source_volume_id" value="0"/>\n'
        '      <metadata key="source_offset_x" value="0"/>\n'
        '      <metadata key="source_offset_y" value="0"/>\n'
        f'      <metadata key="source_offset_z" value="{placements[i][2]:.3f}"/>\n'
        f'      <mesh_stat face_count="{len(F)}" edges_fixed="0" degenerate_facets="0" '
        'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
        '    </part>\n  </object>\n'
        for i, (name, V, F, c) in enumerate(groups))
    insts = "".join(
        f'    <model_instance>\n      <metadata key="object_id" value="{oid(i)}"/>\n'
        '      <metadata key="instance_id" value="0"/>\n'
        f'      <metadata key="identify_id" value="{72+i}"/>\n    </model_instance>\n'
        for i in range(len(groups)))
    asm = "".join(
        f'   <assemble_item object_id="{oid(i)}" instance_id="0" '
        f'transform="1 0 0 0 1 0 0 0 1 {px:.3f} {py:.3f} {pz:.3f}" offset="0 0 0" />\n'
        for i, (px, py, pz) in enumerate(placements))
    data["Metadata/model_settings.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + objs +
        '  <plate>\n    <metadata key="plater_id" value="1"/>\n'
        '    <metadata key="plater_name" value=""/>\n'
        '    <metadata key="locked" value="false"/>\n'
        '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
        '    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>\n'
        '    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>\n'
        '    <metadata key="top_file" value="Metadata/top_1.png"/>\n'
        '    <metadata key="pick_file" value="Metadata/pick_1.png"/>\n'
        + insts + '  </plate>\n  <assemble>\n' + asm + '  </assemble>\n</config>\n').encode()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for n in names:
            zo.writestr(n, data[n])


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("painted", type=Path, help="painted Bambu 3MF (read-only)")
    ap.add_argument("-o", "--out", type=Path, required=True, help="work + output directory")
    ap.add_argument("--granularity", default="simple", choices=["simple", "balanced", "detailed"])
    ap.add_argument("--group", action="append", default=[],
                    help="NAME=i,j,k — merge those part indices into one output. Repeatable. "
                         "An index may be i#c to take only connected component c of part i "
                         "(largest-first), for when a segment fuses unrelated geometry that is "
                         "attached to the figure and so survives --drop-detached.")
    ap.add_argument("--sweep", action="append", default=[],
                    help="NAME=code[,code] — reassign these stray paint codes inside that group")
    ap.add_argument("--remap", action="append", default=[],
                    help="TARGET=old>new[,old>new] — repaint one filament slot as another. "
                         "TARGET is a group name or a part id (part_2), so you can treat "
                         "e.g. the flag differently from the staff. Applied after grouping.")
    ap.add_argument("--drop-detached", type=float, metavar="MM",
                    help="drop shells that do not transitively touch the group's largest shell, "
                         "within this tolerance in mm (try 1.0). Use when a segment drags a "
                         "free-floating fragment of neighbouring hardware into the group. Does "
                         "NOT merge shells — abutting parts are kept, only detached ones go.")
    ap.add_argument("--single-file", action="store_true",
                    help="write ONE 3MF holding every group as a separate object, laid out "
                         "side by side on the plate, instead of one file per group")
    args = ap.parse_args()

    key = os.environ.get("TRIPO_API_KEY")
    if not key:
        sys.exit("TRIPO_API_KEY not set (set -a; source .env; set +a)")
    args.out.mkdir(parents=True, exist_ok=True)

    verts, faces, paint, palette, obj_entry = load_painted(args.painted)
    require_bambu_project(args.painted, obj_entry)
    print(f"{args.painted.name}: {len(verts):,} verts, {len(faces):,} faces")
    print(f"  palette: {palette}")

    glb = segment_and_close(verts, faces, args.out, args.granularity, api(key))
    parts = load_parts(glb)
    src = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    tree = cKDTree(src.triangles_center)
    xf = make_transform(parts, verts)

    groups = {}
    for spec in args.group:
        name, _, idxs = spec.partition("=")
        groups[name] = [f"part_{i.strip()}" for i in idxs.split(",") if i.strip()]
    sweeps = {}
    for spec in args.sweep:
        name, _, codes = spec.partition("=")
        sweeps[name] = {c.strip() for c in codes.split(",") if c.strip()}
    remaps = {}
    for spec in args.remap:
        name, _, pairs = spec.partition("=")
        remaps[name] = dict(p.split(">") for p in pairs.split(",") if ">" in p)

    if not groups:  # pass 1: report and stop
        print(f"\n{len(parts)} parts — pick a grouping with --group NAME=i,j\n")
        for name, m in parts.items():
            codes, n_cap, _ = inherit(m, xf, tree, paint, set())
            cnt = Counter(c if len(c) <= 2 else c[:2] for c in codes)
            used = [k for k in cnt if k in SLOT_CODES]
            inv = "  ".join(f"{slot_name(k, palette)}={100*cnt[k]/len(codes):.1f}%"
                            for k in sorted(used, key=lambda k: -cnt[k]))
            print(f"  {name:<9s} {len(m.faces):>9,} faces  watertight={str(m.is_watertight):<5s} "
                  f"{len(used)} filaments\n{'':13s}{inv}")
        return

    written = []
    for gname, members in groups.items():
        missing = [p for p in members if p.partition("#")[0] not in parts]
        if missing:
            sys.exit(f"{gname}: no such part(s) {missing}")
        V_l, F_l, lbl_l, off = [], [], [], 0
        for p in members:
            m = resolve_member(parts, p)
            V_l.append(xf(m.vertices))
            F_l.append(m.faces + off)
            lbl_l.append(np.full(len(m.faces), p, dtype=object))
            off += len(m.vertices)
        V, F = np.vstack(V_l), np.vstack(F_l)
        face_part = np.concatenate(lbl_l)
        mesh = trimesh.Trimesh(vertices=V, faces=F, process=False)
        n_dropped = 0
        if args.drop_detached is not None:
            keep, n_dropped = attached_faces(mesh, args.drop_detached)
            if n_dropped:
                print(f"  {gname}: dropped {n_dropped} detached shell(s), "
                      f"{int((~keep).sum()):,} faces")
                F, face_part = F[keep], face_part[keep]
                uv, flat = np.unique(F, return_inverse=True)   # compact away orphan vertices
                V, F = V[uv], flat.reshape(-1, 3)
                mesh = trimesh.Trimesh(vertices=V, faces=F, process=False)
        codes, n_cap, n_sweep = inherit(mesh, None, tree, paint, sweeps.get(gname, set()))

        # repaint: group-wide rules first, then per-part ones so they can override
        for target in [gname] + members:
            rule = remaps.get(target)
            if not rule:
                continue
            scope = np.ones(len(codes), bool) if target == gname else (face_part == target)
            for old, new in rule.items():
                hit = scope & (codes == old)
                codes[hit] = new
                if hit.any():
                    print(f"  remap {target}: {slot_name(old, palette)} -> "
                          f"{slot_name(new, palette)}  ({int(hit.sum()):,} faces)")

        cnt = Counter(c if len(c) <= 2 else c[:2] for c in codes)
        used = [k for k in cnt if k in SLOT_CODES]
        e = np.sort(mesh.edges, axis=1)
        _, ct = np.unique(e, axis=0, return_counts=True)
        if args.single_file:
            written.append((gname, V, F, codes))
            out = None
        else:
            out = args.out / f"{args.painted.stem}_{gname}.3mf"
            write_3mf(args.painted, obj_entry, out, V, F, codes, len(faces))
        print(f"\n{gname}: {len(F):,} faces ({n_cap:,} cap, {n_sweep:,} swept)  "
              f"{np.round(mesh.extents,1)} mm")
        for k in sorted(used, key=lambda k: -cnt[k]):
            print(f"    {slot_name(k, palette):<22s} {cnt[k]:>9,}  {100*cnt[k]/len(F):5.2f}%")
        dest = f"-> {out.name} ({out.stat().st_size/1e6:.1f} MB)" if out else "(pending single file)"
        print(f"    watertight={mesh.is_watertight} open_edges={int((ct==1).sum())} "
              f"bodies={mesh.body_count}  {dest}")
        print(f"    {len(used)} filaments needed")

    if args.single_file:
        out = args.out / f"{args.painted.stem}_split.3mf"
        write_3mf_multi(args.painted, obj_entry, out, written)
        print(f"\nsingle file: {out.name} ({out.stat().st_size/1e6:.1f} MB) — "
              f"{len(written)} separate objects: {', '.join(n for n, *_ in written)}")


if __name__ == "__main__":
    main()
