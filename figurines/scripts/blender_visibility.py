"""Blender (headless) helper: which vertices can a front-on, orthographic camera see?

Run by photo_project_colorize.py, not by hand:

    blender -b --factory-startup --python scripts/blender_visibility.py -- in.npz out.npy

in.npz holds V (n,3) vertices in the final mm frame (Z up, camera looks along +Y from -Y),
F (m,3) faces, and N (n,3) vertex normals. For every vertex whose normal faces the camera,
a ray is cast from just in front of the vertex toward the camera (-Y) through Blender's BVH;
any hit means something sits between the vertex and the photo, so it must not take a photo
colour. Writes a bool array (n,) to out.npy.
"""
import sys
import time

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
min_facing = float(argv[2]) if len(argv) > 2 else 0.0

d = np.load(src)
V, F, N = d["V"], d["F"], d["N"]
t0 = time.time()
tree = BVHTree.FromPolygons(V.tolist(), F.tolist(), all_triangles=True)
print(f"[blender] BVH over {len(F):,} faces in {time.time() - t0:.1f}s")

span = float(V[:, 1].max() - V[:, 1].min())
eps = 1e-4 * span + 1e-6
toward_cam = Vector((0.0, -1.0, 0.0))
facing = (-N[:, 1]) > min_facing
vis = np.zeros(len(V), bool)
t0 = time.time()
for i in np.flatnonzero(facing):
    x, y, z = V[i]
    nx, ny, nz = N[i]
    # start a hair off the surface (along the normal and toward the camera) so the ray does not
    # immediately hit the faces that share this vertex
    o = Vector((x + nx * eps, y + ny * eps - eps, z + nz * eps))
    hit, _, _, _ = tree.ray_cast(o, toward_cam, span * 2)
    vis[i] = hit is None
print(f"[blender] {int(facing.sum()):,} facing verts ray-cast in {time.time() - t0:.1f}s; "
      f"{int(vis.sum()):,} visible ({100 * vis.mean():.1f}% of all)")
np.save(dst, vis)
