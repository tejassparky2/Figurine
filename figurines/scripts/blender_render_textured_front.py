"""Blender (headless): flat, orthographic FRONT render of a textured GLB in the pipeline's mm frame.

    blender -b --factory-startup --python scripts/blender_render_textured_front.py -- \
        model.glb out.png --height 120 --window u0,u1,v0,v1 --ppmm 40

Same normalisation as colorize_3mf.py / clean_colorize.py: glTF Y-up -> Z-up (Blender's importer
does exactly the rotation reorient() does), scale so the Z extent is --height mm, centre X/Y, sit on
z=0. Camera: orthographic, looking +Y from -Y (the front, view 0). Pixel (px, py) <-> model mm:

    u = u0 + (px + 0.5) / ppmm        v = v1 - (py + 0.5) / ppmm

Workbench engine with flat lighting and texture colour, so what you get is the model's own texture
with no shading — the right input for 2D face-landmark detection.
"""
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
opt = {"--height": "120", "--window": None, "--ppmm": "40"}
for i, a in enumerate(argv[2:]):
    if a in opt:
        opt[a] = argv[2:][i + 1]
H_MM, PPMM = float(opt["--height"]), float(opt["--ppmm"])
u0, u1, v0, v1 = map(float, opt["--window"].split(","))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in sc.objects if o.type == "MESH"]

# world-space bounds of all mesh vertices
pts = []
for o in meshes:
    co = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(o.matrix_world)
    pts.append(co @ M[:3, :3].T + M[:3, 3])
pts = np.concatenate(pts)
lo, hi = pts.min(0), pts.max(0)
s = H_MM / (hi[2] - lo[2])
t = np.array([-(lo[0] + hi[0]) / 2 * s, -(lo[1] + hi[1]) / 2 * s, -lo[2] * s])
root = bpy.data.objects.new("root", None)
sc.collection.objects.link(root)
for o in meshes:
    if o.parent is None:
        o.parent = root
    for p in [o] + list(o.children_recursive):
        pass
# parent any top-level objects (empties from the glTF hierarchy too)
for o in list(sc.objects):
    if o is not root and o.parent is None:
        o.parent = root
root.scale = (s, s, s)
root.location = tuple(t)
bpy.context.view_layer.update()

cd = bpy.data.cameras.new("cam")
cd.type = "ORTHO"
cd.sensor_fit = "HORIZONTAL"
cd.ortho_scale = u1 - u0
cd.clip_end = 5000
cam = bpy.data.objects.new("cam", cd)
cam.location = ((u0 + u1) / 2, -1000, (v0 + v1) / 2)
cam.rotation_euler = (np.pi / 2, 0, 0)
sc.collection.objects.link(cam)
sc.camera = cam

sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "FLAT"
sh.color_type = "TEXTURE"
sh.background_type = "VIEWPORT"
sh.background_color = (1, 1, 1)
sc.render.resolution_x = int(round((u1 - u0) * PPMM))
sc.render.resolution_y = int(round((v1 - v0) * PPMM))
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = True
sc.render.image_settings.color_mode = "RGBA"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print(f"[blender] {out}: {sc.render.resolution_x}x{sc.render.resolution_y}, scale {s:.4f}, "
      f"window u {u0}..{u1} v {v0}..{v1} @ {PPMM} px/mm")
