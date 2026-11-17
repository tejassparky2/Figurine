#!/usr/bin/env python3
"""Pack a textured GLB into a *textured* 3MF — replicating Tripo Studio's colored-3MF download.

Tripo's `convert_model` API to 3MF strips color, and trimesh's 3MF export does too. Tripo Studio
gets a colored 3MF by embedding the GLB's UV texture into the 3MF via the 3MF Materials &
Properties extension (`<m:texture2d>` + `<m:texture2dgroup>`). This script does the same from the
GLB, so we get the identical full-color 3MF without going through Tripo Studio.

NOTE: this preserves the FULL UV texture (many colors + baked shading) — same as Studio. For clean
N-filament printing use scripts/colorize_3mf.py instead (quantizes to N flat colors). See
docs/auto_coloring.md.

Usage:
  python scripts/glb_to_textured_3mf.py <input.glb> -o <out.3mf> [--height 120]
"""

import argparse
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual import TextureVisuals

NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS_MAT = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
REL_MODEL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
REL_TEXTURE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dtexture"
TEX_PATH = "/3D/Textures/texture.png"


def reorient_and_scale(mesh, height=None):
    tallest = int(np.argmax(mesh.extents))
    if tallest == 1:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    elif tallest == 0:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    if height:
        mesh.apply_scale(height / mesh.extents[2])
    b = mesh.bounds
    mesh.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])


def main():
    ap = argparse.ArgumentParser(description="Pack a textured GLB into a textured 3MF (Studio-style)")
    ap.add_argument("input", help="input GLB (textured)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--height", type=float, help="scale to this Z height (mm)")
    args = ap.parse_args()

    scene = trimesh.load(args.input, process=False)
    mesh = scene.to_geometry() if isinstance(scene, trimesh.Scene) else scene
    assert isinstance(mesh, trimesh.Trimesh)
    if not isinstance(mesh.visual, TextureVisuals) or mesh.visual.uv is None:
        raise SystemExit("Input GLB has no UV texture — cannot make a textured 3MF.")

    # texture image bytes (PNG)
    mat = mesh.visual.material
    img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
    if img is None:
        raise SystemExit("No texture image found on the GLB material.")
    tex_buf = BytesIO()
    img.save(tex_buf, format="PNG")

    reorient_and_scale(mesh, args.height)

    V = mesh.vertices
    F = mesh.faces
    uv = np.asarray(mesh.visual.uv, dtype=float)
    uv = uv[:, :2].copy()
    uv[:, 1] = 1.0 - uv[:, 1]  # glTF (v-down) -> 3MF (v-up)

    vlines = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in V)
    coords = "".join(f'<m:tex2coord u="{u:.6f}" v="{v:.6f}"/>' for u, v in uv)
    # per-triangle UV indices = vertex indices (UV is per-vertex)
    tlines = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}" p1="{a}" p2="{b}" p3="{c}"/>'
        for a, b, c in F
    )

    model_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{NS_CORE}" xmlns:m="{NS_MAT}">\n'
        '<resources>\n'
        f'<m:texture2d id="1" path="{TEX_PATH}" contenttype="image/png" '
        'tilestyleu="wrap" tilestylev="wrap"/>\n'
        '<m:texture2dgroup id="2" texid="1">' + coords + '</m:texture2dgroup>\n'
        '<object id="3" type="model" pid="2" pindex="0">\n'
        '<mesh>\n'
        '<vertices>' + vlines + '</vertices>\n'
        '<triangles>' + tlines + '</triangles>\n'
        '</mesh>\n</object>\n</resources>\n'
        '<build><item objectid="3"/></build>\n</model>\n'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="{REL_MODEL}"/>'
        '</Relationships>'
    )
    model_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Target="{TEX_PATH}" Id="rel1" Type="{REL_TEXTURE}"/>'
        '</Relationships>'
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("3D/3dmodel.model", model_xml)
        z.writestr("3D/_rels/3dmodel.model.rels", model_rels)
        z.writestr("3D/Textures/texture.png", tex_buf.getvalue())

    print(f"Wrote {out} ({out.stat().st_size/1e6:.1f} MB, {len(F)} triangles, embedded {img.size} texture)")


if __name__ == "__main__":
    main()
