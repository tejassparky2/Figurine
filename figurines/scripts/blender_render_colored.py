"""Blender (headless) photoreal render of a coloured OBJ+MTL, as it will look printed in PLA.

    blender -b --factory-startup --python scripts/blender_render_colored.py -- \
        model_colored.obj out.png [--photo approved.png] [--size 1000] [--samples 48] [--angle 0]

Imports the OBJ+MTL written by colorize_3mf.py / photo_project_colorize.py (Z-up, mm), gives
each filament a matte PLA material, and renders an orthographic front view (camera looking +Y,
the same view the approved render shows) in Cycles on CPU. With --photo the approved image is
placed to the left of the render for a side-by-side check. --angle rotates the model about Z
(180 = back view).
"""
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
obj_path, out_path = Path(argv[0]), Path(argv[1])
opts = {"--photo": None, "--size": "1000", "--samples": "48", "--angle": "0"}
for i, a in enumerate(argv[2:]):
    if a in opts:
        opts[a] = argv[2:][i + 1]
size, samples, angle = int(opts["--size"]), int(opts["--samples"]), float(opts["--angle"])

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.wm.obj_import(filepath=str(obj_path), forward_axis="Y", up_axis="Z")
obj = bpy.context.selected_objects[0]
obj.rotation_euler[2] = math.radians(angle)
bpy.context.view_layer.update()

for mat in obj.data.materials:  # matte PLA look, keep the MTL Kd colour
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        # MTL Kd holds the filament hex as sRGB, but Blender treats Base Color as linear —
        # left alone, every colour renders far too light (navy #282D48 came out ~#6B7290)
        bc = bsdf.inputs["Base Color"].default_value
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in bc[:3]]
        bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.55
        bsdf.inputs["Specular IOR Level"].default_value = 0.35

import numpy as np  # noqa: E402  (bundled with Blender)
co = np.empty(len(obj.data.vertices) * 3, np.float32)
obj.data.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
c_, s_ = math.cos(math.radians(angle)), math.sin(math.radians(angle))
xs = co[:, 0] * c_ - co[:, 1] * s_
ys = co[:, 0] * s_ + co[:, 1] * c_
zs = co[:, 2]
cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
w, h = max(xs) - min(xs), max(zs) - min(zs)

cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = max(w, h) * 1.06
cam = bpy.data.objects.new("cam", cam_data)
cam.location = (cx, min(ys) - 500, cz)
cam.rotation_euler = (math.radians(90), 0, 0)  # look along +Y, Z up
scene.collection.objects.link(cam)
scene.camera = cam
cam_data.clip_end = 2000

from mathutils import Vector  # noqa: E402


def sun(name, travel, strength, angle_deg):
    """Sun lamp — no distance falloff, so it behaves the same at mm scale as at m scale."""
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy, ld.angle = strength, math.radians(angle_deg)  # wide angle = soft shadows
    lo = bpy.data.objects.new(name, ld)
    lo.rotation_euler = Vector(travel).normalized().to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(lo)


# light travel directions (camera sits at -Y looking +Y)
sun("key", (0.45, 0.75, -0.55), 1.7, 25)    # from front-top-left
sun("fill", (-0.6, 0.7, -0.15), 0.5, 40)    # from front-right, low
sun("rim", (0.0, -0.6, -0.8), 0.8, 20)      # from behind-top, for edge separation
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.22
scene.world = world

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = samples
scene.cycles.use_denoising = True
scene.render.resolution_x = size
scene.render.resolution_y = int(size * min(1.0, (h * 1.06) / (max(w, h) * 1.06)) + 0.5) if w > h else size
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"
scene.render.filepath = str(out_path)
bpy.ops.render.render(write_still=True)
print(f"[blender] rendered {out_path}")

if opts["--photo"]:  # side-by-side: approved photo | render, on white
    r = bpy.data.images.load(str(out_path))
    p = bpy.data.images.load(opts["--photo"])
    def arr(img):
        a = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)
        return a
    ra, pa = arr(r), arr(p)
    rgb = ra[..., :3] * ra[..., 3:] + (1 - ra[..., 3:])  # composite on white
    H = rgb.shape[0]
    # nearest-neighbour scale the photo to the render's height
    ys_ = (np.arange(H) * pa.shape[0] / H).astype(int)
    xs_ = (np.arange(int(pa.shape[1] * H / pa.shape[0])) * pa.shape[0] / H).astype(int)
    ph = pa[ys_][:, xs_, :3]
    both = np.concatenate([ph, np.ones((H, 20, 3), np.float32), rgb], axis=1)
    out = bpy.data.images.new("sbs", both.shape[1], H, alpha=False)
    out.pixels[:] = np.concatenate([both, np.ones((*both.shape[:2], 1), np.float32)], axis=2).ravel()
    sbs = out_path.with_name(out_path.stem + "_vs_photo.png")
    out.filepath_raw = str(sbs)
    out.file_format = "PNG"
    out.save()
    print(f"[blender] side-by-side {sbs}")
