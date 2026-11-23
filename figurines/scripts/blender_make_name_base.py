"""Blender (headless): build a round display base with a curved name plaque, ready for 2-colour printing.

    blender -b --factory-startup --python scripts/blender_make_name_base.py -- out.npz \
        --name "Name" --title "TITLE LINE" [--diameter 110] [--height 26] \
        [--plaque-w 60] [--plaque-h 14] [--serif FONT.ttf] [--sans FONT.ttf] [--blend out.blend]

Shape (mm, Z up, front = -Y, origin at the centre of the bottom):
  * a turned plinth: chamfered foot, body tapering slightly inward, a small groove, then a top disc
    with a rounded top edge (profile revolved, 360 segments, flat top for the figure to stand on);
  * a rounded-rectangle plaque wrapped onto the front of the body, bevelled front edge, its back
    sunk 1.5 mm into the body so the union is solid;
  * the name (serif bold) and title (sans bold, letter-spaced) raised 0.4 mm on the plaque,
    wrapped onto the same cylinder.
Everything is unioned with the EXACT boolean into one watertight solid. Material per face:
0 = base, 1 = plaque, 2 = text. Writes out.npz with vertices V (mm), faces F, material M.
"""
import math
import sys

import bmesh
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]
opt = {"--name": "Name", "--title": "TITLE", "--diameter": "110", "--height": "26",
       "--plaque-w": "60", "--plaque-h": "14", "--name-cap": "5.0", "--title-cap": "2.6",
       "--serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
       "--sans": "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf", "--blend": None}
rest = argv[1:]
for i, a in enumerate(rest):
    if a in opt:
        opt[a] = rest[i + 1]

R = float(opt["--diameter"]) / 2
H = float(opt["--height"])
PW, PH = float(opt["--plaque-w"]), float(opt["--plaque-h"])
SEG = 360

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def material(name, rgb):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    return m


MATS = [material("Color1", (0.42, 0.27, 0.19)), material("Color2", (0.89, 0.69, 0.29)),
        material("Color3", (0.29, 0.18, 0.12))]


def new_object(name, bm, mat_index):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in MATS:
        me.materials.append(m)
    for p in me.polygons:
        p.material_index = mat_index
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------- plinth (revolved profile)
Hb = H - 7.5                     # top of the body / start of the groove
prof = [(R - 0.8, 0.0), (R, 0.8), (R - 0.8, Hb), (R - 1.8, Hb + 0.4), (R - 1.8, Hb + 1.1),
        (R - 0.9, Hb + 1.5)]
fr = 2.6                          # top-edge fillet radius
cx, cz = R - 0.9 - fr, H - fr
for k in range(0, 13):
    t = math.radians(90 * k / 12)
    prof.append((cx + fr * math.cos(t), cz + fr * math.sin(t)))


def body_radius(z):
    return R - 0.8 * (z - 0.8) / (Hb - 0.8)


bm = bmesh.new()
rings = []
for (r, z) in prof:
    ring = [bm.verts.new((r * math.sin(2 * math.pi * j / SEG), -r * math.cos(2 * math.pi * j / SEG), z))
            for j in range(SEG)]
    rings.append(ring)
for a, b in zip(rings[:-1], rings[1:]):
    for j in range(SEG):
        bm.faces.new((a[j], a[(j + 1) % SEG], b[(j + 1) % SEG], b[j]))
bot, top = bm.verts.new((0, 0, 0)), bm.verts.new((0, 0, H))
for j in range(SEG):
    bm.faces.new((rings[0][(j + 1) % SEG], rings[0][j], bot))
    bm.faces.new((rings[-1][j], rings[-1][(j + 1) % SEG], top))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
base = new_object("base", bm, 0)

# ---------------------------------------------------------------- flat-space helpers
# Flat coordinates: x = arc length along the front (mm), y = height (mm), z = radial offset from RREF.
RREF = R
ZC = 0.8 + (Hb - 0.8) / 2        # plaque centred on the body
FRONT = 1.2                       # plaque front face, radial offset
BACK = -1.5                       # plaque back face (sunk into the body)


def slice_x(bm, step=1.0):
    xs = [v.co.x for v in bm.verts]
    x = math.floor(min(xs) / step) * step
    while x < max(xs):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(x, 0, 0), plane_no=(1, 0, 0))
        x += step


def wrap(bm):
    for v in bm.verts:
        s, y, d = v.co
        th = s / RREF
        r = RREF + d
        v.co = (r * math.sin(th), -r * math.cos(th), y + ZC)


def rounded_rect(w, h, rad, n=10):
    pts = []
    for (qx, qy, a0) in ((w / 2 - rad, h / 2 - rad, 0), (-w / 2 + rad, h / 2 - rad, 90),
                         (-w / 2 + rad, -h / 2 + rad, 180), (w / 2 - rad, -h / 2 + rad, 270)):
        for k in range(n + 1):
            t = math.radians(a0 + 90 * k / n)
            pts.append((qx + rad * math.cos(t), qy + rad * math.sin(t)))
    return pts


# ---------------------------------------------------------------- plaque
bm = bmesh.new()
outline = rounded_rect(PW, PH, 2.0)
back = [bm.verts.new((x, y, BACK)) for x, y in outline]
face = bm.faces.new(back[::-1])
ext = bmesh.ops.extrude_face_region(bm, geom=[face])
top_verts = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
bmesh.ops.translate(bm, verts=top_verts, vec=(0, 0, FRONT - BACK))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
front_face = max(bm.faces, key=lambda f: f.calc_center_median().z)
bmesh.ops.bevel(bm, geom=list(front_face.edges), offset=0.5, segments=3, affect="EDGES",
                profile=0.5, clamp_overlap=True)
bmesh.ops.triangulate(bm, faces=bm.faces)
slice_x(bm)
wrap(bm)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
plaque = new_object("plaque", bm, 1)


# ---------------------------------------------------------------- text
def text_bmesh(body, font_path, cap_mm, spacing=1.0):
    cu = bpy.data.curves.new("t", type="FONT")
    cu.body = body
    cu.font = bpy.data.fonts.load(font_path)
    cu.size = 1.0
    cu.space_character = spacing
    cu.align_x = "CENTER"
    cu.resolution_u = 6
    ob = bpy.data.objects.new("t", cu)
    scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    ob.evaluated_get(dg).to_mesh_clear()
    bpy.data.objects.remove(ob)
    # measure cap height from a capital letter of the same font
    cu2 = bpy.data.curves.new("h", type="FONT"); cu2.body = "H"; cu2.font = cu.font; cu2.size = 1.0
    ob2 = bpy.data.objects.new("h", cu2); scene.collection.objects.link(ob2)
    dg = bpy.context.evaluated_depsgraph_get()
    m2 = ob2.evaluated_get(dg).to_mesh()
    cap = max(v.co.y for v in m2.vertices) - min(v.co.y for v in m2.vertices)
    ob2.evaluated_get(dg).to_mesh_clear(); bpy.data.objects.remove(ob2)
    k = cap_mm / cap
    bmesh.ops.scale(bm, vec=(k, k, 1), verts=bm.verts)
    return bm


name_bm = text_bmesh(opt["--name"], opt["--serif"], float(opt["--name-cap"]))
title_bm = text_bmesh(opt["--title"], opt["--sans"], float(opt["--title-cap"]), spacing=1.12)


def bounds(bm):
    xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]
    return min(xs), max(xs), min(ys), max(ys)


nx0, nx1, ny0, ny1 = bounds(name_bm)
tx0, tx1, ty0, ty1 = bounds(title_bm)
gap = 1.4
block = (ny1 - ny0) + gap + (ty1 - ty0)
avail_w = PW - 5.0
for bmx, (x0, x1, y0, y1), y_top in ((name_bm, (nx0, nx1, ny0, ny1), block / 2),
                                    (title_bm, (tx0, tx1, ty0, ty1), block / 2 - (ny1 - ny0) - gap)):
    sx = min(1.0, avail_w / (x1 - x0))   # squeeze a long line to fit the plaque
    for v in bmx.verts:
        v.co.x = (v.co.x - (x0 + x1) / 2) * sx
        v.co.y = v.co.y - y1 + y_top
    if sx < 1.0:
        print(f"[base] line squeezed to {100 * sx:.0f}% width to fit the plaque")

text = bmesh.new()
for bmx in (name_bm, title_bm):
    me = bpy.data.meshes.new("tmp"); bmx.to_mesh(me); bmx.free()
    text.from_mesh(me); bpy.data.meshes.remove(me)
bmesh.ops.remove_doubles(text, verts=text.verts, dist=1e-5)
for v in text.verts:
    v.co.z = FRONT - 0.3
faces = list(text.faces)
for f in faces:
    if f.normal.z < 0:
        f.normal_flip()
ext = bmesh.ops.extrude_face_region(text, geom=faces)
bmesh.ops.translate(text, verts=[g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)],
                    vec=(0, 0, 0.7))
bmesh.ops.recalc_face_normals(text, faces=text.faces)
bmesh.ops.triangulate(text, faces=text.faces)
slice_x(text, 1.0)
wrap(text)
bmesh.ops.recalc_face_normals(text, faces=text.faces)
txt = new_object("text", text, 2)

# ---------------------------------------------------------------- union
for operand in (plaque, txt):
    mod = base.modifiers.new("u", "BOOLEAN")
    mod.operation = "UNION"
    mod.solver = "EXACT"
    mod.object = operand
    if hasattr(mod, "material_mode"):
        mod.material_mode = "TRANSFER"
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier=mod.name)
    operand.hide_render = True
    operand.hide_set(True)

bm = bmesh.new()
bm.from_mesh(base.data)
bmesh.ops.triangulate(bm, faces=bm.faces)
V = np.array([v.co[:] for v in bm.verts])
F = np.array([[v.index for v in f.verts] for f in bm.faces], np.int64)
M = np.array([f.material_index for f in bm.faces], np.int64)
bm.free()
np.savez(out, V=V, F=F, M=M)
if opt["--blend"]:
    bpy.ops.wm.save_as_mainfile(filepath=opt["--blend"])
print(f"[base] {len(V)} verts, {len(F)} faces; materials {np.bincount(M, minlength=3).tolist()} -> {out}")
print(f"[base] bbox {V.min(0).round(2).tolist()} .. {V.max(0).round(2).tolist()}")
