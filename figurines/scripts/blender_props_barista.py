"""Blender (headless): add an espresso machine and a coffee-bean sack onto a name base, as ONE solid.

    blender -b --factory-startup --python scripts/blender_props_barista.py -- base.npz out.npz \
        [--top 30] [--machine-at 33,7] [--sack-at -33,4] [--blend out.blend]
        [--machine-out machine.npz [--pocket 1.2] [--clearance 0.2]]

With --machine-out the machine is NOT fused: it is written as its own part (flat bottom at z = 0)
and a pocket (--pocket deep, --clearance per side) is cut in the base top to glue it into. Use this
when the whole set needs more filaments than the printer has heads.

base.npz comes from blender_make_name_base.py (V, F, M; materials 0 base, 1 plaque, 2 text).
Adds, standing on the flat top (z = --top, front = -Y):
  * espresso machine (27 x 22 x 38 mm): bevelled body with a comb rack on top, a grey control panel
    with three knobs, a side knob, a grey brew recess with a drip tray, a portafilter (cone-shaped
    underside so it prints without support), a black handle and a white cup with a handle;
  * burlap sack (27 mm wide, 24 mm tall): bulging revolved body with a woven texture and soft folds,
    rolled rim, filled with a dome of coffee beans.
Everything is unioned (EXACT boolean, materials transferred). Extra materials:
3 black, 4 grey, 5 white, 6 sack tan, 7 beans. Writes out.npz with V, F, M.
"""
import math
import random
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
opt = {"--top": "30", "--machine-at": "33,7", "--sack-at": "-33,4", "--blend": None, "--machine-out": None,
       "--pocket": "1.2", "--clearance": "0.2"}
for i, a in enumerate(argv[2:]):
    if a in opt:
        opt[a] = argv[2:][i + 1]
TOP = float(opt["--top"])
MX, MY = map(float, opt["--machine-at"].split(","))
SX, SY = map(float, opt["--sack-at"].split(","))
SEPARATE = opt["--machine-out"] is not None      # machine printed on its own, glued into a pocket
POCKET, CLEAR = float(opt["--pocket"]), float(opt["--clearance"])

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
COLS = [(0.42, 0.27, 0.19), (0.89, 0.69, 0.29), (0.29, 0.18, 0.12), (0.1, 0.1, 0.1),
        (0.6, 0.64, 0.67), (0.95, 0.95, 0.93), (0.85, 0.63, 0.48), (0.23, 0.15, 0.1)]
MATS = []
for i, c in enumerate(COLS):
    m = bpy.data.materials.new(f"Color{i + 1}")
    m.diffuse_color = (*c, 1.0)
    MATS.append(m)
BASE, PLAQUE, TEXT, BLACK, GREY, WHITE, TAN, BEANS = range(8)


def to_object(name, bm, mat=None):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in MATS:
        me.materials.append(m)
    if mat is not None:
        for p in me.polygons:
            p.material_index = mat
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


def boolean(target, operand, op="UNION", self_overlap=False):
    mod = target.modifiers.new("b", "BOOLEAN")
    mod.operation = op
    mod.solver = "EXACT"
    mod.use_self = self_overlap          # operand made of overlapping pieces (beans) needs this
    mod.object = operand
    if hasattr(mod, "material_mode"):
        mod.material_mode = "TRANSFER"
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(operand)


def box(x0, x1, y0, y1, z0, z1, bevel=0.0, seg=2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=seg, affect="EDGES",
                        profile=0.5, clamp_overlap=True)
    return bm


def cylinder(r1, r2, length, matrix, seg=40, bevel=0.0):
    """Cone/cylinder along local +Z from 0 to length, then transformed by matrix."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r1, radius2=r2,
                          depth=length, matrix=Matrix.Translation((0, 0, length / 2)))
    if bevel > 0:
        top = [e for e in bm.edges if all(v.co.z > length - 1e-4 for v in e.verts)]
        bmesh.ops.bevel(bm, geom=top, offset=bevel, segments=3, affect="EDGES", profile=0.5,
                        clamp_overlap=True)
    bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)
    return bm


def revolve(profile, seg, radial=None, mat_of=None):
    """Closed solid from an (r, z) profile running bottom -> top, fan caps on the axis.
    radial(theta, r, z) -> new r lets the caller add folds / texture."""
    bm = bmesh.new()
    rings = []
    for (r, z) in profile:
        ring = []
        for j in range(seg):
            th = 2 * math.pi * j / seg
            rr = radial(th, r, z) if radial else r
            ring.append(bm.verts.new((rr * math.cos(th), rr * math.sin(th), z)))
        rings.append(ring)
    faces = []
    for k, (a, b) in enumerate(zip(rings[:-1], rings[1:])):
        for j in range(seg):
            f = bm.faces.new((a[j], a[(j + 1) % seg], b[(j + 1) % seg], b[j]))
            faces.append((f, k))
    c0 = bm.verts.new((0, 0, profile[0][1]))
    c1 = bm.verts.new((0, 0, profile[-1][1]))
    for j in range(seg):
        faces.append((bm.faces.new((rings[0][(j + 1) % seg], rings[0][j], c0)), 0))
        faces.append((bm.faces.new((rings[-1][j], rings[-1][(j + 1) % seg], c1)), len(profile) - 2))
    if mat_of:
        for f, k in faces:
            r = 0.5 * (profile[k][0] + profile[min(k + 1, len(profile) - 1)][0])
            z = 0.5 * (profile[k][1] + profile[min(k + 1, len(profile) - 1)][1])
            f.material_index = mat_of(r, z)
    return bm


def torus(R, r, matrix, seg=32, rseg=12):
    bm = bmesh.new()
    vs = [[bm.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
           for b in (2 * math.pi * q / rseg for q in range(rseg))] for a in (2 * math.pi * p / seg for p in range(seg))]
    for p in range(seg):
        for q in range(rseg):
            bm.faces.new((vs[p][q], vs[(p + 1) % seg][q], vs[(p + 1) % seg][(q + 1) % rseg], vs[p][(q + 1) % rseg]))
    bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)
    return bm


def resample(pts, step):
    outp = [pts[0]]
    for (r0, z0), (r1, z1) in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(math.hypot(r1 - r0, z1 - z0) / step)))
        outp += [(r0 + (r1 - r0) * t / n, z0 + (z1 - z0) * t / n) for t in range(1, n + 1)]
    return outp


def place(bm, x, y, z, rotz=0.0):
    bmesh.ops.transform(bm, matrix=Matrix.Translation((x, y, z)) @ Matrix.Rotation(rotz, 4, "Z"), verts=bm.verts)
    return bm


# ---------------------------------------------------------------- base from npz
d = np.load(src)
me = bpy.data.meshes.new("base")
me.from_pydata(d["V"].tolist(), [], d["F"].tolist())
for m in MATS:
    me.materials.append(m)
me.polygons.foreach_set("material_index", d["M"].astype(np.int32).tolist())
me.update()
base = bpy.data.objects.new("base", me)
scene.collection.objects.link(base)

# ---------------------------------------------------------------- espresso machine (local frame)
W, D, HM = 27.0, 22.0, 38.0
FY = -D / 2                                   # front face
ZB = -POCKET if SEPARATE else -0.6           # body bottom (sits in the pocket when separate)
mach = to_object("machine", box(-W / 2, W / 2, -D / 2, D / 2, ZB, HM, bevel=1.0), BLACK)
boolean(mach, to_object("recess", box(-10.5, 10.5, FY - 1, FY + 8, 4.5, 21.0), GREY), "DIFFERENCE")
parts = []
parts.append((box(-10.5, 10.5, FY - 1.2, FY + 8.5, 3.9, 5.6, bevel=0.4), GREY))           # drip tray
parts.append((box(-11, 11, FY - 0.8, FY + 0.6, 23.0, 34.0, bevel=0.5), GREY))              # control panel
for kx in (-6.5, 0.0, 6.5):                                                               # knobs
    parts.append((cylinder(2.5, 2.5, 3.3, Matrix.Translation((kx, FY + 0.5, 28.5)) @ Matrix.Rotation(math.pi / 2, 4, "X"),
                           bevel=0.6), BLACK))
parts.append((cylinder(1.6, 1.6, 2.4, Matrix.Translation((W / 2 - 0.4, -2.0, 27.0)) @ Matrix.Rotation(math.pi / 2, 4, "Y"),
                       bevel=0.4), BLACK))                                                 # side knob
for i in range(8):                                                                        # comb rack on top
    x = -W / 2 + 2.2 + i * (W - 4.4 - 1.4) / 7
    parts.append((box(x, x + 1.4, FY + 1.6, -FY - 1.6, HM - 0.5, HM + 2.2, bevel=0.3, seg=1), BLACK))
pfy = FY + 4.0
parts.append((cylinder(1.4, 4.2, 2.8, Matrix.Translation((0, pfy, 17.0))), GREY))          # portafilter cone
parts.append((cylinder(4.2, 4.2, 1.9, Matrix.Translation((0, pfy, 19.7))), GREY))          # portafilter top
ang = math.radians(-30)
hdir = Vector((math.cos(ang), math.sin(ang), 0))
hmat = Matrix.Translation((0, pfy, 19.6)) @ (Vector((0, 0, 1)).rotation_difference(hdir)).to_matrix().to_4x4()
parts.append((cylinder(1.5, 1.7, 19.0, hmat, seg=24, bevel=0.8), BLACK))                   # handle
cup = revolve([(2.3, 0.0), (2.5, 0.4), (3.3, 4.3), (3.1, 4.6), (2.6, 4.4)], 48)
parts.append((place(cup, 0, FY + 3.6, 5.4), WHITE))                                        # cup
parts.append((torus(1.25, 0.5, Matrix.Translation((3.6, FY + 3.6, 7.8)) @ Matrix.Rotation(math.pi / 2, 4, "X")), WHITE))
for k, (bm, mat) in enumerate(parts):
    boolean(mach, to_object(f"p{k}", bm, mat))

def export(ob, path, dz=0.0):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    # drop zero-volume slivers the boolean can leave between touching beans
    seen, junk = set(), []
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        isl, stack = [], [f0]
        seen.add(f0.index)
        while stack:
            f = stack.pop(); isl.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index); stack.append(g)
        vol = sum(f.verts[0].co.dot(f.verts[1].co.cross(f.verts[2].co)) for f in isl) / 6
        if abs(vol) < 0.05:
            junk += isl
    if junk:
        print(f"[props] removed {len(junk)} faces of zero-volume slivers")
        bmesh.ops.delete(bm, geom=junk, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.verts.index_update(); bm.faces.index_update()
    V = np.array([v.co[:] for v in bm.verts]) + [0, 0, dz]
    F = np.array([[v.index for v in f.verts] for f in bm.faces], np.int64)
    M = np.array([f.material_index for f in bm.faces], np.int64)
    bm.free()
    np.savez(path, V=V, F=F, M=M)
    return V, F, M


if SEPARATE:
    Vm, Fm, Mm = export(mach, opt["--machine-out"], dz=POCKET)        # own print, flat bottom at z = 0
    print(f"[props] machine part {len(Fm)} faces, {Vm.min(0).round(2).tolist()} .. {Vm.max(0).round(2).tolist()}"
          f" -> {opt['--machine-out']} (assembled: shift by {MX}, {MY}, {TOP - POCKET})")
    bpy.data.objects.remove(mach)
    c = CLEAR
    boolean(base, to_object("pocket", box(MX - W / 2 - c, MX + W / 2 + c, MY - D / 2 - c, MY + D / 2 + c,
                                          TOP - POCKET, TOP + 5), BASE), "DIFFERENCE")
else:
    bm = bmesh.new(); bm.from_mesh(mach.data)
    place(bm, MX, MY, TOP)
    bm.to_mesh(mach.data); bm.free()
    boolean(base, mach)

# ---------------------------------------------------------------- coffee sack (local frame)
# Squat burlap sack as in the art: wide flat bottom with a big rounded corner, near-vertical sides,
# a pinch under a thick rolled cuff, diagonal woven ribs, and a heaped dome of large beans.
prof = [(10.0, 0.0), (11.6, 0.4), (12.6, 1.3), (13.3, 2.8), (13.7, 5.0), (13.8, 7.5), (13.6, 10.5),
        (13.2, 13.2), (12.8, 15.3), (12.6, 16.4), (13.4, 17.1), (14.2, 18.0), (14.6, 19.5), (14.6, 21.0),
        (14.2, 22.4), (13.4, 23.4), (12.3, 24.0), (11.2, 24.1), (10.4, 23.8), (9.9, 23.2), (9.6, 22.6),
        (8.0, 23.5), (6.0, 24.3), (4.0, 24.8), (2.0, 25.1)]
BED = [(9.6, 22.6), (8.0, 23.5), (6.0, 24.3), (4.0, 24.8), (2.0, 25.1), (0.0, 25.15)]
prof = resample(prof, 0.25)
RIB_N, RIB_K = 69, 2 * math.pi * 0.57             # diagonal ribs: ~1 mm pitch at 35 degrees


def bed_z(r):
    for (r0, z0), (r1, z1) in zip(BED[:-1], BED[1:]):
        if r1 <= r <= r0:
            return z0 + (z1 - z0) * (r0 - r) / (r0 - r1)
    return BED[-1][1]


def sack_r(th, r, z):
    fold = 1 + 0.025 * math.sin(3 * th + 0.2 * z) + 0.015 * math.sin(7 * th + 1.3)
    dent = 0.55 * math.exp(-((math.atan2(math.sin(th - 2.6), math.cos(th - 2.6))) ** 2) / 0.08) \
        * math.exp(-((z - 11.0) / 4.0) ** 2)       # one soft fold on the left side
    rib = 0.12 * math.sin(RIB_N * th + RIB_K * z) if (0.9 < z < 23.6 and not (r < 9.95 and z > 22.4)) else 0.0
    return r * fold - dent + rib


sack = to_object("sack", revolve(prof, 360, sack_r, lambda r, z: BEANS if (r < 9.65 and z > 22.4) else TAN))
rng = random.Random(11)
beans = bmesh.new()
placed = []
while len(placed) < 40:
    rr = 8.8 * math.sqrt(rng.random())
    th = rng.random() * 2 * math.pi
    x, y = rr * math.cos(th), rr * math.sin(th)
    if any((x - a) ** 2 + (y - b) ** 2 < 2.1 ** 2 for a, b in placed):
        continue
    placed.append((x, y))
    tmp = bmesh.new()
    bmesh.ops.create_uvsphere(tmp, u_segments=18, v_segments=10, radius=1.0)
    bmesh.ops.scale(tmp, vec=(1.7, 1.15, 0.8), verts=tmp.verts)
    bmesh.ops.transform(tmp, matrix=Matrix.Translation((x, y, bed_z(rr) + 0.3)) @ Matrix.Rotation(rng.random() * math.pi, 4, "Z")
                        @ Matrix.Rotation(rng.uniform(-0.35, 0.35), 4, "X"), verts=tmp.verts)
    me_t = bpy.data.meshes.new("bt"); tmp.to_mesh(me_t); tmp.free()
    beans.from_mesh(me_t); bpy.data.meshes.remove(me_t)
boolean(sack, to_object("beans", beans, BEANS), self_overlap=True)
bm = bmesh.new(); bm.from_mesh(sack.data)
place(bm, SX, SY, TOP - 0.5)
bm.to_mesh(sack.data); bm.free()
boolean(base, sack)

# ---------------------------------------------------------------- export
V, F, M = export(base, out)
if opt["--blend"]:
    bpy.ops.wm.save_as_mainfile(filepath=opt["--blend"])
print(f"[props] {len(V)} verts, {len(F)} faces; per material {np.bincount(M, minlength=8).tolist()} -> {out}")
print(f"[props] bbox {V.min(0).round(2).tolist()} .. {V.max(0).round(2).tolist()}")
