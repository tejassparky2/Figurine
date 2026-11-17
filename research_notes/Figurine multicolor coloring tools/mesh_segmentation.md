# 3D mesh part segmentation for AI-generated figurines: runnable methods, licences, hardware, quality

Scope: splitting an AI-generated figurine mesh (people, often several in one model, about 1-2M triangles) into parts such as hair, face, eyes, eyebrows, beard, lips, glasses, shirt, trousers, shoes and accessories, so that each part gets one flat filament colour. The target machine is a Linux container with a CPU only (no CUDA GPU). Research date: 2026-11-17.

Notes on sources:
- Facts were checked against the repo README and LICENSE files (fetched raw from raw.githubusercontent.com), arXiv pages, Hugging Face model cards, vendor docs and GitHub issue lists.
- Star counts are as shown on the GitHub pages on 2026-11-17.
- Items marked **[local test]** were measured in this session's container: 4 vCPU, 15 GB RAM, Python 3.13, no GPU. They are first-hand measurements, not web sources.

---

## Q1. Learning-based open-source segmenters: what has public code and weights, when was it released, what GPU does it need, can it run on a CPU, and does it reuse multi-view renders with SAM/SAM2 (and so the texture)?

### Takeaway
Only a few methods segment an existing mesh, have public code and weights, and run without training per category:
- SAMesh, PartField, SAMPart3D, P3-SAM (Hunyuan3D-Part), GeoSAM2, PartSAM, Point-SAM and Find3D.
- All are documented and tested only on CUDA GPUs. GeoSAM2 is the one repo that says outright "CPU is supported but slow".
- PartField is by far the best and fastest on the main benchmark: about 10 s per shape and 79.2 class-agnostic mIoU, against 56.9 for SAMesh and 53.5 for SAMPart3D. Its licence is NVIDIA's non-commercial licence.
- SAMesh has no licence at all.
- P3-SAM's licence excludes the EU, the UK and South Korea.
- The multi-view render + SAM family (SAMesh, SAMPart3D, GeoSAM2, MeshSegmenter, SATR, PartSLIP) is the one that could in principle take the colour texture into account.
- PartCrafter, PartPacker, OmniPart, HoloPart and X-Part are part generators or part completers. They do not label the faces of an existing mesh.

### Cited Findings

**Comparison table: methods that segment an existing mesh or point cloud**

| Method | Released | Code + weights | Licence | Hardware (documented) | Input / mechanism | Granularity / output | Quality evidence |
|---|---|---|---|---|---|---|---|
| **SAMesh** (Segment Any Mesh) | arXiv 24 Aug 2024, v2 9 Mar 2025 ([arXiv](https://arxiv.org/abs/2408.13679)) | Yes, [gtangg12/samesh](https://github.com/gtangg12/samesh), 202 stars; SAM2 checkpoint downloaded separately | **No LICENSE file.** [Issue #22](https://github.com/gtangg12/samesh/issues/22), "repo is all-rights-reserved by default", was closed 28 May 2026 without adding one | Tested on Python 3.12 + CUDA 11.8; no VRAM figure; CPU not mentioned ([README](https://github.com/gtangg12/samesh)) | Multi-view renders of normals, shape-diameter scalars or matte go to SAM2, then 2D masks are lifted to mesh faces; zero-shot, no vocabulary ([README](https://github.com/gtangg12/samesh); [arXiv](https://arxiv.org/abs/2408.13679)) | Class-agnostic parts per face; mask-count tuning via config | ~7 min per shape, 56.86 mIoU on PartObjaverse-Tiny ([PartField paper Table 1](https://arxiv.org/html/2504.11451v1)); human study on a curated set of *generated* meshes beats SDF ([arXiv](https://arxiv.org/abs/2408.13679)) |
| **PartField** (NVIDIA) | arXiv 2504.11451 (Apr 2025), ICCV 2025 ([arXiv](https://arxiv.org/html/2504.11451v1)) | Yes, [nv-tlabs/PartField](https://github.com/nv-tlabs/PartField), 478 stars; Objaverse-trained checkpoint on HF; the PartNet-trained model is not released "due to licensing restrictions" | **NVIDIA License: "non-commercially … for non-commercial research and educational purposes only"** (LICENSE §3.3, raw file) | Python 3.10, PyTorch 2.4, CUDA 12.4; on OOM, lower `n_point_per_face` to 500; CPU not documented ([README](https://github.com/nv-tlabs/PartField)) | Feedforward PVCNN + triplane + transformer on sampled points (100k points per shape in training); no rendering, so the texture is ignored ([paper](https://arxiv.org/html/2504.11451v1)) | Agglomerative clustering on face adjacency gives a **hierarchical part tree** (set with `--max_num_clusters`, e.g. 20); KNN or remesh options for meshes with many components; **no semantic labels** ([README](https://github.com/nv-tlabs/PartField); [paper](https://arxiv.org/html/2504.11451v1)) | **~10 s per shape, 79.18 mIoU** vs SAMesh 56.86, SAMPart3D 53.47, PartSLIP 31.54, Find3D 21.28. "Human-Shape" column 80.85, though the header is garbled in the HTML ([paper Table 1](https://arxiv.org/html/2504.11451v1)) |
| **SAMPart3D** | arXiv 2411.07184 (Nov 2024) ([arXiv](https://arxiv.org/html/2411.07184)) | Yes, [Pointcept/SAMPart3D](https://github.com/Pointcept/SAMPart3D), 584 stars; PTv3-object weights on HF | MIT (LICENSE file) | CUDA (`CUDA_VISIBLE_DEVICES`, pointops); no VRAM figure ([README](https://github.com/Pointcept/SAMPart3D)) | Renders a GLB in **Blender 4.0, 16 views RGB + depth**, then trains a small per-object MLP ([README](https://github.com/Pointcept/SAMPart3D)). Paper: ~1 min of SAM masks + ~5 min of MLP training per object ([arXiv](https://arxiv.org/html/2411.07184)) | Scale-conditioned granularity (scales 0-2, edit `val_scales_list`); optional GPT-4o part naming ([arXiv](https://arxiv.org/html/2411.07184)) | ~15 min per shape, 53.47 mIoU ([PartField paper](https://arxiv.org/html/2504.11451v1)); Human-Shape category (29 objects) class-agnostic mIoU 54.4 ([arXiv](https://arxiv.org/html/2411.07184)) |
| **P3-SAM** (in Hunyuan3D-Part) | arXiv 8 Sep 2025 ([arXiv](https://arxiv.org/abs/2509.06784)); licence file dated "Release Date: September 23, 2025" | Yes, [Tencent-Hunyuan/Hunyuan3D-Part](https://github.com/Tencent-Hunyuan/Hunyuan3D-Part), 562 stars; weights at [HF tencent/Hunyuan3D-Part](https://huggingface.co/tencent/Hunyuan3D-Part) | **Tencent Hunyuan 3D-Part Community License.** "DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA"; a licence is required above 1M MAU; outputs may not be used to improve other AI models (LICENSE, raw file) | Python 3.10, PyTorch 2.4.0+cu121, CUDA 12.1, plus Sonata dependencies ([P3-SAM README](https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-Part/main/P3-SAM/README.md)) | Native 3D point-promptable model trained on ~3.7M labelled models; `auto_mask.py` gives automatic masks; a point-prompt web app is also included ([arXiv](https://arxiv.org/abs/2509.06784); P3-SAM README) | Part instances + bounding boxes + semantic features (no text labels) | Project page has a section "Our Segmentation Results on AI Generated Models", images only, no numbers ([project page](https://murcherful.github.io/P3-SAM/)). HF Space **running on ZeroGPU** ([Space](https://huggingface.co/spaces/tencent/Hunyuan3D-Part)) |
| **GeoSAM2** (VAST) | arXiv 2508.14036 (Aug 2025), CVPR 2026 ([HF card](https://huggingface.co/VAST-AI/GeoSAM2/blob/main/README.md)) | Yes, [VAST-AI-Research/GeoSAM2](https://github.com/VAST-AI-Research/GeoSAM2) inference only; ckpt 588 MB fp32 / 294 MB bf16, ~154M params | Apache-2.0 (code and checkpoint) | "A CUDA-capable GPU with PyTorch 2.3+ **(CPU is supported but slow)**"; the CUDA op is optional (`GEOSAM2_BUILD_CUDA=0`) (README) | Blender 4.0+ renders **12 views of color + depth + normal** at 1024²; SAM2 with LoRA propagates a mask across views, then back-projects to per-face labels | **Prompt-only** (2D click or mask on one view); no automatic mode; post-processing sometimes needs per-mesh tuning ([HF card](https://huggingface.co/VAST-AI/GeoSAM2/blob/main/README.md)) | SOTA claims on PartObjaverse-Tiny / PartNetE (paper, via search summary) |
| **PartSAM** | arXiv 2509.21965 (Sep 2025), ICLR 2026 ([ICLR](https://iclr.cc/virtual/2026/poster/10006586)) | Yes: README TODO marks inference code, weights and training code as released; weights `Czvvd/PartSAM` on HF ([czvvd/PartSAM README](https://github.com/czvvd/PartSAM)) | No LICENSE file found at repo root | PyTorch 2.4.1 + CUDA 12.4; needs torkit3d + apex (CUDA builds) (README) | Native-3D, SAM-style click-promptable, triplane encoder; trained partly on PartField-generated labels (README) | Binary mask per prompt; "eval_everypart" script for automatic segmentation | Not evaluated here |
| **Point-SAM** | (release date not checked) | Yes, [zyc00/Point-SAM](https://github.com/zyc00/Point-SAM) + [HF Space](https://huggingface.co/spaces/yuchen0187/Point-SAM) | MIT | `FORCE_CUDA=1` torkit3d, apex with CUDA extension (README) | Promptable point-cloud model; "support[s] mesh segmentation by sampling points from the mesh and propagat[ing] labels back" (README) | Click-prompted masks | n/a |
| **Find3D** | arXiv 2411.13550, ICCV 2025 Highlight ([repo](https://github.com/ziqi-ma/Find3D)) | Yes, MIT, 129 stars; HF Space `ziqima/Find3D` | MIT | "GPU with CUDA" required; FlashAttention build "might take up to three hours" | **Text queries** on point clouds (.pcd); no mesh input in the demo | Per-point labels for given queries | ~10 s per shape but 21.28 mIoU (5,000 points) ([PartField paper](https://arxiv.org/html/2504.11451v1)) |
| **PartSLIP / PartSLIP++** | CVPR 2023 / Dec 2023 | PartSLIP++: [zyc00/PartSLIP2](https://github.com/zyc00/PartSLIP2), MIT | MIT | PyTorch3D + SAM + GLIP (GPU) | Renders the point cloud; **few-shot checkpoints per object category** (PartNet-E) (README) | Category-specific semantic parts | PartSLIP ~4 min per shape, 31.54 mIoU ([PartField paper](https://arxiv.org/html/2504.11451v1)) |
| **COPS** | WACV 2025 ([repo](https://github.com/marco-garosi/COPS)) | Code yes | No LICENSE file found | PyTorch 2.1 + cu121, pytorch3d (README) | Aggregates 2D (DINOv2) features onto points geometrically | Part clusters / zero-shot labels | n/a |
| **MeshSegmenter** | ECCV 2024 ([ECVA](https://www.ecva.net/papers/eccv_2024/papers_ECCV/html/9881_ECCV_2024_paper.php)) | **No code.** Repo is README-only, "The code will be updated soon" ([repo](https://github.com/zimingzhong/MeshSegmenter)) | none | n/a | SAM on renders + Stable Diffusion texture synthesis + multi-view revoting | Semantic | n/a |
| **SAM3D** (Pointcept) / **SAMPro3D** | 2023 / 3DV 2025 | Yes: [SegmentAnything3D](https://github.com/Pointcept/SegmentAnything3D) (MIT), [SAMPro3D](https://github.com/GAP-LAB-CUHK-SZ/SAMPro3D) (Apache-2.0) | MIT / Apache-2.0 | CUDA pointops / SAM | **Indoor scene** point clouds (ScanNet), not object parts (READMEs) | Scene instances | Not applicable to figurines |

**Generators and completers: these do not segment the user's existing mesh**
- **PartCrafter** (NeurIPS 2025): generates a part-structured mesh from an image.
  - Fully open-sourced 2025-07-13; HF demo `alexnasa/PartCrafter`.
  - Needs "a CUDA-enabled GPU with at least 8GB VRAM". MIT.
  - Source: [README](https://github.com/wgsxm/PartCrafter).
- **PartPacker** (NVIDIA): image to a part-separated mesh.
  - "~10GB GPU memory (assuming float16)"; tested on 3090/4090; HF demo `nvidia/PartPacker`.
  - No LICENSE file found at the repo root.
  - Source: [README](https://github.com/NVlabs/PartPacker).
- **OmniPart**: image to part-aware 3D, with a PartField module inside its Space. LICENSE file is MIT (copyright VAST-AI-Research).
  - Sources: [repo](https://github.com/HKU-MMLab/OmniPart); [HF Space tree](https://huggingface.co/spaces/omnipart/OmniPart/tree/main/modules/PartField/partfield).
- **HoloPart** (VAST, MIT): completes parts that were already segmented.
  - Input is a mesh plus a per-face `mask.npy`.
  - The README recommends **SAMesh or SAMPart3D** to produce the masks.
  - Source: [README](https://github.com/VAST-AI-Research/HoloPart).
- **X-Part**: generates complete parts from P3-SAM boxes.
  - Its sub-README still lists "Realse the pre-trained models" as not done, and the repo calls the release "a light version of X-Part", with the full version on Hunyuan3D-Studio.
  - This conflicts with the top-level README's weights link.
  - Sources: [XPart README](https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-Part/main/XPart/README.md); [HF card](https://huggingface.co/tencent/Hunyuan3D-Part).

**Which methods could use the user's colour texture**
- SAMPart3D renders RGB + depth of the GLB in Blender ([README](https://github.com/Pointcept/SAMPart3D)).
- GeoSAM2 renders a color channel alongside depth and normals ([HF card](https://huggingface.co/VAST-AI/GeoSAM2/blob/main/README.md)).
- SAMesh's default modes are untextured: normals, SDF and matte. The paper reports that normals and SDF renders work better than plain untextured renders ([arXiv](https://arxiv.org/abs/2408.13679)).
- SAMesh issue #7, "Error when using PBR textured mesh", is still open ([issues](https://github.com/gtangg12/samesh/issues?q=is%3Aissue)).
- PartField, P3-SAM and PartSAM work on geometry or points only.

**SAM 3** (the 2D foundation model that would drive a DIY "render, text-prompt, lift" pipeline):
- 848M params; "segment all instances of an open-vocabulary concept specified by a short text phrase".
- The README requires a "CUDA-compatible GPU with CUDA 12.6 or higher".
- SAM License; gated checkpoints. SAM 3.1 checkpoints were released 03/27/2026.
- Source: [facebookresearch/sam3 README](https://cdn.jsdelivr.net/gh/facebookresearch/sam3@main/README.md).

**Hosted GPU options seen**
- Hunyuan3D-Part Space, running on ZeroGPU ([link](https://huggingface.co/spaces/tencent/Hunyuan3D-Part)).
- Find3D Space ([repo](https://github.com/ziqi-ma/Find3D)) and Point-SAM Space ([repo](https://github.com/zyc00/Point-SAM)).
- PartPacker and PartCrafter demos (READMEs above).
- No official PartField Space was found. PartField code is bundled inside the `rayli/particulate` Space ([HF](https://huggingface.co/spaces/rayli/particulate/blob/main/PartField/README.md)).
- No SAMesh Space was found.

### Inferences
- **None of the learning-based segmenters is a realistic CPU-only tool as documented.** They depend on CUDA builds: pointops, torkit3d/apex, FlashAttention, torch-scatter CUDA wheels, SAM2 builds.
  - PartField (a feedforward pass plus clustering) is the most plausible to *port* to CPU, but its README is CUDA-only and nobody has reported trying.
  - GeoSAM2 officially runs on CPU, but it is prompt-driven: someone must click one view per part.
  - The practical route is a rented GPU (Colab, RunPod) or the HF ZeroGPU Space for P3-SAM, with the per-face labels carried back to the CPU pipeline.
- **Face count:** the point-based methods sample points and map them back to faces (PartField samples per face; Find3D was benchmarked with 5k points). A 1-2M-triangle mesh is therefore not a hard limit, but VRAM is: PartField's OOM advice is fewer points per face.
  - Decimating to about 100-300k faces, segmenting, then transferring labels back by nearest face is the low-risk approach.
- **Granularity mismatch:** the class-agnostic models are trained on Objaverse/PartNet-style parts (limbs, head, accessories). On a figurine the eyes, eyebrows and lips are often painted texture or very shallow relief, so geometry-only models (PartField, P3-SAM, PartSAM) are unlikely to separate them.
  - The texture-aware multi-view approaches, or the 2D human/face parsers in Q2, are better suited to these fine facial classes.
- **Licensing for a commercial figurine business:**
  - PartField: non-commercial only.
  - SAMesh: no licence granted.
  - Hunyuan3D-Part: territory-restricted, and unusable if the user is in the EU or UK.
  - Cleanest licences: GeoSAM2 (Apache-2.0), SAMPart3D (MIT), Find3D (MIT), Point-SAM (MIT). SAM2-derived weights are Apache-2.0 per the GeoSAM2 card.

### Gaps
- No measured CPU runtimes were found for any learning-based method (SAMesh, PartField, P3-SAM, SAMPart3D, GeoSAM2), and no GitHub issue asks about CPU-only use for SAMesh or PartField (issue lists checked).
- VRAM needs for SAMesh, PartField, P3-SAM and SAMPart3D are not stated anywhere I found.
- PartSAM, COPS and PartPacker licence terms could not be confirmed (no LICENSE at the repo root).
- No release date was checked for Point-SAM.
- GeoSAM2 numeric results were seen only through a search summary of the paper.

---

## Q2. Text-promptable and semantic methods: which take labels like "hair" or "eyes", and how good are they on stylised humans?

### Takeaway
- The 3D text-promptable methods are research code with weak or untested quality on stylised humans:
  - SATR (2023, CUDA 11.1 + Kaolin).
  - 3DHighlighter (2023, 16 GB GPU, non-deterministic).
  - Find3D (low mIoU).
  - PartSLIP (per-category few-shot).
  - MeshSegmenter (no code).
- The strongest semantic signal for the user's exact label set comes from **2D human-parsing and face-parsing models**, run on multi-view renders of the textured mesh and lifted to faces. Their class lists already contain hair, eyebrows, eyes, glasses, lips, upper clothes, pants, shoes, hat, bag, scarf and necklace, and some document CPU inference. The best ones are non-commercial, though.

### Cited Findings
- **SATR** (arXiv 11 Apr 2023):
  - Assigns segments from multi-view zero-shot 2D *detector* boxes, with topological reweighting.
  - Introduces **FAUST coarse and fine-grained** human-body benchmarks, beating a baseline by 1.3% (coarse) and 4% (fine) mIoU. Absolute numbers were not on the abstract page.
  - Source: [arXiv](https://arxiv.org/abs/2304.04909).
  - Install is old: CUDA 11.1, torch 1.10.1, Kaolin. MIT ([README](https://github.com/Samir55/SATR)).
- **3DHighlighter** (CVPR 2023): localises one text-described region per run by CLIP-guided optimisation.
  - "The installation will fail if run on something other than a CUDA GPU machine"; needs a "16 GB GPU".
  - "results can vary across different runs even when fully seeded".
  - Source: [README](https://github.com/threedle/3DHighlighter).
- **Find3D**: text queries such as "head", "ear" or "arm" on point clouds; CUDA required. Its demo file is `mickey.pcd`, but no human or figurine metrics are reported ([repo](https://github.com/ziqi-ma/Find3D)). Class-agnostic mIoU is 21.28 on PartObjaverse-Tiny ([PartField paper](https://arxiv.org/html/2504.11451v1)).
- **PartSLIP++**: uses "few-shot checkpoints for each object category" from the PartNet-Ensembled dataset, so it has no human or figurine category ([README](https://github.com/zyc00/PartSLIP2)).
- **SAMPart3D semantic mode**: part names come from GPT-4o on highlighted renders. Human-Shape semantic mIoU is 44.4 vs 39.3 for PartSLIP. Vroid anime characters are shown only qualitatively ([arXiv](https://arxiv.org/html/2411.07184)).
- **MeshSegmenter**: code not released ([repo](https://github.com/zimingzhong/MeshSegmenter)).
- **SAM 3**: text-prompted concept masks in 2D; CUDA 12.6+ GPU per its README; SAM License ([README](https://cdn.jsdelivr.net/gh/facebookresearch/sam3@main/README.md)).
- **2D parsers that match the figurine label set:**
  - **face-parsing** (`jonathandinu/face-parsing`, SegFormer mit-b5, 84.6M params, CelebAMask-HQ):
    - 19 classes: skin, nose, **eye_g (eyeglasses), l_eye, r_eye, l_brow, r_brow**, ears, mouth, **u_lip, l_lip, hair, hat**, ear_r (earring), neck_l (necklace), neck, **cloth**.
    - Runs on CUDA, MPS **or CPU**; an ONNX/Transformers.js version exists.
    - **Licence: non-commercial research/education.**
    - Source: [model card](https://huggingface.co/jonathandinu/face-parsing).
  - **segformer_b2_clothes** (27.4M params, ATR dataset):
    - 18 classes: Hat, **Hair, Sunglasses, Upper-clothes**, Skirt, **Pants**, Dress, Belt, **Left/Right-shoe, Face**, legs, arms, **Bag, Scarf**.
    - Licence "other", pointing to the NVlabs SegFormer licence.
    - Source: [model card](https://huggingface.co/mattmdjaga/segformer_b2_clothes).
  - **Sapiens-seg-1B** (Meta, Aug 2024): 28-class body-part segmentation, 1.169B params, 1024×768 input, **CC-BY-NC-4.0** ([model card](https://huggingface.co/facebook/sapiens-seg-1b)).

### Inferences
- A practical CPU-only semantic pipeline:
  1. Render N views of the textured figurine (Blender, pyrender or PyMeshLab rasters).
  2. Run segformer_b2_clothes for clothes, hair and shoes, and face-parsing on the face crops for eyes, brows, lips and glasses.
  3. Accumulate per-face label votes by visibility.
  4. Clean up with a crease-aware graph cut (Q5).
- At 27-85M params, these models should take seconds per view on a CPU, but no CPU timing was published (see Gaps).
- These parsers are trained on photos. On Pixar-style figurine renders, domain shift is likely, especially for exaggerated eyes. Accuracy on stylised renders is unverified.
- Licence check: face-parsing and Sapiens are non-commercial. A commercial deployment would need a permissively licensed face parser, or SAM 2 / SAM 3 with prompts (SAM 3 needs a GPU per its README).

### Gaps
- No published evaluation of any text-promptable 3D method on stylised or AI-generated figurines (Funko/Pixar-like) was found.
- No CPU latency numbers for segformer_b2_clothes or face-parsing.
- The SegFormer (NVlabs) licence terms were not opened.
- SATR absolute FAUST mIoU values were not retrieved.

---

## Q3. Classical and geometric tools: SDF (CGAL), spectral clustering, crease or curvature region growing, libigl/CGAL/PyMeshLab, Blender operators, and DIY multi-view SAM2 projection

### Takeaway
- Everything in this family runs on a CPU, and most of it installs from PyPI on this container.
- **CGAL's SDF segmentation** is the reference geometric method: SDF, then a GMM, then an alpha-expansion graph cut with concave-crease-aware smoothness. It is slow at 1-2M faces (46 s for SDF alone at 89k faces in 2014 benchmarks), and the Python `cgal` wheels stop at Python 3.12-era builds.
- PyMeshLab, libigl, trimesh and Blender provide crease detection, connected components, curvature, and selection grow/shrink. None has a semantic or part segmentation filter.
- Geometry alone separates limbs and thick parts. It cannot find painted-on boundaries (eyes, lips, brows, shirt/skin colour edges on smooth surfaces).

### Cited Findings
**CGAL Surface_mesh_segmentation** ([docs](https://doc.cgal.org/latest/Surface_mesh_segmentation/index.html)):
- Method:
  - SDF is computed per facet with an inward ray cone, bilateral smoothing and normalisation.
  - A k-cluster GMM gives soft labels.
  - An **alpha-expansion graph cut** produces the hard labels. Its smoothness term is based on dihedral angle, with **convex edges weighted 0.08 and concave edges 1**, so boundaries prefer concave creases.
- Parameters: k (default 5) and λ (default 0.26; higher gives fewer segments).
- Timings (CGAL 4.4, i7 3.2 GHz):
  - SDF: 88,928 triangles in 46.1 s (Simple_cartesian) or 62.3 s (EPICK).
  - Graph cut: 314-4,239 ms for 2-15 clusters.
- Input: a closed, 2-manifold, intersection-free mesh is expected. "runs on imperfect meshes but may give unreliable results".

**CGAL from Python:**
- **[local test]** `pip install cgal` found no wheel for Python 3.13. The latest version listed was `5.6.post202402071826`.
- The [cgal-swig-bindings README](https://github.com/CGAL/cgal-swig-bindings) says packages are on PyPI. It does not mention Surface_mesh_segmentation (grep found no match).
- SAMesh's repo ships a `notebooks/mesh_shape_diameter_function.ipynb` SDF baseline ([README](https://github.com/gtangg12/samesh)).

**PyMeshLab** ([filter list](https://pymeshlab.readthedocs.io/en/latest/filter_list.html); **[local test]** `pymeshlab 2025.7.post1` installs on CPU):
- No segmentation filter. Relevant building blocks:
  - `compute_selection_crease_per_edge`: signed dihedral thresholds, concave default -45°, convex default +45°.
  - `meshing_cut_along_crease_edges`.
  - `generate_splitting_by_connected_components`.
  - `compute_selection_by_color_per_face`.
  - `compute_scalar_by_discrete_curvature_per_vertex`.
  - `compute_scalar_by_heat_geodesic_distance_from_selection_per_vertex`.
  - `apply_selection_dilatation` / `apply_selection_erosion`.
  - `compute_color_from_active_rasters_projection`: projects camera images onto the mesh, which is a ready-made multi-view-to-mesh transfer.
- The docs reference "watershed segmentation" only in a curvature citation.

**libigl Python** (**[local test]** `libigl 2.6.3`): `igl.sharp_edges` and `igl.facet_components` exist; `igl.shape_diameter_function` is **not exposed** in the Python module (`hasattr` returned False).

**Spectral clustering:** [kugelrund/mesh_segmentation](https://github.com/kugelrund/mesh_segmentation) is a Blender add-on implementing Liu and Zhang 2004 spectral clustering with numpy/scipy. MIT. Runs on CPU.

**Blender:**
- *Select ‣ Select Sharp Edges* selects edges whose face-normal angle exceeds "Sharpness" ([manual](https://docs.blender.org/manual/en/latest/modeling/meshes/selecting/sharp_edges.html)).
- *Select Linked (Ctrl-L)* has **Delimit** options Normal, Material, **Seam, Sharp, UVs** ("Stop at island borders in any UV map"), so linked selection can flood-fill between sharp edges or UV islands ([manual](https://docs.blender.org/manual/en/latest/modeling/meshes/selecting/linked.html)).

**Existing DIY multi-view projection designs to copy:**
- SAMesh: renders, then SAM2 masks, then lifting ([README](https://github.com/gtangg12/samesh)).
- SAMPart3D: 16 Blender views ([README](https://github.com/Pointcept/SAMPart3D)); the paper uses 36 views ([arXiv](https://arxiv.org/html/2411.07184)).
- GeoSAM2: 12 views at 1024², colour + depth + normal + `meta.json` cameras, then back-projection to per-face labels ([HF card](https://huggingface.co/VAST-AI/GeoSAM2/blob/main/README.md)).

### Inferences
- **SDF cost at the user's scale:** scaling CGAL's 2014 figure roughly linearly (46 s per 89k faces), SDF on 1-2M faces would take about 10-20+ minutes on one core.
  - Decimating to about 100-200k faces first, then transferring labels back, keeps it in the tens of seconds. This is an extrapolation, not a measurement.
- **What SDF is good for:** it separates parts of different thickness (arms vs torso, hair strands vs head). It is pose-invariant but not colour-aware, so it is a geometric prior, not a complete answer.
- **Crease region growing works only where geometry has creases.** AI-generated figurines often have modelled creases at shirt hems, shoe soles, hair masses and glasses frames. Eyes, brows and lips are usually just texture on a smooth surface.
- **Pipeline sketch for the CPU container:**
  1. Texture-colour or 2D-parser votes as unary terms.
  2. A crease or dihedral-weighted graph cut (Q5).
  3. Connected components to split multiple people (PyMeshLab or trimesh).
- PyMeshLab's raster projection filter or a custom numpy z-buffer can do the render-and-lift step without a GPU.

### Gaps
- CGAL licensing could not be verified: cgal.org/license returned 403. Surface_mesh_segmentation is commonly GPL/commercial dual-licensed, but this is unverified here.
- No benchmark of CGAL SDF on more than 100k faces with a modern CGAL was found.
- Spectral clustering on 1M+ faces (eigendecomposition cost) was not measured; it almost certainly needs decimation.

---

## Q4. Commercial and API options the user already has (Tripo, Meshy), and how they compare with open source

### Takeaway
- **Tripo `/v3/mesh/segment`** accepts *any* uploaded model (GLB, GLTF, FBX, OBJ, STL; at most 150 MB).
  - Default model `v1.0-20250506` is geometric and retires 1 Dec 2026.
  - `v2.0-20260430` (beta) is semantic, with `simple` / `balanced` / `detailed` granularity, `split_by_connectivity`, and an optional reference image.
  - Example cost: 40 credits.
- **Meshy Auto Split** is limited to Meshy-6/7-generated models with at most 8M faces, at 10 credits.
  - Its `by_color` mode cuts along colour regions named from the *source image*. This is the closest commercial feature to "one filament per region", but it rejects uploaded models.
- Neither vendor documents a face-level part taxonomy (hair, eyes, lips).
- Open-source PartField or P3-SAM would give comparable class-agnostic parts, but they need a GPU and carry licence caveats.

### Cited Findings
**Tripo mesh segmentation** ([docs](https://developers.tripo3d.com/en/docs/mesh-segment.md)):
- Request: `POST https://openapi.tripo3d.com/v3/mesh/segment`. `input` is one of a task_id, a file_token, or a URL.
- `model`: default `v1.0-20250506` (geometry-based) or `v2.0-20260430` (beta, "semantic labeling").
- v2-only parameters: `segmentation_granularity` (`simple` | `balanced` (default) | `detailed`), `split_by_connectivity` (default true), `ref_image` (overrides granularity and connectivity).
- Formats GLB, GLTF, FBX, OBJ, STL; max 150 MB; no face limit stated.
- Output: `model_url` (GLB) plus `rendered_image_url`. Example response shows `credits_consumed: 40`.
- Mesh completion consumes the segment task's `part_names`, e.g. `tripo_part_0` ([mesh-complete docs](https://developers.tripo3d.com/en/docs/mesh-complete)).
- v1 "is retiring and stops working on December 1, 2026". v2 identifies "limbs, accessories, and mechanical pieces".
- "models with distinct, well-defined parts segment more cleanly than smooth, fused shapes".
- Scenario's v2 surface accepts GLB, OBJ and FBX at up to 150 MB and advises decimating very dense meshes ([Scenario help](https://help.scenario.com/articles/9861107995-tripo-segmentation-the-essentials)).
- Third-party wrapper 3D AI Studio charges 80 credits per request ([3daistudio](https://www.3daistudio.com/Platform/API/Documentation/segmentation/tripo)).

**Meshy Auto Split** ([API docs](https://docs.meshy.ai/api/auto-split.md)):
- Request: `POST /openapi/v1/print/split`, modes `auto` | `by_parts` | `by_color`.
- `by_parts` and `by_color` take 1-10 named parts, and anything unnamed becomes one extra part.
- `by_color` cuts "along color regions you name, found in the source image rather than the model's texture" and needs Image-to-3D input.
- Only Meshy 6/7 source tasks are accepted. Tasks built on uploaded models return 400, and inputs over 8,000,000 faces return 400.
- Outputs include `3mf`, which keeps parts separate; STL fuses them. 10 credits per task.
- The web-app guide and help centre partly disagree on whether textured models can be split (search summary of [webapp guide](https://docs.meshy.ai/en/webapp/guides/3d-model/auto-split), not opened).

**Commercial Blender add-on: AMS Splitter** ([docs](https://superhivemarket.com/products/ams-splitter/docs)):
- **Clusters Base Color texture colours in LAB** (2-24 colours, default 6), with an option to reduce baked shadows.
- Optional voxel remesh to one closed solid, then smoothing of speckled boundaries.
- Outputs material slots for Bambu Studio. $80. Features thinner than about 2 voxels may be lost.

### Inferences
- Tripo v2 `detailed` with a `ref_image` (the approved render) is the cheapest experiment for semantic parts on models the user already has, since uploads are allowed.
  - Whether it splits eyebrows or lips is undocumented and should be tested on one figurine.
- Meshy's `by_color` is attractive, but it only works on Meshy generations, so it cannot be applied to Tripo/Hunyuan meshes.
- Open source vs these APIs:
  - PartField / P3-SAM give similar class-agnostic splits and allow local control (a hierarchical tree to choose granularity), but need GPU time.
  - Neither side reliably separates painted-on facial features. That still needs texture-based labelling plus graph-cut cleanup.

### Gaps
- No published comparison of Tripo v1/v2 or Meshy split quality against PartField or SAMesh was found.
- No Tripo face-count limit is documented. Per-credit USD pricing was not checked.
- Hitem3D's colour segmentation and CGTrader's segmentation tool appeared in search results but were not opened.

---

## Q5. Graph-cut and MRF refinement of segment boundaries on meshes (alpha-expansion with crease-aware smoothness)

### Takeaway
Crease-aware alpha-expansion on the face-adjacency graph is a well-established, CPU-cheap technique:
- CGAL uses it with concave-weighted dihedral smoothness.
- MeshSegNet's released code uses pygco with a −log(θ/π) dihedral pairwise term.
- **[local test]** On this container, `gco-wrapper` refines a 1.31M-face mesh with 10 labels in about 11 s.

### Cited Findings
- **CGAL**: an alpha-expansion graph cut with data term = −log(cluster probability). Smoothness is dihedral-angle-based, with **convex 0.08 vs concave 1** weights ([CGAL docs](https://doc.cgal.org/latest/Surface_mesh_segmentation/index.html)).
- **MeshSegNet** (IEEE TMI 2020, MIT; [chunfenglian/MeshSegNet](https://github.com/chunfenglian/MeshSegNet), file `step6_predict_with_post_processing_pygco.py`):
  - unaries = `-100*log10(prob)`.
  - Potts pairwise term.
  - Edge weight = `-log10(theta/pi)*phi` when θ>π/2, otherwise `-beta*log10(theta/pi)*phi` with `beta = 1 + |n_i·n_j|`.
  - Scaled by `lambda_c=30`, then `pygco.cut_from_graph`.
  - The search summary of the repo confirms "The multi-label graph cut is implemented by the python package pygco" ([search result / repo](https://github.com/chunfenglian/MeshSegNet)).
- **pyGCO / gco-wrapper**: wraps gco-v3.0 ("graph cuts based move-making algorithm for optimization in Markov Random Fields"). Supports `cut_general_graph` with per-edge weights ([Borda/pyGCO README](https://github.com/Borda/pyGCO)).
- **[local test]** `pip install PyMaxflow gco-wrapper` succeeded on Python 3.13 (PyMaxflow 1.3.2, gco-wrapper 3.0.9).
- **[local test]** Benchmark:
  - Mesh: icosphere with 1,310,720 faces and 1,966,080 adjacent face pairs. `trimesh.face_adjacency` took 1.0 s.
  - Labels: 10, with noisy unaries (argmin accuracy 0.699).
  - Edge weights: `0.12*exp(-dihedral/0.3)+0.01`, i.e. cheap to cut across creases.
  - `gco.cut_general_graph(..., algorithm='expansion', n_iter=-1)` converged in **11.1 s** with **0.987** accuracy vs ground truth.
  - Caveat: passing int32 costs returned all-zero labels (degenerate). Float costs, which the wrapper auto-scales, worked.

### Inferences
- **Recommended refinement step for any upstream labeller** (Tripo parts, PartField clusters, texture colour clusters, 2D-parser votes):
  - Unary = −log(vote fraction).
  - Pairwise = Potts × f(dihedral, colour difference), with concave or sharp edges cheap to cut, à la CGAL or MeshSegNet.
  - Add a texture-colour gradient term so boundaries also snap to painted edges.
  - This runs in seconds at the user's mesh size on a CPU.
- For two-label problems (e.g. "is this face hair?"), PyMaxflow's exact s-t min-cut suffices. For multi-label problems, use gco alpha-expansion.

### Gaps
- No paper or repo was found that combines texture-colour-gradient and dihedral terms specifically for AI-generated textured meshes. That combination would be custom.
- The benchmark used synthetic labels on a sphere. Real figurine boundary quality is untested.

---

## Q6. Reported results on AI-generated meshes (Tripo, Meshy, TRELLIS, Hunyuan3D): issues, Reddit, X, blogs

### Takeaway
- Evidence on AI-generated meshes comes mostly from the method authors themselves:
  - SAMesh curated and evaluated on a dataset of *generated* meshes.
  - PartField ships TRELLIS demo meshes, plus KNN and remesh options for their messy connectivity.
  - P3-SAM shows AI-generated results; X-Part recommends AI-generated input.
  - HoloPart recommends SAMesh or SAMPart3D for preparing masks.
- User-side evidence is thin: a handful of SAMesh issues about over- and under-segmentation and textured-mesh errors. No Reddit or X threads on segmenting AI figurines for multicolour printing were found.

### Cited Findings
- **SAMesh**:
  - The authors "curated and released a dataset of generated meshes"; a human evaluation shows better generalisation than SDF ([arXiv](https://arxiv.org/abs/2408.13679)).
  - Open issues include #9 "My 3D model is divided into a lot of parts" (Jan 2025), #11 "My mesh is not divided at all" (closed Mar 2025), #7 "Error when using PBR textured mesh", #17 "IndexError during rendering: face indices out of bounds" and #19 "meshes doesn't match mask" (Dec 2025) ([issue list](https://github.com/gtangg12/samesh/issues?q=is%3Aissue)).
- **PartField**:
  - Demo data includes "Trellis3D (AI-generated)" meshes. For meshes with "multiple connected components or poor connectivity", it recommends `--option 1 --with_knn True` or a remesh-then-cluster path ([README](https://github.com/nv-tlabs/PartField)).
  - None of its 15 issues mention CPU, VRAM, large meshes or AI-generated meshes ([issue list](https://github.com/nv-tlabs/PartField/issues?q=is%3Aissue)).
- **P3-SAM / X-Part**:
  - The project page has a section "Our Segmentation Results on AI Generated Models" (images only) ([project page](https://murcherful.github.io/P3-SAM/)).
  - "For X-Part, we recommend using scanned or AI-generated meshes (e.g., from Hunyuan3D V2.5 or V3.0)… P3-SAM can handle any input mesh" ([README](https://github.com/Tencent-Hunyuan/Hunyuan3D-Part)).
- **HoloPart** recommends SAMesh or SAMPart3D for the segmentation step before part completion ([README](https://github.com/VAST-AI-Research/HoloPart)).
- **Vendors**:
  - Scenario's Tripo article: smooth, fused shapes segment worse than models with distinct parts ([Scenario](https://help.scenario.com/articles/9861107995-tripo-segmentation-the-essentials)).
  - AMS Splitter targets "AI-generated models from tools like Meshy, Rodin, or Luma AI" using texture colour clustering ([docs](https://superhivemarket.com/products/ams-splitter/docs)).
- A search for Reddit threads on splitting AI-generated models into colour parts returned **no Reddit results**, only vendor pages (search run 2026-11-17).

### Inferences
- AI-generated figurine meshes are typically one fused, watertight-ish surface with baked texture. Part boundaries such as shirt/neck and hair/forehead are often only in the texture.
  - This favours texture-aware labelling (colour clustering, 2D parsers, multi-view SAM on textured renders) plus geometric graph-cut cleanup, over geometry-only part models.
- Where the generator does produce separated or creased parts (glasses, hats, separate figures), connected components plus crease-aware cuts handle them on a CPU.

### Gaps
- No independent (non-author) benchmark of SAMesh, PartField or P3-SAM on Tripo, Meshy or Hunyuan figurines was found.
- No Reddit, X or blog reports by 3D-printing users were found.
- The contents of the SAMesh issues (beyond their titles) were not read, so it is unknown whether those meshes were AI-generated.
