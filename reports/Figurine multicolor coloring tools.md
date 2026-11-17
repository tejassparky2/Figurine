# Paint triangles natively, de-shade upstream, detect faces automatically

Your pipeline is already close to the best open-source approach. Its crease-aware graph cut (PyMaxflow alpha-expansion over Lab-snapped colours) is more principled than any other open converter found. The three upgrades that pay off most are therefore not new colouring algorithms:

- **Output format.** Make Bambu/Orca `paint_color` per-triangle 3MF the main output again, plus a PrusaSlicer `slic3rpe:mmu_segmentation` variant. The colorgroup 3MF that figurine-colorize writes goes through Bambu Studio's re-clustering import dialog. Going by OrcaSlicer's source code it is very probably flattened to one colour there.
- **Shading.** Remove baked shading *before* colour transfer. Request Tripo's `v3.5-20260815` texture model with `delight=true`, down-weight Lab L*, and divide out mesh AO computed with embreex.
- **Faces.** Replace the hand-written ellipse specs with specs generated automatically. MediaPipe Face Landmarker (Apache-2.0) and a BiSeNet face-parsing ONNX model both install as wheels on Python 3.13 CPU. In a local test they found 3/3 faces on this project's Tripo renders, glasses included. Their detections are ray-cast onto mesh triangles with Blender's `BVHTree`.

The landscape has changed since mid-2026. Bambu Studio 2.7.1 and OrcaSlicer 2.5 now turn textures into colour painting themselves (up to 32 colours), so plain k-means quantisation is no longer worth maintaining. A custom pipeline earns its keep through what slicers still cannot do: semantic and part-aware boundaries, shadow rejection, exact palettes, and facial features. Two licence problems matter commercially. Most of the strongest research models are non-commercial: PartField, Careaga's intrinsic decomposition, RGB↔X, dlib's 68-point model, InsightFace models, Sapiens and the CelebAMask-HQ-derived face parsers. And Tripo's default segmentation model, which a per-segment block-colour step depends on, stops working on **1 December 2026**. Reddit could not be reached during the research, so "practitioner" evidence below comes from the Bambu forum, GitHub and blogs.

How to read this report:

- A claim followed by a citation was checked against that source.
- "Local test" means the research team measured it in this Linux, Python 3.13, CPU-only container on 2026-11-17.
- Sentences marked **Inference** are engineering judgement, not sourced fact.

## Bambu and Orca now quantise textures themselves, but blindly

The biggest change of 2026 is on the slicer side. **Bambu Studio 2.7.1** added *Texture to Color Painting* ([Bambu wiki](https://wiki.bambulab.com/en/software/bambu-studio/texture-to-color)):

- It accepts OBJ, glTF, GLB and FBX with a texture map.
- It clusters the texture to **1–32 colours**, with an Auto button, **Boundary Smoothness 0–10** and **Gap Area 0–5 %**, which merges small regions into neighbours.
- It maps the clusters to loaded filaments, or decomposes them into CMYKW colour mixes.
- **Draco-compressed GLB is not supported.**
- The release note adds that painting now survives a Plane Cut ([2.7.1 release note](https://wiki.bambulab.com/en/software/bambu-studio/release/release-note-2-7-1)). That makes splitting a figurine into parts with fewer colours each much easier.

**OrcaSlicer 2.5.0** (beta released 27 October) adds a unified "Import Model" dialog for textures, vertex colours and OBJ material colours, with a Color Count, smoothing and auto-mix. It also adds "top and bottom paint penetration layers" ([Orca 2.5.0 alpha notes](https://www.orcaslicer.com/wiki/releases/release_2_5_0_alpha); [v2.5.0-beta release](https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.5.0-beta)). Bambu's clustering is plain k-means: `QuantKMeans` in `ObjColorUtils.cpp`, shared by the OBJ and standard-3MF importers ([BambuStudio source](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/ObjColorUtils.cpp)).

**PrusaSlicer still imports no colour at all** from OBJ vertex/MTL colours, textures or 3MF basematerials. Issue #12040 has been open since January 2024 and #4503 since 2020 ([#12040](https://github.com/prusa3d/PrusaSlicer/issues/12040); [#4503](https://github.com/prusa3d/PrusaSlicer/issues/4503)). The community workaround is to save from Bambu Studio and open the 3MF in PrusaSlicer 2.9.6, which reads Bambu `paint_color`. That route **regressed in PrusaSlicer 3.0.0-alpha14** ([#16268](https://github.com/prusa3d/PrusaSlicer/issues/16268)). PrusaSlicer painting is capped at **16 extruders**, and the slicer silently merges thin painted regions into a neighbour, changing their colour ([Prusa KB](https://help.prusa3d.com/article/multi-material-painting_262620)).

The forum evidence explains why these slicer features do not make your pipeline redundant:

- An independent Tripo H3.1 review found that Tripo's default texture "carries baked shadows". With Remove Lighting off, Bambu Studio found only three clusters and grey rocks came out cream. Bambu's Color Count of 4 merged orange and white into peach ([3DPrinting.com review](https://3dprinting.com/reviews/tripo-h3-1-review-from-image-to-3d-print/)).
- On Bambu Studio 2.8.2, users complain that the import dialog forces smoothing, matches filament types they have not loaded, mixes colours unasked, and cannot be reopened after import ([forum: "Importing is a mess"](https://forum.bambulab.com/t/importing-is-a-mess/258389); [forum: map colours only on import](https://forum.bambulab.com/t/why-does-studio-only-let-us-map-colors-on-import/258461)).
- One user puts the AI failure plainly: AI "thinks depth is darker colors… a hole in a flat surface… ai sees it like a flat wall with a black stain" ([forum](https://forum.bambulab.com/t/image-to-3d-model-is-really-hit-or-miss/220515)).

Shadow-as-colour, merged near-colours, global-only knobs and no notion of eyes or lips are exactly the problems your graph cut, palette snapping and face pass target.

**Inference:** use Bambu 2.7.1+ Texture-to-Color, and the free browser-only **PrintPal AMS converter**, as *benchmarks*, not as pipeline stages. PrintPal is closed-source, 2–8 colours, and its palette is LAB-based "so small parts, like eyes or buttons, keep their own color", with specks under 1 mm² absorbed ([PrintPal](https://printpal.io/tools/ams-converter)). If your output does not beat them on a given figurine, that figurine does not need the custom path.

Other projects reported in the community fill niches:

- **FullSpectrum Studio** reduces already-painted Bambu 3MFs to fewer real filaments plus mix recipes, but it is PolyForm Noncommercial ([forum thread](https://forum.bambulab.com/t/fullspectrum-studio-automatic-palette-reduction-for-hundreds-of-colors/253789); [licence snippet](https://gh.r-mj.com/Gr33k3D/FullSpectrum-Studio)).
- **HueForge** makes 2D relief plates, not figurines ([Snapmaker blog](https://www.snapmaker.com/blog/hueforge-3d-printing/)).
- For the older OBJ route, forum regulars recommend Blender's OBJ export with "Color" and "Triangulate Mesh" enabled ([forum](https://forum.bambulab.com/t/importing-blender-multi-color-3mf-file-into-bambu-studio-is-problematic/242163)).

Practical print constraints also shape colouring decisions:

- **Prime tower.** Keep it on for figurines. There is almost no infill to flush into, and tiny face segments under-extrude at colour changes ([forum](https://forum.bambulab.com/t/problems-with-colored-miniatures/160232)).
- **Colour-change height.** The tower must reach the highest layer with a colour change. Rotating a part so colour changes sit low cut tower mass by about 40 % in Bambu's example ([Bambu wiki](https://wiki.bambulab.com/en/software/bambu-studio/reduce-wasting-during-filament-change)).
- **Placement (inference).** A single rare colour near the top of the figurine, such as a bindi or hair clip, is expensive.

## Your 3MF writer is the weakest link: paint_color beats colorgroup

Reading the slicer source code settles which format to write. **Bambu Studio and OrcaSlicer both read a per-triangle `paint_color` attribute**, an uppercase hex string per `<triangle>` ([bbs_3mf.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Format/bbs_3mf.cpp); [OrcaSlicer bbs_3mf.cpp](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/Format/bbs_3mf.cpp)):

- For unsplit triangles, filament 1 = `"4"`, 2 = `"8"`, 3 = `"0C"`, 4 = `"1C"`, … 16 = `"DC"`, up to 32 = `"EFC"`. This is `CONST_FILAMENTS` in Model.cpp.
- `set_triangle_from_string` **drops any triangle whose string is not uppercase hex** ([Model.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Model.cpp)).
- The underlying TriangleSelector encoding also supports sub-triangle splits. That allows finer boundaries without remeshing ([TriangleSelector.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/TriangleSelector.cpp)).

The **`Application` metadata must not start with `BambuStudio-`**. Otherwise Bambu treats the file as a native project and strictly expects plate and slice files you do not write. ditherforge's MIT Go writer documents this, along with a minimal `Metadata/model_settings.config` and a `Metadata/project_settings.config` carrying a `filament_colour` array ([ditherforge export3mf.go](https://github.com/rtwfroody/ditherforge/blob/main/internal/export3mf/export3mf.go)). ditherforge's own comments are inconsistent on this point, so test both variants.

**Colorgroup output is worse on both slicers.** In Bambu Studio 2.5+, a non-native 3MF with `m:colorgroup` (and, in current master, `basematerials`) opens the "Standard 3MF Color Parsing" dialog. It **re-clusters to at most 32 colours** and maps them to filaments ([Bambu wiki](https://wiki.bambulab.com/en/bambu-studio/Standard-3MF-File-Color-Parsing)). Users cannot disable it; it is tracked as #9666, and it "pukes 10+ filaments into my workspace" even on cancel, with "Reload from disk" as the workaround ([forum](https://forum.bambulab.com/t/how-to-disable-standard-3mf-import-color/241644)).

In OrcaSlicer's importer, colorgroup colours map to extruders only through the **object-level** `pid` ([Orca source](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/Format/bbs_3mf.cpp)). The painted2printed author says the same independently: OrcaSlicer "ignores per-triangle 3MF colors" ([painted2printed README](https://github.com/Omegadarling/painted2printed)).

figurine-colorize's `write_3mf` emits only `<object pid="2" pindex="0">` with per-triangle `p1`. It writes no `paint_color`, no `Metadata/*.config` and no `Application` tag ([colorize_3mf.py](https://github.com/everything3d/figurine-colorize/blob/main/scripts/colorize_3mf.py)). **Inference (untested in a running Orca):** its README claim that the file "opens in … Orca Slicer with the colours already on" is very likely wrong for Orca, because the whole object would take one colour.

Its CLI note that "basematerials does NOT show color in Bambu Studio" also conflicts with Bambu master, which now folds basematerials into the colour-group map ([bbs_3mf.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/Format/bbs_3mf.cpp)). It is probably true of older releases.

The OBJ+MTL output that figurine-colorize calls "crispest borders" in Bambu is still useful. It passes through the same import dialog, though, so set smoothing to 0 and match manually.

For **PrusaSlicer**, write the same TriangleSelector string as `slic3rpe:mmu_segmentation` together with `<metadata name="slic3rpe:MmPaintingVersion">1</metadata>`. PrusaSlicer master now also writes a JSON sidecar but still dual-writes and reads the attribute ([LegacyPaintingCompat.hpp](https://github.com/prusa3d/PrusaSlicer/blob/master/src/slic3r-shared/include/Slic3r/Biz/Format/3mf/LegacyPaintingCompat.hpp); [Model3mf.cpp](https://github.com/prusa3d/PrusaSlicer/blob/master/src/slic3r-shared/src/Slic3r/Biz/Format/3mf/Model3mf.cpp)). Alternatively, run the MIT tool **Panda2Prusa**, which transcodes `paint_color` to `mmu_segmentation` ([Panda2Prusa](https://github.com/CupsOhJoe/Panda2Prusa)).

**lib3mf** 2.5.0 (BSD) has a single wheel that works on 3.13. It writes valid colorgroup and basematerials files, but it has **no API for `paint_color`** (local test; [PyPI](https://pypi.org/project/lib3mf/)). Use it for reading back and validating output, and write the Bambu XML with `zipfile` plus string templates, as ditherforge does.

**Inference:** emit separate files per slicer rather than one file carrying both attribute families. Nobody has checked which one Bambu prefers when both are present.

## Shadows are cheapest to kill before they reach the mesh

Baked lighting is the root cause of "creases turn black" and "highlights turn white". The research points to a layered defence, ordered by cost.

**Layer 1 is free: fix the generator call.** Tripo's `/v3/models/texture` has `delight` (default true), "Removes baked-in lighting from the reference image before texturing". But "only the v3.5-20260815 texture model reads this", while **the default texture model is still `v3.0-20250812`**, which ignores it ([Tripo texture API](https://developers.tripo3d.com/en/docs/models-texture.md)). The same endpoint offers:

- `bake`, which bakes material effects into base colour;
- `texture_alignment`;
- `part_names`, which re-textures only the parts named from an earlier segmentation.

Meshy's `remove_lighting` applies only with `meshy-6` at 2k/4k; `meshy-7` de-lights automatically ([Meshy retexture API](https://docs.meshy.ai/api/retexture.md)). The Tripo review measured the difference: Remove Lighting on gave flat saturated colours and all four target colours; off gave three muddy clusters ([3DPrinting.com](https://3dprinting.com/reviews/tripo-h3-1-review-from-image-to-3d-print/)). **Inference:** because your reference renders are generated in-house, also prompt the image model for flat, even, shadowless "matte toy" lighting. This is untested.

**Layer 2 is cheap mesh-side de-shading.** The open converter 3mf-webCLI scales L* by **0.35** before k-means "so baked shading does not create bands" ([3mf-webCLI README](https://github.com/tejaswigowda/3mf-webCLI)). Its code is AGPL per the README, but the idea is free to reuse. Dividing a mesh AO term out of the colour is long-standing photogrammetry practice: Unity's De-Lighting Tool takes AO and bent normals as inputs, Substance has an AO Cancellation node, and artists warn that full-strength division is "too destructive" ([CG Channel](https://www.cgchannel.com/2017/07/download-unity-labs-free-texture-de-lighting-tool/); [dmg3d blog](https://dmg3d.blogspot.com/2015/09/removing-ambient-occlusion-from-photo.html)).

**Inference:** compute per-vertex AO with trimesh plus **embreex**, which figurine-colorize already pins for its shadow fix ([requirements.txt](https://github.com/everything3d/figurine-colorize/blob/main/requirements.txt)). Apply `albedo ≈ colour / (1 − s·(1 − AO))` in linear RGB, with `s` between 0.5 and 0.9 and AO floored at about 0.2, then palette-snap. Snapping only needs crease colours to move closer to the right palette entry than to black.

Blender 4.5's Cycles bake with only the "Color" contribution gives "the pass color… independent of sampling refinement" ([Blender manual](https://docs.blender.org/manual/en/4.5/render/cycles/baking.html)). **Inference:** that removes *scene* lighting when transferring a texture to a colour attribute. It does not remove shading painted *into* the AI texture.

**Layer 3 is better sampling.** Your per-vertex KDTree transfer mirrors figurine-colorize, which samples `mesh.visual.to_color().vertex_colors` per vertex ([clean_colorize.py](https://github.com/everything3d/figurine-colorize/blob/main/scripts/clean_colorize.py)). trimesh's `uv_to_color` is a nearest-pixel lookup with no area averaging. `trimesh.sample.sample_surface(mesh, count, sample_color=True)` returns a **`face_index`** for every sample ([trimesh color.py](https://github.com/mikedh/trimesh/blob/main/trimesh/visual/color.py); [sample.py](https://github.com/mikedh/trimesh/blob/main/trimesh/sample.py)).

**Inference:** sample about 20–50 points per face, convert to Lab, and take the **per-face median**. That rejects seam and shadow outliers and stops colour smearing across UV seams, which per-vertex sampling causes. PyMeshLab's `transfer_texture_to_color_per_vertex` handles the textured-mesh-to-watertight-mesh case in one call, but it samples per vertex and is GPL-3.0 ([PyMeshLab filters](https://pymeshlab.readthedocs.io/en/latest/filter_list.html)).

One trap: figurine-colorize pins `trimesh==4.12.2` and `numpy==2.3.3` because "Newer numpy (2.5) / trimesh (5.x) break the face pass". This container has numpy 2.5.x and trimesh 5.2.1 (local check). Run the skill in its own pinned virtual environment.

**Layer 4 is learned de-lighting, and it is mostly licence-blocked.**

| Model | What it removes | Licence for commercial use | CPU feasibility |
|---|---|---|---|
| Marigold-IID lighting v1-1 | Albedo, diffuse shading and residual | **Apache-2.0 code, OpenRAIL++-M weights: usable** ([model card](https://huggingface.co/prs-eth/marigold-iid-lighting-v1-1); [LICENSE](https://raw.githubusercontent.com/prs-eth/Marigold/main/LICENSE.txt)) | SD2-based, 1–50 steps; no CPU timing published |
| StableDelight | Specular highlights only, not crease shadows | Apache-2.0 per README badge ([README](https://raw.githubusercontent.com/Stable-X/StableDelight/main/README.md)) | Unbenchmarked |
| Careaga & Aksoy "Intrinsic" | Albedo, shading and residual | **Academic use only, patent pending** ([repo](https://github.com/compphoto/Intrinsic)) | `device='cpu'` possible |
| RGB↔X (Adobe) | Albedo and other intrinsic channels | **Non-commercial research only** ([LICENSE](https://raw.githubusercontent.com/zheng95z/rgbx/main/LICENSE)) | NVIDIA GPU only |
| IntrinsicAnything | Object albedo and specular | Free, but a company must register first ([LICENSE](https://raw.githubusercontent.com/zju3dv/IntrinsicAnything/master/LICENSE)) | Diffusion; likely slow |
| Hunyuan3D-2 Delight | Shadows and highlights on the reference image | Community licence **excludes the EU, UK and South Korea**; file headers say non-commercial ([LICENSE](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/LICENSE)) | fp16 is hard-coded; 50 steps at 512² |

**Inference:** apply learned de-lighting to the single 2D reference render, not to the texture. Use the output to choose palette colours and as unary votes. On CPU, Marigold is the only clean choice, and it needs benchmarking first.

The open-source re-texturers all need 24–48 GB NVIDIA GPUs: MaterialAnything, Paint-it, TEXGen, SyncMVD and TRELLIS.2 ([TRELLIS.2 README](https://github.com/microsoft/TRELLIS.2); [TEXGen](https://github.com/CVMI-Lab/TEXGen)). They are not options here.

## Graph cuts already lead; segmentation models mostly add licence risk

Among open converters, the recipes converge on the same stages: Lab features with L down-weighted, then k-means++, then face-adjacency smoothing, then an MRF, then merging small islands ([3mf-webCLI](https://github.com/tejaswigowda/3mf-webCLI); [paint-to-print-3d](https://github.com/tntpsu/paint-to-print-3d); [painted2printed](https://github.com/Omegadarling/painted2printed)).

figurine-colorize goes further. Its energy is `Σ area·|colour − palette| + λ Σ length·crease·[label differs]`. It is solved by global alpha-expansion, and crease weight falls toward zero at concave creases, so boundaries snap to sculpted edges ([clean_colorize.py](https://github.com/everything3d/figurine-colorize/blob/main/scripts/clean_colorize.py)). CGAL's reference segmenter uses the same idea, weighting convex edges 0.08 against concave edges 1 ([CGAL docs](https://doc.cgal.org/latest/Surface_mesh_segmentation/index.html)). **This is the state of the art among open tools. Keep it.**

There are two worthwhile additions.

First, **gco-wrapper** (`gco.cut_general_graph`) gives true multi-label alpha-expansion on an arbitrary graph in a single call. It has no cp313 wheel but builds from sdist with a compiler. Local test: on a 1.31M-face mesh with 10 labels it converged in **11.1 s** at 0.987 accuracy against ground truth. Integer cost arrays gave all-zero labels, and float costs worked ([PyPI gco-wrapper](https://pypi.org/project/gco-wrapper/)). PyMaxflow's own `fastmin` helpers work on grids only, so a mesh needs your own expansion loop, which is what you already have. pygco fails to build on 3.13 (local test).

Second, **inference:** add a texture-gradient term to the pairwise weight, so boundaries also snap to *painted* edges on smooth surfaces where no crease exists. No published method combines dihedral and colour-gradient terms for AI meshes.

Learned 3D part segmenters look tempting but fit poorly on three counts. They need a GPU, their licences are restrictive, and **geometry-only models cannot see painted-on eyes, brows or lips**.

| Segmenter | Quality on PartObjaverse-Tiny | Licence | Hardware |
|---|---|---|---|
| PartField | **79.18 mIoU, about 10 s per shape** | **NVIDIA non-commercial** | CUDA |
| SAMesh | 56.86 mIoU, about 7 min per shape | **No licence file** ("all rights reserved") | CUDA |
| SAMPart3D | 53.47 mIoU | MIT | CUDA |
| P3-SAM (Hunyuan3D-Part) | Images only for AI meshes | **Excludes EU/UK/South Korea** | CUDA; ZeroGPU Space |
| GeoSAM2 | State-of-the-art claims, numbers seen only in a search summary | Apache-2.0 | "CPU is supported but slow"; prompt-only, someone clicks each part |

Sources for the table: [PartField paper Table 1](https://arxiv.org/html/2504.11451v1); [SAMesh issue #22](https://github.com/gtangg12/samesh/issues/22); [Hunyuan3D-Part](https://github.com/Tencent-Hunyuan/Hunyuan3D-Part); [GeoSAM2 card](https://huggingface.co/VAST-AI/GeoSAM2/blob/main/README.md).

On the classical side, CGAL's SDF segmenter has no Python 3.13 wheel (local test). libigl's Python module does not expose `shape_diameter_function` (local test). PyMeshLab offers useful crease-selection and connected-component building blocks, but no segmentation filter ([PyMeshLab filters](https://pymeshlab.readthedocs.io/en/latest/filter_list.html)).

**The commercial API you already pay for is the pragmatic segmenter, with a deadline.** Tripo `/v3/mesh/segment` accepts *uploaded* models up to 150 MB. Its default model, `v1.0-20250506`, is geometric and **"stops working on December 1, 2026"**. The replacement, `v2.0-20260430` (beta), does "semantic labeling" with `simple`, `balanced` or `detailed` granularity and an optional `ref_image`. The example response shows 40 credits per call ([Tripo segment docs](https://developers.tripo3d.com/en/docs/mesh-segment.md)). **Inference:** if your figurine-blockcolor step calls segment without pinning `model`, it will break or change behaviour within two weeks. Test v2 `detailed` with the approved render as `ref_image` now.

Meshy's Auto Split `by_color` mode cuts along named colour regions, which is the closest commercial match to "one filament per region". It rejects uploaded models and works only on Meshy-6/7 generations ([Meshy Auto Split](https://docs.meshy.ai/api/auto-split.md)).

The best use of any segmenter here is as unary votes feeding your existing graph cut, not as final labels.

## Faces can be detected automatically with two wheel-installable models

No open-source tool automatically detects and paints facial features on figurine meshes for multi-colour FDM. The research found adjacent tools only, such as Faceit for rigging and texture-to-3MF converters. This project's own `photo_project_colorize.py` plus hand-written `eyes.spec` ellipses is the closest thing to it (local repo, 2026-11-17).

The building blocks do exist and run on this box:

- **MediaPipe Face Landmarker** 1.2.3: Apache-2.0, a manylinux wheel for Python 3.9–3.14, **478 landmarks including iris centres** ([docs](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker); [PyPI](https://pypi.org/pypi/mediapipe/json)). It installed in a 3.13 venv but first failed with `OSError: libGLESv2.so.2`. `apt-get install libgles2` fixed it (local test).
- **BiSeNet ResNet18 face parsing** as ONNX, from yakhyo/face-parsing (MIT code), run with onnxruntime 1.32's cp313 wheel ([yakhyo/face-parsing](https://github.com/yakhyo/face-parsing); [onnxruntime PyPI](https://pypi.org/pypi/onnxruntime/json)).

Local test results on this project's family-of-3 models:

- MediaPipe found **3/3 faces** on the approved render and on the Tripo textured front render. Iris centres (indices 468 and 473) sat on the pupils **even behind thick glasses frames**.
- On an untextured clay render it found only 1/3 faces in the whole image, but **3/3 once each head was cropped** to about 360–560 px.
- BiSeNet segmented glasses, brows, nose, lips, ears and hair correctly. It has three blind spots: it labelled the whole lens area including the eyes as `eye_g`, **the beard as skin**, and **the bindi as skin**. CelebAMask-HQ has no beard class.

Installs that were weighed and rejected: dlib is sdist-only, and its 68-point model "can't be used in a commercial product" ([dlib-models](https://github.com/davisking/dlib-models)). InsightFace's pretrained models are non-commercial ([insightface](https://github.com/deepinsight/insightface)). The cartoon-specific MDFLD v3 is "research use only" and supports Python 3.10–3.12 only ([MDFLD](https://github.com/zenonLEE/MDFLD)). FLAME and 3DMM fitting cannot represent exaggerated cartoon heads ([arXiv 2004.09190](https://arxiv.org/pdf/2004.09190)).

**Inference: proposed wiring.** It keeps your painter as the only writer of 3MF triangles.

1. Render each head orthographically, facing the head, at about 20–40 px/mm. Use the textured render first and fall back to clay.
2. Run MediaPipe for eye contours, iris centre and radius, brow lines, lip contour and forehead point, and BiSeNet for the glasses, brow and lip masks.
3. Cast one ray per landmark or mask pixel with Blender 4.5's `BVHTree.ray_cast`, which returns `(position, normal, index, distance)` (local check of the installed 4.5.16). Open3D's `RaycastingScene` works too: it returns `primitive_ids` in bulk and has a cp313 wheel ([Open3D tutorial](https://www.open3d.org/docs/release/tutorial/geometry/ray_casting.html)).
4. **Emit an `eyes.spec` automatically**:
   - eye polygon → skin-reset ellipse;
   - iris → pupil ellipse;
   - brow landmarks → stroke polyline;
   - lip contour → lip polygon;
   - forehead point plus a red-texture test or a 1–2 mm convex-bump test → bindi;
   - BiSeNet `eye_g` → frame mask. Rays continue past a frame hit to reach the eye behind it.
5. Snap ellipses to the sculpted lid crease, a concave curvature loop. This should cure the few-pixel speckle seen with photo labels.

**Feature size decides which features to paint at all.** On this project's 120 mm three-person bust, eye openings measure about 4.2–5.7 × 1.4–1.9 mm, and the shipped Rev 5 style uses solid black pupil ovals of about 2.2–2.5 × 1.5–1.7 mm, with no whites and no catchlights (local files `family_d_eye_sockets.json`, `eyes_v5.spec`). Published guidance agrees:

- Avoid AMS detail "under 5mm" ([Geeky Inc guide](https://www.geekyinc.com/multi-color-3d-printing-anime-figures-the-ams-guide-for-p1s-x1c-2026/)).
- Miniature makers use a 0.2 mm nozzle and 0.05–0.08 mm layers for faces ([Bambu forum](https://forum.bambulab.com/t/how-to-print-small-fine-things/10417)).
- Painters use a dot-only eye at 15 mm scale and below, and full iris plus pupil only at 54 mm and up ([Brush Slinger guide](https://prime-paint.pages.dev/blog/how-to-paint-eyes)).
- Funko convention is large solid black round eyes, often with no mouth or brows ([Wikipedia](https://en.wikipedia.org/wiki/Funko)).

**Inference (no published spec exists):** keep every colour island **at least 0.8–1.0 mm in its narrowest direction on a 0.4 mm nozzle**, or 0.4–0.5 mm on a 0.2 mm nozzle. In practice:

- brows ≥0.8 mm;
- a bindi as a ≥1.5 mm red dot, or left as a skin-coloured bump if no slot is free;
- beards in the hair colour;
- glasses in the black or hair slot.

A test coupon of dots and lines from 0.4 to 2.0 mm on a vertical wall is the only reliable answer.

## Ranked install list and where each tool plugs in

Ranked by impact per hour of work on the Python 3.13 CPU container. "Verified" means install or behaviour was confirmed in a source or local test.

| Rank | Tool / change | Install | Plugs into | Status |
|---|---|---|---|---|
| 1 | **`paint_color` writer** (revive your older Bambu writer; follow ditherforge's layout: uppercase `CONST_FILAMENTS`, non-`BambuStudio-` Application, `model_settings.config`, `project_settings.config` with `filament_colour`) | None (zipfile) | Replaces colorgroup 3MF as the main output; keep colorgroup and OBJ/MTL as secondary | Format verified from source; slicer opening untested here |
| 2 | **PrusaSlicer variant** (`slic3rpe:mmu_segmentation` + `MmPaintingVersion=1`), or Panda2Prusa (MIT) | None / git clone | Same writer, second file | Verified from source; not tested in PrusaSlicer |
| 3 | **Tripo texture `model="v3.5-20260815"`, `delight=true`**; flat-lighting prompt for reference renders | API parameter | Before KDTree transfer | Verified docs; one independent review |
| 4 | **Tripo segment `v2.0-20260430`** (pin `model`; try `detailed` + `ref_image`) | API parameter | figurine-blockcolor, and as graph-cut unaries | Verified docs; quality on faces untested |
| 5 | **Per-face Lab-median sampling** via `trimesh.sample.sample_surface(sample_color=True)`; isolated venv with figurine-colorize's pins | Already installed | Replaces per-vertex `to_color` + KDTree | API verified; benefit inferred |
| 6 | **AO de-shading + L\* down-weight** (embreex AO, partial division in linear RGB, L×~0.35 in the data term) | `pip install embreex` (cp313) | Between colour transfer and Lab snapping | Technique sourced; parameters inferred |
| 7 | **mediapipe + libgles2 + onnxruntime + BiSeNet-R18 ONNX → auto `eyes.spec`** | `pip install mediapipe onnxruntime`; `apt-get install libgles2` | Generates input for the existing face-paint pass | Install and detection verified locally |
| 8 | **lib3mf** (BSD) for reading output back | `pip install lib3mf` | Validation after writing | Verified locally |
| 9 | **gco-wrapper** (optional faster multi-label cut; use float costs) | `pip install gco-wrapper` (compiles) | Drop-in alternative to the PyMaxflow expansion loop | Verified locally; GCO C++ licence unverified |
| 10 | scikit-image / colour-science for ΔE2000 | pip (cp313) | Lab palette snapping | Verified locally |
| 11 | Bambu Studio ≥2.7.1, OrcaSlicer 2.5, PrintPal | Desktop / browser | Benchmark against your output | Verified docs |
| 12 | opencv-contrib-python-headless (`ximgproc.l0Smooth`) for flattening the 2D reference; Marigold-IID via diffusers + CPU torch | pip (cp313 available) | Reference-image palette and unary votes | Installable; CPU speed unbenchmarked |
| 13 | PyMeshLab (crease selection, texture→vertex transfer), Open3D RaycastingScene | pip (cp313 wheels) | Optional helpers | Wheels verified; not run |

Skip for this business: PartField, SAMesh, P3-SAM, SAM 3 (needs a GPU), Careaga Intrinsic, RGB↔X, Hunyuan delight, dlib, InsightFace, MDFLD, FLAME, CGAL Python, pygco, HueForge and FullSpectrum Studio.

Open-source converters worth *reading* rather than installing:

- **ditherforge** (MIT, 56★): writer layout, and clipping geometry at colour boundaries ([repo](https://github.com/rtwfroody/ditherforge)).
- **paint-to-print-3d** (MIT): automated QA drift and island-count reports ([repo](https://github.com/tntpsu/paint-to-print-3d)).
- **painted2printed** (GPL-3.0 Blender add-on): watertight per-colour part splitting ([repo](https://github.com/Omegadarling/painted2printed)).
- The Clonephaze **3MF Import/Export** Blender extension, which claims Bambu, Orca and Prusa paint-zone preservation and baking textures to filament colours. Its licence was not checked ([Blender Extensions](https://extensions.blender.org/add-ons/threemf-io/)).

## Licence flags for a commercial figurine business

GPL-3.0 tools, which include PyMaxflow, PyMeshLab, `bpy` and Blender, are unproblematic for **internal** production use. **Inference:** their copyleft obligations attach to distribution, so they matter only if you ship the pipeline as software. AGPL projects (3mf-webCLI per its README, spectrum3mf, kylertran/bambu-3mf-to-glb, Pythia) should not be copied into your codebase, though their documented algorithms can inform your own.

The real blockers are **model weights and datasets**:

| Item | Restriction | Source |
|---|---|---|
| PartField | NVIDIA non-commercial | [repo](https://github.com/nv-tlabs/PartField) |
| SAMesh | No licence granted | [issue #22](https://github.com/gtangg12/samesh/issues/22) |
| Hunyuan3D-2 / 2.1 / Part | Not licensed in EU/UK/South Korea; >1M MAU clause | [LICENSE](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/LICENSE) |
| Careaga Intrinsic | Academic only, patent pending | [repo](https://github.com/compphoto/Intrinsic) |
| RGB↔X | Non-commercial research | [LICENSE](https://raw.githubusercontent.com/zheng95z/rgbx/main/LICENSE) |
| IntrinsicAnything | Company registration required | [LICENSE](https://raw.githubusercontent.com/zju3dv/IntrinsicAnything/master/LICENSE) |
| BiSeNet weights (CelebAMask-HQ) | Dataset widely described as non-commercial; jonathandinu SegFormer card says so explicitly | [model card](https://huggingface.co/jonathandinu/face-parsing) |
| Sapiens-seg | CC-BY-NC-4.0 | [model card](https://huggingface.co/facebook/sapiens-seg-1b) |
| dlib 68-point model | No commercial use | [dlib-models](https://github.com/davisking/dlib-models) |
| InsightFace models | Non-commercial research | [insightface](https://github.com/deepinsight/insightface) |
| MDFLD | Research use only | [MDFLD](https://github.com/zenonLEE/MDFLD) |
| FullSpectrum Studio | PolyForm Noncommercial | [snippet](https://gh.r-mj.com/Gr33k3D/FullSpectrum-Studio) |
| GCO v3 C++ (inside gco-wrapper) | Wrapper is MIT; bundled library historically research-only, unverified | [PyPI](https://pypi.org/project/gco-wrapper/) |

These look clean on the evidence gathered: MediaPipe (Apache-2.0), Marigold-IID (Apache-2.0 code, OpenRAIL++-M weights), StableDelight (Apache-2.0 badge only), GeoSAM2 (Apache-2.0), SAMPart3D (MIT), lib3mf (BSD), trimesh, Open3D and onnxruntime (MIT), ditherforge, paint-to-print-3d and Panda2Prusa (MIT).

**The BiSeNet weight licence is the one that touches the recommended stack.** Before production, either clear CelebAMask-HQ's terms or rely on MediaPipe landmarks alone, which give eyes, irises, brows and lips without a parser.

## What could not be verified

Several gaps remain:

- **Community and user evidence.** Reddit (r/BambuLab, r/3Dprinting, r/OrcaSlicer, r/prusa3d) returned 403 and no indexed threads, so no Reddit recommendation is cited. MakerWorld, Printables and the Bambu paint-tool wiki page were readable only as search snippets. No user reports were found that evaluate Bambu's Texture-to-Color on Tripo, Meshy, Hunyuan or TRELLIS figurines specifically.
- **Slicer behaviour in running slicers.** Nobody opened a file in a running slicer during this research. That covers three open questions: whether OrcaSlicer really flattens figurine-colorize's colorgroup 3MF to one colour, whether Bambu prefers `paint_color` or colorgroup when both are present, and which released Bambu version first read `basematerials`.
- **Undocumented algorithms.** Bambu's Texture-to-Color clustering details are undocumented, beyond `QuantKMeans` in the OBJ and 3MF code path.
- **Release facts.** Exact release dates for Bambu Studio 2.5–2.7.1 are unconfirmed; "May 2026" for 2.7.1 comes from a third-party snippet. Whether OrcaSlicer 2.5.0 is stable yet is also unconfirmed.
- **Performance and quality numbers.** No CPU runtimes exist for any intrinsic-decomposition or learned segmentation model. No evaluation of any of them on Pixar-style figurines was found. MediaPipe was tested on one family (three faces); true Funko or chibi heads with huge eyes and no nose or mouth remain untested and will likely fail.
- **Missing references.** There is no published minimum paintable feature size for Bambu or Orca, no measured flush-waste data for AI figurines, and no official Bambu documentation of `paint_color` or the `Metadata/*.config` files. Everything about those comes from source code and third-party reverse engineering.
- **Licences not opened.** The licence texts for CelebAMask-HQ, GCO v3, CGAL, FLAME, Unity's De-Lighting Tool and the Clonephaze add-on were not checked.

## Conclusion

The competitive frontier has moved. Turning a texture into N colours is now a free slicer feature. The remaining value lies in three things slicers structurally cannot do: knowing that a dark crease is shadow and not black cloth, knowing that two dots above the nose are pupils that must survive at 2 mm, and delivering a file every slicer paints identically without a dialog. Your graph cut already handles boundaries better than any open alternative. The leverage now is at the two ends of the pipeline: an upstream switch (Tripo `v3.5` delight) that costs nothing, and a downstream writer change (`paint_color` and `mmu_segmentation`) that removes the slicer's chance to re-cluster your work.

Face automation is the one genuinely new capability within reach on CPU. Generating `eyes.spec` from MediaPipe landmarks, rather than replacing the painter, makes it a low-risk addition that scales to every order. Two things are time-sensitive and should be scheduled before anything else: Tripo segmentation v1 shuts off on 1 December 2026, and the BiSeNet weight licence needs to be cleared before face parsing goes into paid production.
