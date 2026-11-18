"""Blender (headless): exact per-pixel FILAMENT-ID render of a painted OBJ+MTL, front orthographic view.

    blender -b --factory-startup --python scripts/blender_render_label_front.py -- \
        painted.obj ids.png --window u0,u1,v0,v1 --ppmm 40

The OBJ is already in the pipeline's mm frame (Z up, front = -Y), as written by colorize/cleanup
scripts. Each material ColorN gets the flat ID colour R = N/16 (linear), G = B = 0, rendered with
Workbench FLAT lighting, no anti-aliasing, Standard view transform, transparent background. Decode a
pixel with  N = round(16 * srgb_to_linear(R/255)); alpha 0 = no surface. This is the honest raster to
measure against: real triangles, real depth test, no point-splat gaps.
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
opt = {"--window": None, "--ppmm": "40"}
for i, a in enumerate(argv[2:]):
    if a in opt:
        opt[a] = argv[2:][i + 1]
u0, u1, v0, v1 = map(float, opt["--window"].split(","))
ppmm = float(opt["--ppmm"])

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.wm.obj_import(filepath=src, forward_axis="Y", up_axis="Z")
for o in sc.objects:
    if o.type != "MESH":
        continue
    for m in o.data.materials:
        try:
            n = int("".join(ch for ch in m.name if ch.isdigit()))
        except ValueError:
            n = 0
        m.diffuse_color = (n / 16.0, 0.0, 0.0, 1.0)

cd = bpy.data.cameras.new("cam")
cd.type = "ORTHO"
cd.sensor_fit = "HORIZONTAL"
cd.ortho_scale = u1 - u0
cd.clip_end = 5000
cam = bpy.data.objects.new("cam", cd)
cam.location = ((u0 + u1) / 2, -1000, (v0 + v1) / 2)
cam.rotation_euler = (3.14159265 / 2, 0, 0)
sc.collection.objects.link(cam)
sc.camera = cam
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "MATERIAL"
sc.display.render_aa = "OFF"
sc.render.resolution_x = int(round((u1 - u0) * ppmm))
sc.render.resolution_y = int(round((v1 - v0) * ppmm))
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = True
sc.render.image_settings.color_mode = "RGBA"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print(f"[blender] id render {out} {sc.render.resolution_x}x{sc.render.resolution_y}")
