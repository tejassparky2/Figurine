# Open-source libraries and projects: texture to mesh colour, N-colour quantisation, multi-colour 3MF writing (as of 2026-11-17)

Scope note: this covers (a) moving texture colour onto vertices/faces, (b) reducing to N flat filament colours with clean boundaries, (c) writing 3MF that Bambu Studio / OrcaSlicer / PrusaSlicer read, plus existing open-source end-to-end converters. Method: GitHub repository search API (stars/last-push read 2026-11-17), raw READMEs and source files fetched from GitHub, PyPI JSON metadata, official docs. I also ran an install and smoke test on **Python 3.13.18, Linux, CPU only** in a scratch venv (results marked "tested here"). Slicer source citations are from `master`/`main` branches fetched 2026-11-17. Line numbers are approximate and will drift.

## Q1. Texture to vertex/face colour: which tools give per-face colour with proper texel averaging?

### Takeaway
None of the off-the-shelf libraries gives true per-face, area-integrated texel averaging in one call. trimesh, PyMeshLab, Open3D and Blender all sample at points: vertices, corners, a nearest pixel, or random surface points. Per-face colour then comes from a second step that averages 3 vertex colours (PyMeshLab "Vertex to Face") or from Monte-Carlo sampling. The best ready-made primitive for proper per-face averaging is `trimesh.sample.sample_surface(..., sample_color=True)`, which returns `face_index`; you then `np.bincount` the samples per face. A hand-rolled UV-space rasteriser per triangle is still the most exact option.

### Cited Findings
**trimesh (MIT, pure-Python wheel; v5.2.1 released 2026-11-12, requires Python >=3.10)**
- `TextureVisuals.to_color()` converts to `ColorVisuals` with **vertex** colours: `colors = self.material.to_color(self.uv)` then `ColorVisuals(vertex_colors=colors)`. One sample per UV-vertex, no face averaging. — [trimesh/visual/texture.py](https://github.com/mikedh/trimesh/blob/main/trimesh/visual/texture.py) (inspected from the installed 5.2.1 source, tested here)
- `trimesh.visual.color.uv_to_color(uv, image)` is a **nearest-pixel** lookup: `x = uv[:,0]*(w-1)`, `y = (1-uv[:,1])*(h-1)`, then `.round()` into the RGBA array. No bilinear filtering and no mip/area averaging. `uv_to_interpolated_color(uv, image)` also exists (bilinear). `PBRMaterial.to_color` uses `baseColorTexture` and falls back to `baseColorFactor`. — [trimesh/visual/color.py](https://github.com/mikedh/trimesh/blob/main/trimesh/visual/color.py), [trimesh/visual/material.py](https://github.com/mikedh/trimesh/blob/main/trimesh/visual/material.py) (tested here)
- `trimesh.sample.sample_surface(mesh, count, face_weight=None, sample_color=False, return_barycentric=False, seed=None)`: when `sample_color` is set and the mesh has UVs, it interpolates each sample's UV from the face corners. It returns sample points, **face_index** and colours, which allows area-weighted Monte-Carlo per-face averaging. — [trimesh/sample.py](https://github.com/mikedh/trimesh/blob/main/trimesh/sample.py) (signature and code inspected, tested here)
- trimesh's 3MF exporter (`trimesh.exchange.threemf.export_3MF`) writes **no colour** (no `pid`/`colorgroup`/`basematerials` in the code), and `load_3MF` does not read colorgroup/basematerials either (5.2.1). — [trimesh/exchange/threemf.py](https://github.com/mikedh/trimesh/blob/main/trimesh/exchange/threemf.py) (grep of installed source, tested here)
- The everything3d/figurine-colorize project pins `trimesh==4.12.2` and `numpy==2.3.3` with the comment "Newer numpy (2.5) / trimesh (5.x) break the face pass". This is a compatibility warning for the current pip defaults (numpy 2.5.5, trimesh 5.2.1 installed here). — [figurine-colorize requirements.txt](https://github.com/everything3d/figurine-colorize/blob/main/requirements.txt)

**PyMeshLab (GPL-3.0; 2025.7.post1 uploaded 2026-01-30; manylinux wheels for cp310–cp314, cp313 wheel confirmed by pip dry-run here)**
Exact filter names (Python id → MeshLab name), from the official filter list — [PyMeshLab filter list](https://pymeshlab.readthedocs.io/en/latest/filter_list.html):
- `compute_color_from_texture_per_vertex`: "Transfer Color: Texture to Vertex" (same mesh). Per-vertex only.
- `transfer_texture_to_color_per_vertex`: "Transfer: Texture to Vertex Color (1 or 2 meshes)". Params `sourcemesh`, `targetmesh`, `upperbound` (max search distance, default 2%). Samples the source texture onto the target mesh's vertices. Useful for textured Tripo/AI mesh → separate watertight print mesh.
- `transfer_attributes_per_vertex`: "Vertex Attribute Transfer". For each target vertex it finds the closest **point** (not vertex) on the source and copies interpolated attributes. `vertexsampling` toggles closest-vertex mode. "Assumes that the two meshes are reasonably similar and aligned."
- `compute_color_transfer_vertex_to_face`: "Transfer Color: Vertex to Face". This is the only route to per-face colour (mean of vertex colours, so not texel-averaged). `compute_color_transfer_face_to_vertex` and `compute_color_transfer_mesh_to_face` ("Mesh to Face") also exist.
- Reverse direction: `transfer_attributes_to_texture_per_vertex` (vertex colour, normal or texture → another mesh's texture), `compute_texmap_from_color` (vertex colour → texture, pull-push fill).
- There is **no** "texture → face colour" filter in the list (searched all 280 ids for texture/color/transfer).

**Open3D (MIT; 0.20.0 uploaded 2026-09-16; cp310–cp314 manylinux_2_35 wheels)** — [PyPI open3d](https://pypi.org/project/open3d/)
- Tensor API `open3d.t.geometry.TriangleMesh.sample_points_uniformly(number_of_points, use_triangle_normal=False)`: "If texture_uvs and albedo are present, these are used to estimate the sampled point color". It returns a PointCloud plus an "areas" attribute. The face index is not documented as an output. — [Open3D t.TriangleMesh docs](https://www.open3d.org/docs/release/python_api/open3d.t.geometry.TriangleMesh.html)
- `bake_vertex_attr_textures` and `bake_triangle_attr_textures` go in the **opposite** direction (attributes → texture, CPU only). `project_images_to_albedo` back-projects calibrated photos to a texture, and `compute_uvatlas` builds UVs. I found no texture → vertex/face colour function. — [Open3D t.TriangleMesh docs](https://www.open3d.org/docs/release/python_api/open3d.t.geometry.TriangleMesh.html)

**libigl Python (MPL-2.0; 2.6.3 uploaded 2026-09-01)**
- Ships a `cp312-abi3` manylinux wheel, which pip resolves on Python 3.13 (dry-run here). — [PyPI libigl](https://pypi.org/project/libigl/)
- I found no texture-sampling function documented for it (see Gaps).

**Blender 4.5 LTS (Blender 4.5.16 LTS is the installed binary here)**
- Cycles bake **Output → Target**: "Image Textures: Bake to the image data-block associated with the Active Image Texture node … Active Color Attribute: Bake to the Active Color Attributes layer on the active mesh."
- Diffuse/Glossy/Transmission contributions have Direct / Indirect / Color toggles: "If only Color is selected you get the pass color, which is a property of the surface and independent of sampling refinement." This gives a lighting-free albedo bake.
- "Selected to Active" baking transfers from one mesh to another, with cage and max ray distance options. — [Blender 4.5 manual: Render Baking](https://docs.blender.org/manual/en/4.5/render/cycles/baking.html)
- `bpy` on PyPI: 5.3.0 (2026-11-10) requires Python `==3.13.*` (GPL-3.0). The Blender 4.5 binary in the environment would be driven with `blender -b --python`. — [PyPI bpy](https://pypi.org/project/bpy/)

**Other**
- JulianKnodt/texture_to_vert_colors (Rust, no licence file, 2★, pushed 2026-06-29): "Convert a 2D image texture to vertex colors with minimal introduced faces". This is texture-aware remeshing, so colour boundaries become geometry, from a research paper. — [GitHub](https://github.com/JulianKnodt/texture_to_vert_colors)
- Omegadarling/painted2printed (Blender add-on) samples **per-face** sRGB from image UV / colour attribute / flat material. It bakes the palette index into a **CORNER** colour attribute, then optionally voxel-remeshes and re-transfers colour by BVH. — [painted2printed README](https://github.com/Omegadarling/painted2printed)

### Inferences
- For a figurine pipeline where faces must carry one filament each, the cleanest library-based route on CPU is Monte-Carlo per-face averaging:
  1. Load the GLB with trimesh (`process=False` to keep face order).
  2. Run `sample_surface(mesh, N≈20–50×faces, sample_color=True)`.
  3. Convert the sample colours to Lab and average per `face_index`, or take the per-face median to reject seam or shadow outliers.
  4. Back-fill faces that received no samples from their own UV centroid.
  This avoids per-vertex smearing across UV seams. An exact alternative is to rasterise each triangle's UV footprint, but no listed library provides that.
- PyMeshLab's per-vertex → per-face route (`compute_color_from_texture_per_vertex` then `compute_color_transfer_vertex_to_face`) loses texture detail inside large triangles and blurs across colour edges. That is acceptable only on dense meshes.
- For the two-mesh case (textured AI mesh → repaired/watertight print mesh), three options exist: PyMeshLab `transfer_texture_to_color_per_vertex`, Blender "Selected to Active" bake to a colour attribute, or trimesh `proximity.closest_point` plus barycentric UV lookup. Blender bakes sample points or corners rather than integrating over the face (inference from the manual's description; not verified in code).
- GPU: none of these need CUDA. Blender Cycles baking runs on CPU (slower). Open3D's bake functions are explicitly CPU-only.

### Gaps
- I did not find documentation for a texture-sampling helper in libigl's Python bindings. It provides geometry primitives (adjacency, components) but was not verified function-by-function.
- I did not verify in Blender source whether colour-attribute baking supersamples per vertex or corner, or how Face-Corner versus Point domains differ in sampling density.
- Open3D's `sample_points_uniformly` does not document returning a triangle index, so per-face averaging with it is unconfirmed.

## Q2. Quantisation and regularisation on meshes (k-means/Lab, ΔE2000, MRF/graph-cut, smoothing, island removal): which packages install cleanly on Python 3.12/3.13?

### Takeaway
On Python 3.13 the dependable stack is:
- **scikit-learn** for KMeans/MiniBatchKMeans.
- **scikit-image** or **colour-science** for Lab conversion and ΔE2000.
- **PyMaxflow** for graph cut, with binary manylinux wheels up to cp313.
- **scipy.sparse.csgraph** for island removal.

Alternatives and dead ends:
- **gco-wrapper** (multi-label alpha-expansion with a general graph) has no cp313 wheel but built from sdist here with a compiler.
- **pygco** fails to build.
- **gco** (2022) has no cp313 wheel.
- **colorthief** and **pyciede2000** are old pure-Python packages that add nothing over scikit-image.

Existing projects converge on the same recipe:
1. Lab with down-weighted L (or OkLab).
2. k-means++.
3. Face-adjacency smoothing.
4. MRF / ICM or alpha-expansion.
5. Small-island merge into the neighbour with the longest shared boundary.

### Cited Findings
**Install status on Python 3.13 (Linux x86_64)**
- scikit-learn 1.9.1 (2026-09-10, BSD-3): cp311–cp315 Linux wheels, requires >=3.11. Has `KMeans`, `MiniBatchKMeans`, `BisectingKMeans`, `MeanShift` (installed and imported here). — [PyPI scikit-learn](https://pypi.org/project/scikit-learn/)
- scikit-image 0.26.0 (2025-12-20): cp311–cp314 wheels. `skimage.color` has `rgb2lab`, `lab2rgb`, `deltaE_ciede2000`, `deltaE_ciede94`, `deltaE_cie76`, `deltaE_cmc` (installed here). — [PyPI scikit-image](https://pypi.org/project/scikit-image/)
- colour-science 0.4.7 (2025-12-06, BSD-3): pure Python, requires >=3.11,<3.15. `colour.delta_E(..., method='CIE 2000')` is available; methods include CIE 2000, CAM16-UCS, DIN99 and HyAB (installed here; warns if matplotlib is absent). — [PyPI colour-science](https://pypi.org/project/colour-science/)
- colorthief 0.2.1, last release 2017-02-09, BSD, py2 wheel, image-only palette extraction. — [PyPI colorthief](https://pypi.org/project/colorthief/)
- pyciede2000 0.0.21, last release 2021-05-16, MIT. — [PyPI pyciede2000](https://pypi.org/project/pyciede2000/)
- PyMaxflow 1.3.2 (2024-11-25, GPL): cp39–cp313 manylinux wheels. `maxflow.fastmin` exposes `aexpansion_grid`, `abswap_grid`, `energy_of_grid_labeling`, `aexpansion_grid_step`, which are **grid-only** multi-label helpers. A mesh face graph needs your own expansion loop over `maxflow.Graph` (installed and imported here). — [PyPI PyMaxflow](https://pypi.org/project/PyMaxflow/)
- gco-wrapper 3.0.9 (2023-06-13, MIT wrapper around Veksler/Delong GCO): wheels only up to cp311. On Python 3.13, `pip install gco-wrapper` **built from sdist successfully** here (a compiler was available). `gco.cut_general_graph(edges, edge_weights, unary, pairwise, n_iter=-1, algorithm='expansion')` returned the correct labelling on a 4-node test. Also has `cut_grid_graph` and a `GCO` class. — [PyPI gco-wrapper](https://pypi.org/project/gco-wrapper/) (tested here)
- gco 2.0.2 (2022-10-21): wheels cp38–cp311 only, so pip found no cp313 binary. — [PyPI gco](https://pypi.org/project/gco/)
- pygco 0.0.16 (2018, sdist only): **failed to build** on Python 3.13 here ("Failed to build 'pygco' when getting requirements to build wheel"). — [PyPI pygco](https://pypi.org/project/pygco/) (tested here)
- networkx 3.7 (2026-09-21, requires >=3.12), igraph 1.0.0 (GPL, abi3 wheel), scipy 1.18.1 (cp312–cp315) are all installable on 3.13 per PyPI metadata. — [PyPI networkx](https://pypi.org/project/networkx/), [PyPI igraph](https://pypi.org/project/igraph/), [PyPI scipy](https://pypi.org/project/scipy/)
- Also cp313-ready per PyPI:
  - fast-simplification 0.2.0 (MIT, decimation)
  - xatlas 0.0.11 (MIT, UV atlas)
  - potpourri3d 1.4.0 (MIT, geodesics)
  - manifold3d 3.5.5 (Apache-2.0, booleans)
  - embreex 4.4.0.post1 (fast ray queries for trimesh)
  - pymeshlab
  - open3d
  — [PyPI](https://pypi.org/project/manifold3d/)

**Mesh-colour smoothing and cleanup filters in PyMeshLab** — [PyMeshLab filter list](https://pymeshlab.readthedocs.io/en/latest/filter_list.html)
- `apply_color_laplacian_smoothing_per_face` ("Smooth: Laplacian Face Color", param `iteration`) and `apply_color_laplacian_smoothing_per_vertex` do plain Laplacian blurring, which is not edge-preserving.
- `compute_selection_by_color_per_face` ("Select Faces by Color", HSV/RGB tolerance).
- `compute_selection_by_small_disconnected_components_per_face` and `meshing_remove_connected_component_by_face_number` work on **geometric** components, not colour regions.

**Algorithms used by existing open-source converters (useful reference designs)**
- tejaswigowda/3mf-webCLI documents its full segmentation pipeline (described as a reimplementation of Pythia's approach):
  1. "Chroma-weighted Lab": L scaled by **0.35** so baked shading does not create bands.
  2. "k-means++ × 3 restarts".
  3. "Edge-aware label smoothing": up to 8 rounds of weighted majority vote, `w = 0.6 + 0.4·exp(−(ΔLab/18)²)`.
  4. "MRF refinement (ICM)": `dataCost − 24 · neighborAgreement`, up to 20 sweeps.
  5. "Small-island dissolve": components <1% of faces go to the label sharing the most boundary edges.
  It also uses an inertia-elbow auto-K and welds vertices by quantised position to build adjacency. — [3mf-webCLI README](https://github.com/tejaswigowda/3mf-webCLI)
- everything3d/figurine-colorize `clean_colorize.py` runs a global graph-cut on `E = Σ_faces area·|colour(face) − palette[label]| + λ Σ_edges length·crease(edge)·[label_i ≠ label_j]`. `crease()` falls to ~0 at concave creases, so boundaries snap to sculpted edges. It is solved with alpha-expansion (PyMaxflow). Islands under `--min-island` mm² merge into the neighbour sharing the longest boundary. Knobs: `--lam` 6, `--sigma` 25°, `--min-island` 0.4 mm². It supports `--only/--forbid/--prefer` box constraints and `--black-max-chroma`, and uses `scipy.sparse.csgraph.connected_components`. — [clean_colorize.py](https://github.com/everything3d/figurine-colorize/blob/main/scripts/clean_colorize.py)
- williamsexton/tex2multimaterial quantises the **texture image** in OkLab with a chroma boost, using "Median-Cut + K-means". It then samples the quantised texture **at each face centroid** and writes a multi-material OBJ/MTL. — [tex2multimaterial README](https://github.com/williamsexton/tex2multimaterial)
- rtwfroody/ditherforge works in CIELAB:
  - "Color warp" uses Gaussian RBF in CIELAB.
  - A "color similarity threshold" pulls voxels toward the nearest palette colour by up to a ΔE distance "to reduce noise".
  - "Confine dither to color regions" stops error from crossing sharp boundaries.
  - Dither mode `none` snaps each cell to the nearest palette colour.
  Its default is dithering, which is the opposite of flat regions. — [ditherforge README](https://github.com/rtwfroody/ditherforge)
- Omegadarling/painted2printed runs k-means with "Quantize In: Perceptual (Lab) (best), Linear, or sRGB" and a seed for determinism. — [painted2printed README](https://github.com/Omegadarling/painted2printed)
- tntpsu/paint-to-print-3d does "texture-region segmentation with morphological cleanup". It has a cleanup candidate that is "only promote[d] … when it improves island/component counts", and reports "too many tiny color islands" as the core problem with AI models. — [paint-to-print-3d README](https://github.com/tntpsu/paint-to-print-3d)
- Bambu Studio itself clusters imported colours with `QuantKMeans quant(10); quant.apply(input_colors, cluster_colors, labels, cluster_number, max_cluster)` (`obj_color_deal_algo`). This is shared by the multi-colour OBJ import and the standard-3MF colour import dialog. — [BambuStudio ObjColorUtils.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/ObjColorUtils.cpp)

### Inferences
- For "N flat colours with clean boundaries", plain k-means alone is insufficient. All mature projects add spatial regularisation on the face-adjacency graph.
- Ranked by quality vs effort on CPU / Python 3.13:
  1. `gco.cut_general_graph` (true multi-label alpha-expansion on an arbitrary graph, one call, but sdist build).
  2. PyMaxflow with a hand-written expansion loop (binary wheel; this is what figurine-colorize does).
  3. ICM / majority-vote smoothing in numpy (no deps, gets stuck in local minima).
- PyMaxflow's `fastmin` helpers are grid-only, so they cannot be used directly on meshes.
- Down-weighting L (×0.35 in 3mf-webCLI) or using a shading-robust feature is the common cheap fix for baked-in shadows in AI textures turning into extra colours.
- Licence implications: PyMaxflow is GPL and pymeshlab is GPL-3.0. That matters only if the pipeline is distributed. gco-wrapper's wrapper is MIT, but the bundled GCO C++ library has its own terms (see Gaps).

### Gaps
- I did not verify the licence text of the GCO v3 C++ library bundled in gco-wrapper. Historically it was distributed for research use, so this should be checked before commercial distribution.
- I found no maintained Python package for bilateral or mean-shift filtering of colours **on a mesh graph**. `sklearn.cluster.MeanShift` works in colour space only; mesh-aware versions would be hand-rolled.
- pymeshlab and open3d were confirmed as cp313 wheels by pip dry-run but not actually installed or run here because of size.

## Q3. Writing multi-colour 3MF for Bambu Studio / OrcaSlicer / PrusaSlicer: formats, exact attribute names, libraries

### Takeaway
Three slicer-specific per-triangle formats matter:
- **Bambu/Orca `paint_color`**: an uppercase hex string per `<triangle>`, filament 1 = "4", 2 = "8", 3 = "0C", 4 = "1C", … 16 = "DC". This is the only per-triangle colour that **OrcaSlicer** honours.
- **PrusaSlicer `slic3rpe:mmu_segmentation`**: the same TriangleSelector bit encoding. PrusaSlicer master is moving to a JSON sidecar but still dual-writes and reads the attribute.
- **Standard Materials-extension colours** (`m:colorgroup` / `basematerials` with per-triangle `pid`/`p1`): Bambu Studio ≥2.5 imports these through a "standard 3MF colour import" dialog only when the file's `Application` metadata does **not** start with `BambuStudio-`.

lib3mf (BSD, wheel works on 3.13) writes standard colorgroups and basematerials but has **no API for `paint_color`**. Bambu-native files need hand-written XML (zip plus string templates), as ditherforge and figurine-colorize do.

### Cited Findings
**Bambu Studio (`bbs_3mf.cpp`, master)** — [BambuStudio bbs_3mf.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Format/bbs_3mf.cpp)
- Constants (≈lines 332–337): `CUSTOM_SUPPORTS_ATTR = "paint_supports"`, `CUSTOM_SEAM_ATTR = "paint_seam"`, `MMU_SEGMENTATION_ATTR = "paint_color"`, `FACE_PROPERTY_ATTR = "face_property"`. Fuzzy skin is also read (`custom_fuzzy_skin`).
- Project files (≈lines 165–176): `Metadata/project_settings.config`, `Metadata/model_settings.config`, `Metadata/_rels/model_settings.config.rels`, `Metadata/slice_info.config`, thumbnail `Metadata/plate_1.png`.
- Native detection (≈line 4575): `m_is_bbl_3mf = true` only when `<metadata name="Application">` starts with `"BambuStudio-"`.
- `paint_color` is read for every triangle regardless of vendor (`mmu_segmentation.push_back(... MMU_SEGMENTATION_ATTR)`, ≈line 4427) and applied via `volume->mmu_segmentation_facets.set_triangle_from_string(...)`.
- For **non-Bambu** files (`if (!m_is_bbl_3mf)`), each triangle's `pid` and `p1/p2/p3` (or the object's `pid`/`pindex`) are recorded as `TriangleColor`.
- A comment (≈line 923) says "basematerials, compositematerials and multiproperties of a standard 3MF [are] read into the color group map as one color per entry, so triangles bound to them resolve like the ones bound to an m:colorgroup".
- Each unique colour string is mapped to a new extruder id (`color_to_extruder_id_map`, ≈lines 2456–2476).
- Texture resources are ignored: "The standard 3MF color import does not read texture images, so textures are ignored" (≈line 209).
- `set_triangle_from_string` **rejects anything but uppercase hex**: "get_triangle_as_string only emits upper case digits. Drop the whole triangle on anything else". — [BambuStudio Model.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Model.cpp)
- Lookup table `CONST_FILAMENTS = {"", "4", "8", "0C", "1C", "2C", "3C", "4C", "5C", "6C", "7C", "8C", "9C", "AC", "BC", "CC", "DC" /*16*/, "EC", "0FC", "1FC", … "EFC" /*32*/}` (Model.cpp ≈line 58). — [BambuStudio Model.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Model.cpp)
- Encoding (TriangleSelector::serialize): "Each triangle is encoded by 4 bits (xxyy) or 8 bits (zzzzxxyy): leaf triangle: xx = EnforcerBlockerType (0,1,2; 3 = indicator for additional 4 bits), yy = 0 … non-leaf: xx = special side, yy = number of split sides". Children are serialised in reverse order "for compatibility with PrusaSlicer 2.3.1". The string is built nibble-by-nibble and prepended, so it reads reversed. Sub-triangle painting (finer boundaries without remeshing) is possible through split codes. — [BambuStudio TriangleSelector.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/TriangleSelector.cpp)
- State enum: `EnforcerBlockerType { NONE=0, ENFORCER=1, BLOCKER=2, …, Extruder1 = ENFORCER, Extruder2 = BLOCKER, Extruder3, … }`, a 1-based filament id. — [BambuStudio Model.hpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Model.hpp)
- The standard 3MF colour import uses a preview (`standard_3mf_to_textured_meshes`, "Preview mesh for the standard 3MF import dialog") and k-means clustering (`obj_color_deal_algo` / `QuantKMeans`). — [BambuStudio ObjColorUtils.hpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/ObjColorUtils.hpp)
- Bambu Studio 2.5.0.64 release notes: "Added support for importing standard 3MF files with color information. After import, the workflow is similar to multi-color OBJ: select the color data to map and apply colors." Also: "Currently, only face color and vertex color data are supported. For texture-colored 3MF files, only face data will be imported." and "Color attributes will be lost after subdivision." — [newreleases.io: BambuStudio v02.05.00.64](https://newreleases.io/project/github/bambulab/BambuStudio/release/v02.05.00.64)
- v2.8.2 reportedly "Fixed incorrect slicing colors bleeding into adjacent objects when importing standard multi-color 3MF files with single-color volumes (#11348)". — [newreleases.io: v02.08.02.60](https://newreleases.io/project/github/bambulab/BambuStudio/release/v02.08.02.60) (seen only in a search-result summary, not opened)

**OrcaSlicer (main)**
- `bbs_3mf.cpp` also uses `MMU_SEGMENTATION_ATTR = "paint_color"` (≈line 363) and sets `m_is_bbl_3mf` for `Application` starting with `"BambuStudio-"`, with a separate branch for `"OrcaSlicer-"` (≈lines 4192–4196).
- Its colorgroup handling stores one colour per group id (`m_group_id_to_color[m_current_color_group] = color`) and maps it to an extruder only through the **object-level** `pid` (`color_group_id_to_extruder_id_map.find(current_object->second.pid)`, ≈line 2326).
- I found no per-triangle `TriangleColor` import in this file. — [OrcaSlicer bbs_3mf.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/Format/bbs_3mf.cpp)
- Orca's PrusaSlicer-format importer has `MMU_SEGMENTATION_ATTR = "slic3rpe:mmu_segmentation"` (≈line 143). — [OrcaSlicer 3mf.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/Format/3mf.cpp)
- painted2printed's README independently states: "Splitting is mainly useful for **OrcaSlicer** (which ignores per-triangle 3MF colors)". — [painted2printed README](https://github.com/Omegadarling/painted2printed)

**PrusaSlicer (master, restructured source tree)**
- `Legacy::MM_SEGMENTATION_ATTR = "slic3rpe:mmu_segmentation"`, plus `<metadata name="slic3rpe:MmPaintingVersion">` (always "1" when dual-writing). — [PrusaSlicer LegacyPaintingCompat.hpp](https://github.com/prusa3d/PrusaSlicer/blob/master/src/slic3r-shared/include/Slic3r/Biz/Format/3mf/LegacyPaintingCompat.hpp)
- The new core-spec writer stores painting in `Metadata/Slic3r_facets_annotation.json` and "dual-write[s] MM segmentation into legacy slic3rpe:mmu_segmentation triangle attributes … so 2.x readers … still see it", only when the painting fits version 1.
- `last_old_stored_version = 2.99.1` ("last version to be parsed by legacy parser"), and files without `Application` metadata route to the legacy loader. — [PrusaSlicer Model3mf.cpp](https://github.com/prusa3d/PrusaSlicer/blob/master/src/slic3r-shared/src/Slic3r/Biz/Format/3mf/Model3mf.cpp)
- Panda2Prusa (MIT, 37★, pushed 2026-11-11) converts Bambu → PrusaSlicer 3MF. It handles "colour (`paint_color` → `mmu_segmentation`) … transcoded when extruders are renumbered" and per-part extruders as PrusaSlicer volumes with `firstid`/`lastid`. It reads Bambu settings from `Metadata/project_settings.config`. — [Panda2Prusa README](https://github.com/CupsOhJoe/Panda2Prusa)
- 3MFTool / prusa_mmu_painter (C#/.NET 8, Windows-only, 0★, pushed 2026-01-06) exports `slic3rpe:mmu_segmentation` and describes the per-triangle quadtree; its wiki page "MMU-Segmentation-Format.md" documents the encoding. The licence is inconsistent: badge and GitHub say Unlicense, README text says MIT. — [prusa_mmu_painter README](https://github.com/coreynguyen/prusa_mmu_painter)

**Standard 3MF Materials extension**
- Namespace prefix `m` = `http://schemas.microsoft.com/3dmanufacturing/material/2015/02`. `<colorgroup>` holds `<color color="#RRGGBB[AA]">` entries indexed from 0, and triangles reference them via `pid` plus `p1/p2/p3`. `<texture2dgroup>` holds `<tex2coord u v>`. `basematerials` (with `displaycolor`) belongs to the core spec. — [3MF Materials and Properties Extension spec](https://github.com/3MFConsortium/spec_materials/blob/master/3MF%20Materials%20Extension.md)

**lib3mf (official SDK)**
- PyPI `lib3mf` 2.5.0 (2026-02-23, BSD): a single `py3-none-manylinux2014_x86_64` wheel (ctypes plus bundled .so), so it is Python-version independent. Publishing repo: 3MFConsortium/lib3mf_python (4★, pushed 2026-02-23). — [PyPI lib3mf](https://pypi.org/project/lib3mf/), [lib3mf_python](https://github.com/3MFConsortium/lib3mf_python)
- Tested here on 3.13:
  - `get_wrapper()`, `CreateModel()`, `AddMeshObject().SetGeometry(...)`, `AddColorGroup().AddColor(wrapper.RGBAToColor(r,g,b,a))`
  - `lib3mf.TriangleProperties` (`ResourceID`, `PropertyIDs[0..2]`) with `SetTriangleProperties` / `SetAllTriangleProperties` / `SetObjectLevelProperty`
  - `GetMetaDataGroup().AddMetaData("", "Application", ...)`, `QueryWriter("3mf").WriteToFile(...)`
  These produced a valid `<m:colorgroup>` file. The model also exposes `AddBaseMaterialGroup`, `AddTexture2DFromAttachment`, `AddTexture2DGroup`, `AddCompositeMaterials`, `AddMultiPropertyGroup` and `AddAttachment`. The only "Custom" methods were `AddCustomContentType` / `RemoveCustomContentType`; there is no API for arbitrary per-triangle attributes such as `paint_color`. (tested here)

**Writers in other languages and reference implementations**
- Vivapercuore/bambu-3mf (TypeScript, MIT, `npm i bambu-3mf three`, 2★, pushed 2026-06-20) generates Bambu-compatible 3MF:
  - per-triangle `paint_color` / `paint_supports` / `paint_seam` / `paint_fuzzy_skin`
  - `encodePaintFacet(state)` with "multi-nibble states and raw escape"
  - `processSettings` → `project_settings.config`
  - per-object settings and plates → `model_settings.config`
  — [bambu-3mf README](https://github.com/Vivapercuore/bambu-3mf)
- rtwfroody/ditherforge (Go) `internal/export3mf/export3mf.go`:
  - Writes `<triangle v1 v2 v3 paint_color="…">` with the same table "from OrcaSlicer/BambuStudio source (Model.cpp CONST_FILAMENTS)" (max 16 filaments).
  - Writes `Metadata/model_settings.config` (`<object id><metadata key="name"/><metadata key="extruder" value="1"/><part id="1" subtype="normal_part">…`).
  - Writes `Metadata/project_settings.config` (JSON with `filament_colour` array, `name: project_settings`) and a thumbnail at `Auxiliaries/.thumbnails/thumbnail_3mf.png`.
  - Code comment: "We intentionally do NOT prefix Application with 'BambuStudio-' / 'OrcaSlicer-': doing so sets m_is_bbl_3mf in Bambu Studio's importer, which then strictly parses project_settings.config and expects plate/slice files we don't emit". An older `Options` comment in the same file still says the BambuStudio- tag "makes Bambu Studio/OrcaSlicer accept the file as a native project", which is internally inconsistent.
  — [ditherforge export3mf.go](https://github.com/rtwfroody/ditherforge/blob/main/internal/export3mf/export3mf.go)
- Omegadarling/painted2printed says Bambu's loader "**ignores** the 3MF core `<basematerials>` block. It only reads … `<m:colorgroup>` … with per-triangle `pid` + `p1=p2=p3`". It keeps `Application` generic because `BambuStudio-*`/`OrcaSlicer-*` "would switch the loader into native project mode and **disable** this color-import path", and notes Bambu Studio 2.5+ shows a "Standard 3mf Import color" dialog. — [painted2printed README](https://github.com/Omegadarling/painted2printed). The basematerials claim **conflicts with current Bambu master**, whose `MaterialColorResources` reads basematerials too ([bbs_3mf.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Format/bbs_3mf.cpp)). It may be true of released 2.5.x builds.
- Decoders and converters useful for validating output:
  - queso/threemf-to-glb (TS, MIT): "Bake a Bambu Lab 3MF (geometry, paint_color …, plate layout) into a glTF binary" — [GitHub](https://github.com/queso/threemf-to-glb)
  - kylertran/bambu-3mf-to-glb (Python, AGPL-3.0) — [GitHub](https://github.com/kylertran/bambu-3mf-to-glb)
  - monomyth/mmu-remapper (Python, MIT, remaps extruders for Prusa/Bambu/Orca) — [GitHub](https://github.com/monomyth/mmu-remapper)
  - UnicornGraveyard/SlicerBridge (GPL-3.0) — [GitHub](https://github.com/UnicornGraveyard/SlicerBridge)
- Ghostkeeper/Blender3mfFormat (GPL-2.0, 373★, last push 2024-06-14): full 3MF Core 1.2.3, tested only up to Blender 3.3. LeeGillie/Blender3mfFormat is a Blender 5 fork (6★, pushed 2026-02-01). — [Blender3mfFormat README](https://github.com/Ghostkeeper/Blender3mfFormat), [Blender 5 fork](https://github.com/LeeGillie/Blender3mfFormat)

### Inferences
- **Recommended output for this project:** write `paint_color` per triangle and keep `Application` non-`BambuStudio-` (e.g. "figurine-colorize-x.y"). Include a minimal `Metadata/model_settings.config` (object/part extruder = 1) and a `Metadata/project_settings.config` with a `filament_colour` list so slot colours show up. This opens painted in both Bambu Studio and OrcaSlicer without any dialog, which is the ditherforge recipe.
  - Add per-triangle `m:colorgroup` `pid/p1` as well only if a dialog-based remap in Bambu Studio 2.5+ or a generic viewer is wanted.
  - Whether Bambu prefers `paint_color` or the colorgroup data when both are present was not checked in code (see Gaps).
- For PrusaSlicer, add `slic3rpe:mmu_segmentation` with the same string and `<metadata name="slic3rpe:MmPaintingVersion">1</metadata>` (dual-write). Whether one file carrying both attribute families is read cleanly by all three slicers was not tested.
- lib3mf is useful for standards-compliant colorgroup and basematerials files and for validation (reading back). Bambu-native painting needs either a post-process of lib3mf's XML (inject attributes) or a plain `zipfile` + string writer, which is simpler and what existing projects do.
- Boundary sharpness in the slicer is limited by triangle size unless you subdivide geometry or emit TriangleSelector split codes. Note Bambu's warning that colour attributes are lost after its own subdivision. Remeshing or adaptive subdivision before labelling is the practical route.

### Gaps
- No official Bambu or Orca public documentation of `paint_color`, `model_settings.config` or `project_settings.config` was found. Everything above comes from source code and third-party reverse-engineering (ditherforge, bambu-3mf, Panda2Prusa).
- I did not trace the Bambu GUI code path that turns `m_volume_color_data` into painting (dialog vs automatic), nor which released version first read `basematerials`.
- Not verified: whether Bambu applies `paint_color` or the standard colours when a non-Bambu file contains both.
- Not verified: the exact PrusaSlicer release (2.9.x vs an unreleased 3.x) containing the JSON-sidecar writer. Released 2.x versions use the inline attribute.
- I did not confirm whether OrcaSlicer has a separate OBJ/3MF colour-import dialog (the code search returned no `ObjColorDialog`, but the index may be incomplete).

## Q4. Existing open-source end-to-end converters (textured GLB/OBJ → multi-colour / MMU-painted 3MF)

### Takeaway
There are now several real projects (most created 2025–2026). The most complete are:
- **ditherforge** (Go, MIT, 56★): textured GLB/OBJ/3MF → Bambu/Orca `paint_color` 3MF. It uses voxel dithering by default and cuts geometry along colour boundaries.
- **paint-to-print-3d** (Python, MIT): AI textured GLB → cleaned regions → colorgroup 3MF, with QA reports and a Tripo-parts route.
- **3mf-webCLI** (browser JS, AGPL per README): Lab k-means + MRF + island cleanup → basematerials/parts 3MF with `model_settings.config`.
- **painted2printed** (Blender add-on, GPL-3.0): k-means Lab → `m:colorgroup` 3MF, optional split into watertight colour parts.
- **figurine-colorize** (Python, MIT): Tripo → graph-cut N colours → colorgroup 3MF.

None is a mature, widely adopted standard (all have <60★ except image-to-flat-relief tools, which are a different problem).

### Cited Findings
(★ and last push from the GitHub search API on 2026-11-17)
- **rtwfroody/ditherforge**: Go, MIT, 56★, pushed 2026-07-30. — [README](https://github.com/rtwfroody/ditherforge), [export3mf.go](https://github.com/rtwfroody/ditherforge/blob/main/internal/export3mf/export3mf.go)
  - Input/output: GLB, 3MF, STL, OBJ, COLLADA → 3MF for OrcaSlicer/BambuStudio. Pre-built Linux/Windows/macOS binaries; `ditherforge-cli` runs the same pipeline from a settings JSON.
  - Pipeline: load + QEM decimation (pristine mesh kept for colour sampling) → stickers → optional split (CGAL `clip`, pegs) → voxelize to a printer-line-width × layer-height grid → colour adjust → RBF warp in CIELAB → palette (TD/translucency-aware, from filament collections) → dither (`dlc-d30-p7` default, `floyd-steinberg`, `riemersma`, `bn-adapt-5`, `none`) → **Clip**, which "cuts the decimated mesh along voxel color boundaries and assigns each fragment a palette color" → coplanar merge → 3MF with per-face assignments, up to 16 colours.
  - Optional repair: winding-number remesh or CGAL alpha-wrap.
  - Building from source needs Go 1.24+, Node 20.19+ and Wails.
  - Limitations: designed for dithered photo-real colour rather than flat regions (`none` mode exists). Layer height must match the slicer. Output is tied to voxel resolution.
- **tntpsu/paint-to-print-3d** (import package `color3dconverter`, CLI `paint-to-print-3d`): Python ≥3.10, MIT, CI, 0★, pushed 2026-09-16. — [README](https://github.com/tntpsu/paint-to-print-3d)
  - Input/output: textured OBJ/MTL, OBJ ZIP, GLB → grouped OBJ/MTL, vertex-colour OBJ, `region_colorgroup.3mf` ("standards-based face-color 3MF export using `colorgroup`"), previews, palette.csv and `conversion_report.json`.
  - Modes: `convert-model --regions 8`, `convert-production` (candidate search against a rendered source preview, "production-ready when drift stays under threshold"), `convert-repaired-transfer` (texture → repaired target mesh), and `convert-repaired-production` (voxel marching-cubes repair + smoothing + paint-region cleanup).
  - A "parts route" (`parts_bundle`) takes a Tripo `generate_parts` model and gives each part a filament slot, thickened into closed shells.
  - Limitations: colorgroup output depends on Bambu's import dialog, and OrcaSlicer ignores per-triangle colorgroup (see Q3). Some modes are tuned to the author's "duck" products.
- **tejaswigowda/3mf-webCLI**: browser JS (three.js), 0★, pushed 2026-10-21. GitHub licence field says NOASSERTION; README says AGPL-3.0 "matching Pythia". — [README](https://github.com/tejaswigowda/3mf-webCLI)
  - Input/output: GLB (texture, vertex colour or material colours) → 3MF "geometry + basematerials + component assembly" with "one `<object>` per material, each with `pid="1"` and unique `pindex`", plus `Metadata/model_settings.config` "Bambu part→extruder (filament slot) mapping". It also writes a segmented GLB.
  - Segmentation: as in Q2 (chroma-weighted Lab k-means, edge-aware smoothing, ICM, island dissolve, auto-K).
  - Limitations: one colour per face sampled at the UV centroid or averaged vertices. Mesh defects are not repaired. Per-material objects are separate shells.
- **Omegadarling/painted2printed** ("Painted 3MF Export"): Blender 4.2+/5.x extension, GPL-3.0, 1★, pushed 2026-08-17, no external dependencies. — [README](https://github.com/Omegadarling/painted2printed)
  - Pipeline: per-face sRGB sample → k-means (Lab) → corner colour attribute → optional repair / scale / voxel remesh + BVH transfer → `m:colorgroup` 3MF with a generic Application tag.
  - "Split Into Parts by Color" writes N co-located watertight (hollow) parts for Orca.
  - Limitations: active object only. Relies on Bambu's 2.5+ import dialog unless split.
- **everything3d/figurine-colorize**: Python, MIT, 6★, pushed 2026-10-25. Claude Code skill. Details in Q5. — [README](https://github.com/everything3d/figurine-colorize)
- **layerweaver/spectrum3mf** (CLI `u1fs`): Python, AGPL-3.0, 15★, pushed 2026-03-28. "Early-stage". — [README](https://github.com/layerweaver/spectrum3mf)
  - Textured assets → Snapmaker U1 / FullSpectrum-oriented 3MF with palette → slot mapping and "virtual mixes"; Streamlit UI.
  - Example: `u1fs convert --input model.glb --out out.3mf --printer u1 --max-colors 12 --layer-height 0.08`. "For best results, use .obj + .mtl".
- **michaelhq/color-mix-lab**: browser, MIT, 5★, pushed 2026-10-10, "Experimental lab project". Texture Baking (GLB/OBJ) → "VertexColor 2 ColorMix" → reduced palette, physical + virtual extruder blends → **PrusaSlicer** 3MF (template-based). — [README](https://github.com/michaelhq/color-mix-lab)
- **williamsexton/tex2multimaterial**: Python (Pillow + numpy only), no licence, 2★, pushed 2026-03-14. OkLab median-cut + k-means on the texture, face-centroid sampling → multi-material OBJ/MTL. Not 3MF. — [README](https://github.com/williamsexton/tex2multimaterial)
- **brettyandell/OBJ2Creality**: 1★, pushed 2026-02-07. Textured OBJ/GLB → vertex-coloured OBJ for Creality Print, mapped to 138+ Creality filament colours. — [README](https://github.com/brettyandell/OBJ2Creality)
- **coreynguyen/prusa_mmu_painter** (3MFTool): C# Windows GUI. Texture quantisation (Uniform / K-Means / Median Cut / Octree), projects to a subdivided mesh, brush painting, exports `slic3rpe:mmu_segmentation`. — [README](https://github.com/coreynguyen/prusa_mmu_painter)
- **robertoSreis/FBX23MF-Converter-in-progress-**: 0★, pushed 2025-10-08, no licence. FBX with texture → Bambu/Anycubic/Orca 3MF. Uses Blender 3.6 + `PyQt6 numpy scikit-learn trimesh Lib3MF`. Minimal README. — [README](https://github.com/robertoSreis/FBX23MF-Converter-in-progress-)
- **a718919334-hub/tripo-3mf-multicolor**: JS demo, 0★, pushed 2026-06-23, README in Chinese. OBJ+texture → palette auto-split (weighted RGB distance) → UV-space hand touch-up → multi-object 3MF with "demo-level" inward-offset shells. Self-described as not production-grade. — [README](https://github.com/a718919334-hub/tripo-3mf-multicolor)
- **ericinawise/flatcolor3mf**: Python, 0★, pushed 2026-06-17. Description "turn glb files to bambu 3mf 5 color files". No README; code search returned no indexed files. — [GitHub search listing](https://github.com/ericinawise/flatcolor3mf)
- **laffranchi/texture-to-3mf-magic**: TypeScript, pushed 2026-02-03. The README is an unedited Lovable template with no technical content. — [README](https://github.com/laffranchi/texture-to-3mf-magic)
- **Pythia (FoxyNinjaStudios/pythia)**: AGPL-3.0 plus Meta SAM licence components. An Apple-Silicon port of SAM 3D Objects; its export includes "3MF Multi-color Export … per-vertex color quantization" (2–256 colours). Needs an M-series Mac with 24 GB, so it is not usable on a Linux CPU box. — [Pythia README](https://raw.githubusercontent.com/FoxyNinjaStudios/pythia/HEAD/README.md)
- Adjacent tools, not texture→mesh:
  - Image → flat multi-colour relief: pgp00/beadrelief (440★), lumina-layer-studio/Lumina-Layers (1223★, AGPL), vycdev/Kromacut (331★, AGPL).
  - Others: suchanek/satprint (terrain → multi-colour 3MF), Gr33k3D/FullSpectrum-Studio (H2C palette compression).
  — [GitHub search results](https://github.com/search?q=multicolor+3mf&type=repositories)
- Commercial or closed alternatives surfaced in web search (not open source):
  - PrintPal AMS converter: textured GLB/OBJ → 3MF for Bambu/Orca. It notes Bambu/Orca "don't read image textures".
  - Meshy's multicolour export.
  - 3D AI Studio's vertex-colour tool.
  - "AMS Splitter" (Blender add-on on Superhive).
  — [PrintPal](https://printpal.io/tools/ams-converter), [Meshy tutorial](https://www.meshy.ai/tutorials/multicolor-3d-printing-with-meshy), [3D AI Studio docs](https://docs.3daistudio.com/utilities/vertex-color), [AMS Splitter](https://superhivemarket.com/products/ams-splitter)

### Inferences
- What these projects do better than a typical hand-rolled pipeline:
  - **ditherforge**: geometry clipping at colour boundaries, so edges are exact and not limited by triangle size; translucency-aware palettes; a proven Bambu/Orca file layout.
  - **3mf-webCLI**: a fully documented regularisation pipeline.
  - **paint-to-print-3d**: automated QA (render-compare drift, island counts) and a repaired-mesh transfer lane.
  - **painted2printed**: watertight per-colour part splitting.
- What they do worse for stylised figurines:
  - ditherforge dithers by default and voxelises.
  - Most others use plain k-means without shading-robust features or crease-aware boundaries.
  - Several write only colorgroup or basematerials, which OrcaSlicer ignores per-triangle and Bambu routes through a manual dialog.
  - Many are 0–15★ with short histories.
- If anything is borrowed, the lowest-risk pieces are the `paint_color` file-layout recipe from ditherforge (MIT) and the island/ICM heuristics from 3mf-webCLI. Avoid copying AGPL code into an MIT or closed pipeline (3mf-webCLI per README, spectrum3mf, Pythia).

### Gaps
- No Reddit or forum thread sharing a reusable textured → MMU-3MF script turned up in web search (results were mostly commercial tools and Fiverr gigs).
- Stars and activity for FoxyNinjaStudios/pythia could not be retrieved (it is not in the search index; per-repo API access is blocked in this session).
- I did not run any of these converters end-to-end. Quality claims are from their READMEs.

## Q5. everything3d/figurine-colorize (comparison only)

### Takeaway
It is public (MIT, 6★, last push 2026-10-25) and is a Claude Code skill. It generates the model with Tripo, then colours it with exactly N filaments using a crease-aware alpha-expansion graph cut (PyMaxflow) on the geometry mesh, plus face-feature painting (eyes, lips, brows). It writes a colorgroup 3MF that it says opens in Bambu Studio and Orca. Its approach is closest to the state of the art among the open projects found. The main portability risks are pinned old numpy/trimesh versions and colorgroup-only output.

### Cited Findings
- README: "turns one image of a figurine into a multi-colour 3D print file". Steps:
  1. Generate a textured model (colour) and a watertight one (print) with Tripo.
  2. "Colours it with exactly N filaments. The colour edges follow the sculpted edges, and shadows don't turn black".
  3. Paints eye whites, irises, catchlights, eyeliner, lips and brows "from the sculpt".
  4. Renders 5 angles.
  "You get a `.3mf` that opens in Bambu Studio or Orca Slicer with the colours already on." Needs a Tripo API key; scripts `gen_textured_for_color.py`, `clean_colorize.py`, `paint_features.py`, `sculpt_features.py`, `render_3mf.py`, `render_pretty.py`, `colorize_3mf.py`. — [README](https://github.com/everything3d/figurine-colorize)
- `clean_colorize.py` takes a textured GLB plus the Tripo `convert_model` 3MF and outputs "colorgroup 3MF, identical mesh and face order". It samples texture via `mesh.visual.to_color().vertex_colors` (per-vertex), then maps to the geometry mesh with a cKDTree. The energy, alpha-expansion, island merge and constraint flags are as described in Q2. Texture colours are cached in `<out>.feats.npz` ("re-runs with new knobs take ~15 s"). — [clean_colorize.py](https://github.com/everything3d/figurine-colorize/blob/main/scripts/clean_colorize.py)
- `colorize_3mf.py::write_3mf` writes a single `<object id="1" pid="2" pindex="0">` with per-triangle `p1="{label}"` and either `<basematerials id="2">` (`<base name="ColorN" displaycolor="#RRGGBBff">`) or `<m:colorgroup id="2">`. It writes only `3D/3dmodel.model`, `[Content_Types].xml` and `_rels/.rels`: no `paint_color`, no `Metadata/model_settings.config` / `project_settings.config`, no `Application` metadata.
  - CLI help: "`--encoding` … colorgroup is what Bambu actually reads (verified); basematerials does NOT show color in Bambu Studio" (default `colorgroup`).
  - "`--obj` … also write OBJ+MTL — best face-color import in Bambu (verified, crispest borders)".
  — [colorize_3mf.py](https://github.com/everything3d/figurine-colorize/blob/main/scripts/colorize_3mf.py)
- Dependencies pinned: requests 2.32.4, numpy 2.3.3, scipy 1.17.1, trimesh 4.12.2, networkx 3.6.1, lxml 6.0.2, Pillow 12.2.0, matplotlib 3.10.7, PyMaxflow 1.3.2, embreex 4.4.0 (ambient occlusion for the shadow fix), moderngl 5.13.0 (renders). — [requirements.txt](https://github.com/everything3d/figurine-colorize/blob/main/requirements.txt)

### Inferences
- Compared with the other projects:
  - Its crease-weighted boundary term and area-weighted data term address exactly the "clean boundaries" requirement that k-means-only tools (painted2printed, tex2multimaterial, OBJ2Creality) lack.
  - It is more principled than 3mf-webCLI's ICM: global alpha-expansion rather than local sweeps.
- It samples texture **per vertex** (`to_color`), not with per-face texel averaging. That is a possible improvement point (see Q1).
- Its writer emits only colorgroup or basematerials: no `paint_color`, no `Metadata/*.config`, no `Application` tag. Per the OrcaSlicer source in Q3, Orca would therefore apply only the object-level `pid="2" pindex="0"` (one colour for the whole object), not the per-triangle colours. The README's claim that it "opens in … Orca Slicer with the colours already on" is very likely wrong for Orca. It holds for Bambu Studio 2.5+ through the standard-3MF colour import. Emitting `paint_color` as well would close this gap.
- Its "basematerials does NOT show color in Bambu Studio" note probably reflects an older Bambu release. Current Bambu master reads basematerials (Q3).

### Gaps
- I did not test the claim about Orca in a running OrcaSlicer. It is inferred from Orca's `bbs_3mf.cpp`.
- No performance numbers beyond "~15 s" for cached re-runs. Tested model sizes are unknown.
