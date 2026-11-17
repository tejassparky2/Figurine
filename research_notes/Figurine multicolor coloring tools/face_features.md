# Automatic face-feature location and painting for multi-colour FDM figurines (eyes, irises, brows, lids, lips, beards, bindi, glasses)

Research date: 2026-11-17. Target: Linux container, CPU only, Python 3.13.18, Blender 4.5.16 LTS headless. Wording used below: "[opened]" means the page was fetched and read; "[snippet]" means the claim comes only from a search-result summary because the page returned 402/403 or was not opened. Treat [snippet] claims as lower confidence. "Local test" means I ran it in this container on 2026-11-17 against the project's own Tripo/Meshy meshes in `figurines/projects/family-of-3/` (scripts and outputs are in the session scratchpad `/tmp/claude-0/-home-user-Figurine/ec43f0fb-398c-5383-9f3e-05ab6ac9103e/scratchpad/{scripts,out}/`, which may be wiped).

## 1. 2D face landmark and face-parsing tools: how well they work on stylised/cartoon faces, and whether they install on Python 3.13 Linux CPU (licences)

### Takeaway
Two tools are the practical pair here. **MediaPipe Face Landmarker** (Apache-2.0, a manylinux wheel that installs on Python 3.13, 478 points including iris) and **BiSeNet face parsing as ONNX** (MIT code, run with onnxruntime, CelebAMask-HQ classes) both worked on Tripo/Meshy figurine renders in a local test, including faces behind glasses and on untextured clay renders once each head was cropped. dlib needs a source build and its 68-point model forbids commercial use. InsightFace's models are non-commercial. Cartoon-specific detectors (MDFLD v3, hysts anime-face-detector) exist, but they are research-licensed or tuned for 2D anime.

### Cited Findings
**MediaPipe Face Landmarker**
- Outputs "478 3-dimensional face landmarks" per face, plus 52 blendshape scores and an optional 4x4 facial transformation matrix. The bundle is BlazeFace short-range detector (192x192 input) + FaceLandmarker-V2 mesh model (256x256) + blendshape model (1x146x2), all float16. Landmarks are normalised x,y in [0,1]; z is scaled like x relative to the head centre. Confidence thresholds (`min_face_detection_confidence`, `min_face_presence_confidence`, `min_tracking_confidence`) default to 0.5. Running modes are IMAGE/VIDEO/LIVE_STREAM in Python — [Google AI Edge docs, opened](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
- Face Mesh V2 model card (model date 15 Sep 2022, Apache-2.0, authors Geng Yan and Ivan Grishchenko): input is a face crop with a 25% margin resized to 256x256. Listed limitations: faces looking away more than 80°, rolled more than 8°, less than 50% visible, or "too far away" (crop cannot be rescaled to 192x192 without degradation). Error is reported as IOD-normalised MAE, about 2.1–3.3% in tracking mode and 2.7–3.9% on the first frame across 17 regions. The training data is real smartphone selfies, and the card says nothing about cartoon faces — [Face Mesh V2 model card PDF, opened](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf)
- PyPI on 2026-11-17: `mediapipe 1.2.3` (uploaded 2026-11-11), wheel `mediapipe-1.2.3-py3-none-manylinux_2_28_x86_64.whl`, classifiers Python 3.9–3.14, Apache 2.0. It depends on absl-py, numpy, flatbuffers, opencv-contrib-python, matplotlib and sounddevice — [PyPI JSON API](https://pypi.org/pypi/mediapipe/json)
- Local test: `pip install mediapipe` in a Python 3.13 venv succeeded. The model is `face_landmarker.task` (3.76 MB) from `storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task`. On first run it **failed with `OSError: libGLESv2.so.2`**, fixed by `apt-get install libgles2`. It also prints a harmless `TypeError` from `FaceLandmarker.__del__` at interpreter exit — local test, 2026-11-17
- Local test results with `num_faces=6`, detection/presence confidence 0.3, run on whole images:
  - Approved GPT-image "Pixar" render `approved/family.png` (1254 px): **3/3 faces**
  - Tripo textured front render `models/debug/family_a_colored_texture_front.png`: **3/3 faces**. The iris centres (indices 468/473) landed on the pupils even behind thick black glasses frames, for dad and mom.
  - Colour-quantised print preview `family_d_blender_front.png`: 3/3
  - Meshy print preview `family_b_blender_front.png` (1000 px): 2/3
  - **Untextured clay (Workbench) render of the Tripo geometry `family_d_geometry.ply`** (1600 px wide): **only 1/3 faces**. Cropping each head to about 360–560 px and re-running gave **3/3**, with a plausible fit on eyes, glasses and lips. The baby's iris centre was slightly off-centre.
  - Eye-corner widths were about 35–56 px at these resolutions — local test, 2026-11-17
- MediaPipe Python install note from the docs: `pip install mediapipe`. The docs page states no licence; the model card and PyPI both say Apache-2.0 — [docs, opened](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker); [PyPI](https://pypi.org/pypi/mediapipe/json)

**BiSeNet face parsing (CelebAMask-HQ classes)**
- zllrunning/face-parsing.PyTorch: a "modified BiSeNet" trained on CelebAMask-HQ, MIT licence. Weights are on Google Drive, and the README states no Python version — [GitHub, opened](https://github.com/zllrunning/face-parsing.PyTorch)
- yakhyo/face-parsing: BiSeNet ResNet18 (about 11.2M params, ~43 MB) and ResNet34 (~82 MB). **ONNX release assets**: `https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx` (and resnet34.onnx). MIT licence, Python ≥3.11, trained at 512x512, last listed update 2025-03-20 — [GitHub, opened](https://github.com/yakhyo/face-parsing)
- Class order used by these BiSeNet ports (from yakhyo `utils/common.py` ATTRIBUTES): 0 bg, 1 skin, 2 l_brow, 3 r_brow, 4 l_eye, 5 r_eye, 6 eye_g (eyeglasses), 7 l_ear, 8 r_ear, 9 ear_r (earring), 10 nose, 11 mouth, 12 u_lip, 13 l_lip, 14 neck, 15 neck_l (necklace), 16 cloth, 17 hair, 18 hat — [yakhyo/face-parsing raw source](https://raw.githubusercontent.com/yakhyo/face-parsing/main/utils/common.py). Note that this differs from the HF SegFormer id order below.
- jonathandinu/face-parsing (SegFormer, fine-tuned from nvidia/mit-b5 on CelebAMask-HQ) uses 19 labels in a different order: 0 background, 1 skin, 2 nose, 3 eye_g, 4 l_eye, 5 r_eye, 6 l_brow, 7 r_brow, 8 l_ear, 9 r_ear, 10 mouth, 11 u_lip, 12 l_lip, 13 hair, 14 hat, 15 ear_r, 16 neck_l, 17 neck, 18 cloth. The licence is **"non-commercial research and educational purposes"**. ONNX is available (Xenova). The card warns the dataset is celebrity images, "not necessarily perfectly diverse" — [HF model card, opened](https://huggingface.co/jonathandinu/face-parsing)
- Local test: BiSeNet-R18 ONNX on onnxruntime 1.32 CPU (cp313 wheel), with 512x512 input, ImageNet mean/std and argmax, run on per-head crops:
  - Textured Tripo crops: **glasses (eye_g) segmented cleanly on dad and mom, but the whole lens area including the eyes was labelled eye_g**, so no l_eye/r_eye pixels appeared behind glasses. Brows (only the parts above the frames), nose, upper and lower lips, ears and hair were correct. For the baby (no glasses), brows, eyes, nose and lips were all clean.
  - **The beard was labelled "skin"** (CelebAMask-HQ has no beard class). **The bindi was labelled skin.**
  - Clay (untextured) crops: glasses, brows, lips and nose were still found, and the baby's eyes and brows were found from geometry shading alone — local test, 2026-11-17
- onnxruntime 1.32.0 (2026-11-13) ships cp311–cp314 manylinux x86_64 wheels, MIT — [PyPI JSON](https://pypi.org/pypi/onnxruntime/json)
- EasyPortrait is an alternative face-parsing set with 9 classes: background, person, skin, left/right brow, left/right eye, lips, teeth. The dataset is under a CC BY-SA 4.0 variant, models are `.pth` on MMSegmentation v0.30.0, and the README says nothing about beards — [GitHub hukenovs/easyportrait, opened](https://github.com/hukenovs/easyportrait). A search summary claimed that EasyPortrait annotations treat the beard as not skin — [snippet, search result](https://ar5iv.labs.arxiv.org/html/2304.13509); not confirmed on the repo page.
- Beard-specific: arXiv 2308.15740 "Beard Segmentation and Recognition Bias" says its facial-hair annotations and model "will be publicly available". No repo was confirmed — [snippet](https://arxiv.org/abs/2308.15740)

**face-alignment (1adrianb)**
- 2D and 3D landmarks. Detectors: SFD (default), BlazeFace, YuNet, RetinaFace, SCRFD (needs onnxruntime); dlib is deprecated. CPU is supported (SFD about 138.8 ms on CPU per the PyPI README table). `pip install face-alignment`, Python 3.9+, PyTorch ≥2.0, BSD-3-Clause — [GitHub, opened](https://github.com/1adrianb/face-alignment); [PyPI JSON](https://pypi.org/pypi/face-alignment/json)
- PyPI: face-alignment 1.5.0 (2026-04-06) is a pure-Python py3 wheel; classifiers list up to Python 3.12 only. It needs torch, numba and scikit-image — [PyPI JSON](https://pypi.org/pypi/face-alignment/json)

**dlib**
- PyPI dlib 20.0.1 (2026-03-29) is **sdist only (no wheels)**, so it needs a C++/CMake build on Python 3.13. Boost licence — [PyPI JSON](https://pypi.org/pypi/dlib/json)
- `shape_predictor_68_face_landmarks.dat`: "The license for this dataset excludes commercial use" (iBUG 300-W), and the model "can't be used in a commercial product". The other dlib-models files are CC0/public domain — [davisking/dlib-models, opened](https://github.com/davisking/dlib-models)

**InsightFace / RetinaFace / SCRFD**
- Code is MIT, but "The pretrained models provided with this library are for non-commercial research only". Since Nov 2025, buffalo_l and Inswapper need separate licensing via contact@insightface.ai. RetinaFace (CVPR 2020) and SCRFD (ICLR 2022) are its detectors — [GitHub deepinsight/insightface, opened](https://github.com/deepinsight/insightface); [python-package README, opened](https://github.com/deepinsight/insightface/tree/master/python-package)
- PyPI insightface 2.1 (2026-10-03) is a pure-Python wheel, requires Python ≥3.10, and depends on onnxruntime, so it installs on 3.13 CPU — [PyPI JSON](https://pypi.org/pypi/insightface/json)

**Cartoon/anime-specific detectors**
- **MDFLD** (ICASSP 2024, "Towards Multi-Domain Face Landmark Detection with Synthetic Data from Diffusion Model", Yuanming Li et al., Korea University): 68 points in iBUG order. v2.1 adds 60-point upper/lower eyelid contours per eye. v3 was released 2026-11. Training is mostly cartoon/caricature data (CariFace 33%, synthetic anime 25%, iCartoonFace, Cartoon Set, …) and includes "Pixar-style images and Blender open movies". Install: Python **3.10–3.12**, CUDA GPU and PyTorch 2.4+ (CPU works if you supply a face box, but slowly). v3 TorchScript is 419 MB, v2 is 69 MB. **Licence: "Research use only, without warranty"**; v3 weights are under the DINOv3 licence and SAM 3.1 weights are gated. Stated limitation: "Non-human characters, profile views and covered eyes are still hard" — [GitHub zenonLEE/MDFLD, opened](https://github.com/zenonLEE/MDFLD)
- **hysts/anime-face-detector**: 28 landmarks (HRNetV2) with Faster R-CNN/YOLOv3 detectors, for near-frontal anime faces. Since v0.1.0 it runs without the OpenMMLab runtime (vendored mmpose 0.29/mmdet 2.28/mmcv 1.7). Needs PyTorch ≥2.2 and Python ≥3.12. MIT, with Apache-2.0 vendored code — [GitHub, opened](https://github.com/hysts/anime-face-detector); PyPI 0.1.0 dated 2026-07-05 — [PyPI JSON](https://pypi.org/pypi/anime-face-detector/json)
- kanosawa/anime_face_landmark_detection (24 points on 128 px crops) and nagadomi/animeface-2009 also exist — [snippet, search results](https://awesome.facts.dev/awesome/kanosawa/anime_face_landmark_detection); [snippet](https://github.com/sunxingxingtf/animeface-2009)
- Related research datasets: 3DCaricShop (CVPR 2021, 2,000 artist-made 3D caricatures with 3D landmarks); arXiv 2307.01468 (animatable 3D cartoon faces with 68-landmark annotations) — [snippet, CVF](https://openaccess.thecvf.com/content/CVPR2021/papers/Qiu_3DCaricShop_A_Dataset_and_a_Baseline_Method_for_Single-View_3D_CVPR_2021_paper.pdf); [snippet, arXiv](https://arxiv.org/pdf/2307.01468)

### Inferences
- The faces from Tripo/Meshy "Pixar-style" generation are close enough to human proportions that photo-trained models (MediaPipe, BiSeNet) work on them. In the local test they beat what the cartoon-specific tools promise, and they install trivially on Python 3.13 CPU. Use MDFLD only as a research fallback for very exaggerated chibi/Funko faces where MediaPipe fails, keeping its research-only licence and Python ≤3.12 in mind.
- Recommended split of roles:
  - **MediaPipe** for geometry: eye contours, iris centre and radius, brow lines, lip contours, forehead point for the bindi. It gives sub-region landmarks even through glasses.
  - **BiSeNet** for masks: glasses frames (eye_g), brows, lips, hair/skin boundary.
  - **Texture colour inside the face region** for beard, moustache and bindi, which no CelebAMask-HQ model separates from skin.
- Always run detectors on **per-head crops**: render or crop each head so the face fills about 50–70% of a 512–1024 px image. A whole-scene render of a 3-person bust makes faces too small for BlazeFace's 192x192 input, and on the clay render that is what caused the 1/3 result.
- Prefer the **textured render** (the Tripo/Meshy base-colour texture) over clay for detection. Use clay or geometry renders when the texture is missing or wrong, and to confirm that a feature is sculpted.
- Commercial use (selling figurines): MediaPipe (Apache-2.0) is clean. BiSeNet code is MIT, but the weights were trained on CelebAMask-HQ, which is generally described as non-commercial; jonathandinu's card says so explicitly. This matters for a paid service, so treat it as a legal check item (see Gaps).

### Gaps
- I could not open the CelebAMask-HQ dataset licence page itself, so the commercial status of BiSeNet weights trained on it is unconfirmed (the jonathandinu SegFormer card says non-commercial).
- The local test covered only one family (3 faces, Tripo + Meshy, Indian adults with glasses and a toddler). There was no test on true Funko/chibi heads (huge eyes, no nose or mouth), where MediaPipe will likely fail. That remains untested.
- MediaPipe iris indices 468–477 (centres 468 and 473) come from common usage and were visually confirmed in the local test. I did not open an official page listing them.
- MDFLD, anime-face-detector and face-alignment were not installed or tested locally.

## 2. Projecting 2D detections back onto the mesh (render → detect → ray-cast pixel → triangle), including glasses that occlude the eyes

### Takeaway
This is a well-established pattern: render known-camera views, run a 2D detector, then cast a ray per landmark or mask pixel and take the first triangle hit. With several views, intersect the rays robustly. Blender 4.5's `BVHTree.ray_cast` returns `(position, normal, index, distance)`, so the face index comes for free. Open3D's `RaycastingScene` (cp313 wheel) returns `primitive_ids` in bulk, and both run on CPU. Glasses are best handled with MediaPipe's eye landmarks (it sees through frames), BiSeNet's eye_g mask, and multi-hit rays (the frame is the first hit, the face behind it the second).

### Cited Findings
- Deep-MVLM / "Multi-view Consensus CNN for 3D Facial Landmark Placement" (Paulsen et al.) renders the surface from many cameras (100 random positions, orthographic in the paper), predicts 2D heatmaps per view, and treats each 2D landmark as a 3D ray. The final 3D landmark is an outlier-robust least-squares intersection of the rays — [snippet, arXiv 1910.06007](https://arxiv.org/pdf/1910.06007)
- BioFace3D (2024) does the same and then snaps the point onto a real mesh vertex using least squares plus RANSAC — [snippet, arXiv 2410.00711](https://arxiv.org/pdf/2410.00711). A syndromic-face-scan study projects 2D landmarks back onto the 3D mesh "using a ray casting algorithm" — [snippet, PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7309125)
- Deep-MVLM repo: rendering types are geometry, depth, RGB, RGB+depth and geometry+depth; **geometry/depth rendering is recommended for untextured meshes**. Accepts OBJ/WRL/VTK/STL/PLY. Pretrained DTU3D (73 landmarks) and BU-3DFE (84 landmarks) models. MIT licence. Pinned to Python 3.7, PyTorch 1.2 and VTK 8.2, last update entry 24-03-2021 — [GitHub RasmusRPaulsen/Deep-MVLM, opened](https://github.com/RasmusRPaulsen/Deep-MVLM)
- CVPR 2023 "3D-aware Facial Landmark Detection via Multiview Consistent Training on Synthetic Data" (Zeng et al.) fits a mesh to visible landmarks and re-projects to other views to enforce multi-view consistency — [snippet, project page](https://people.engr.tamu.edu/nimak/Papers/CVPR2023_Landmark/index.html)
- MVF-Net notes that back-projection "is essentially a ray in 3D space", so you need the 3D surface to find where the ray hits — [snippet, arXiv 1904.04473](https://arxiv.org/pdf/1904.04473)
- Blender 4.5.16 LTS `mathutils.bvhtree.BVHTree.ray_cast(origin, direction, distance=sys.float_info.max)` "Returns a tuple: (position, normal, index, distance), Values will all be None if no hit is found". `BVHTree.FromObject(object, depsgraph, deform=True, render=False, cage=False, epsilon=0.0)` — local `__doc__` printout from installed Blender 4.5.16, 2026-11-17
- Open3D `RaycastingScene`: `add_triangles()` returns a geometry id. `cast_rays()` takes [N,6] origin+direction tensors and returns `t_hit`, `geometry_ids`, `primitive_ids` (triangle index), `primitive_uvs` (barycentrics) and `primitive_normals`. `create_rays_pinhole(fov_deg, center, eye, up, width_px, height_px)` builds a full image of rays, and outputs keep the image shape — [Open3D ray casting tutorial, opened](https://www.open3d.org/docs/release/tutorial/geometry/ray_casting.html). open3d 0.20.0 (2026-09-16) has cp310–cp314 manylinux x86_64 wheels, MIT — [PyPI JSON](https://pypi.org/pypi/open3d/json)
- Other renderers on PyPI: moderngl 5.13.0 (2026-10-07, cp39–cp315 wheels, MIT); pyrender 0.1.45 is from 2021-02 (stale); trimesh 5.2.1 (2026-11-12, MIT) — [PyPI JSON moderngl](https://pypi.org/pypi/moderngl/json); [pyrender](https://pypi.org/pypi/pyrender/json); [trimesh](https://pypi.org/pypi/trimesh/json)
- Local test: Blender 4.5 headless `BLENDER_WORKBENCH` (studio light, cavity on, orthographic camera) rendered a 1.89M-face Tripo PLY at 1600 px in seconds. EGL error lines were printed but the render was written. MediaPipe then ran on it (see Q1). The project already uses "Blender BVH visibility" for photo projection (`figurines/scripts/photo_project_colorize.py`, per `figurines/projects/family-of-3/README.md`) — local test and local repo, 2026-11-17
- Glasses research: a 2024 arXiv paper parses the face, removes the eyeglasses region, then reconstructs. ECCV 2020 glasses work trains a U-Net for frame landmarks plus a mask, excluding rimless and half-rim frames. A quality-assessment survey notes that landmark detectors handle slight occlusion by frames and that there are no publications on eye occlusion by frames specifically — [snippet, arXiv 2412.19849](https://arxiv.org/pdf/2412.19849); [snippet, ECCV 2020](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123700375.pdf); [snippet, arXiv 2211.08030](https://arxiv.org/pdf/2211.08030)
- Local test on glasses: MediaPipe iris and eye landmarks fell inside the frames correctly on both textured and clay renders. BiSeNet labelled frames plus lens interior as one eye_g blob. In the clay render the Tripo glasses are open frames (no lens surface), so the eye geometry is visible through them — local test, 2026-11-17

### Inferences
- **A concrete pipeline that fits this repo:**
  1. **Head finding.** Run one front orthographic render (textured, Cycles or Workbench with texture colour) of the whole figurine, and from it get MediaPipe face boxes. If faces are missed, fall back to clay plus per-head crops, or use the head positions from the Tripo segmentation.
  2. **Per-head render.** For each head, render an orthographic view facing the head (yaw from MediaPipe's transformation matrix or the nose direction) at about 20–40 px/mm. A 5 mm eye then spans 100–200 px. Store the camera matrix.
  3. **Detect.** Run MediaPipe (478 points) and BiSeNet (masks) on the crop.
  4. **Triangle labelling.** Cast one ray per pixel with BVHTree or Open3D to get a `pixel → face_index` map. Label each triangle by majority vote of the mask pixels that hit it. Draw vector shapes (iris circle, pupil, catchlight, lid line, brow stroke) as polygons in image space and rasterise them at the same resolution. If triangles are bigger than the shape, split them along the polygon outline first (Q4).
  5. **Visibility.** Only accept hits whose normal faces the camera (dot product below about −0.3) and that are the first hit. Repeat from ±25° yaw views to reach the sides of eyes and lips, and vote.
- **Glasses:**
  - Frames: `eye_g` pixels where the first ray hit lies noticeably in front of the face (larger depth gap than neighbouring skin, or a second hit behind it) and/or the texture is dark.
  - Eyes behind glasses: take them from MediaPipe's eye contour, casting rays that **skip the frame** (continue past the first hit when that triangle is labelled frame).
  - Lenses: Tripo glasses are open frames, so no lens handling is needed. If a mesh has lens surfaces, treat the first hit as lens and also skip it.
- Single-view projection is enough for front-facing busts. Multi-view ray consensus (Deep-MVLM style) is only worth it for 3/4-turned heads.
- Landmark → mesh: snap to the hit point, not the nearest vertex. Tripo meshes are 1.3–1.9M faces at about 120 mm (per the family-of-3 README), so triangles are already sub-0.2 mm and fine enough for 0.4 mm-nozzle features.

### Gaps
- No public repo was found that does exactly "MediaPipe on renders → paint 3MF triangles". The closest are Deep-MVLM (scan landmarks) and Faceit (manual landmark projection, Q5).
- No quantitative accuracy figure (mm error) exists for MediaPipe-projected eye landmarks on stylised meshes. Measuring it would need hand-labelled ground truth.

## 3. 3D-native face landmark / feature detection on meshes (curvature, eye sockets, FLAME/3DMM fitting): practical for cartoon heads?

### Takeaway
3D-native methods exist, but none is practical as the primary detector for stylised AI meshes. Curvature methods assume human-like, near-frontal scans and report modest eye-corner reliability. Deep-MVLM is really multi-view 2D detection with stale dependencies. FLAME fitting needs landmarks first, non-rigid ICP for arbitrary topology, and a non-commercial model. Geometry is most useful as a *refiner*: snapping eye ellipses to the sculpted eyelid opening, confirming bindi or mole bumps, separating protruding glasses frames.

### Cited Findings
- Curvature literature:
  - Shape-index or H-K (mean/Gaussian curvature) classification finds eye corners and nose tip.
  - Bagchi & Bhattacharjee report eye corners correct in 72.2% of cases and nose tip in 98.8%.
  - Perakis et al. combine shape index and spin images and handle up to 80° yaw.
  - Several methods assume a frontal pose or "that the eyes are above the nose", and degrade beyond about 15° rotation.
  - The nose tip has about 2 mm average error in a review.
  - Sources: [snippet, arXiv 1309.3418](https://arxiv.org/pdf/1309.3418); [snippet, Perakis tech report](https://cgi.di.uoa.gr/~graphics/Research/TechReports/3D_Lmk_v1.pdf); [snippet, Polito review](https://iris.polito.it/retrieve/e384c42e-1460-d4b2-e053-9f05fe0a1d67/3D%20human%20face%20description%20landmarks%20measures%20and%20geometrical%20features.pdf)
- FLAME fitting:
  - The official `Rubikplayer/flame-fitting` repo has scripts to fit to 3D landmarks and to a 3D scan. The scan must be in the same coordinate frame with matching landmark order, and the scan unit (m/cm/mm) is configurable.
  - For arbitrary topology, the maintainer advises replacing vertex-to-vertex distance with point-to-surface distance ("non-rigid ICP"). Arbitrary-topology demo code was later added, and FLAME paper §4.2 describes the method.
  - TF_FLAME does not support arbitrary scans.
  - Sources: [snippet, GitHub flame-fitting](https://github.com/Rubikplayer/flame-fitting); [snippet, voca issue 43](https://github.com/TimoBolkart/voca/issues/43); [snippet, TF_FLAME](https://github.com/TauGames/TF_FLAME)
- A 2025 paper's FLAME pipeline: estimate a rigid transform from detector landmarks, scale the scan, then run Chumpy-based non-rigid fitting from flame-fitting — [snippet, arXiv 2512.10517](https://arxiv.org/pdf/2512.10517)
- No result described FLAME fitting to cartoon heads. 3DCaricShop and caricature work (arXiv 2004.09190) use nonlinear or caricature-specific parametric models, because human 3DMMs do not span exaggerated shapes — [snippet, arXiv 2004.09190](https://arxiv.org/pdf/2004.09190); [snippet, 3DCaricShop](https://openaccess.thecvf.com/content/CVPR2021/papers/Qiu_3DCaricShop_A_Dataset_and_a_Baseline_Method_for_Single-View_3D_CVPR_2021_paper.pdf)
- Stylised-rig analogues:
  - Polywink (2018) claims automatic blendshapes for scanned heads and "cartoon characters".
  - A 2019 paper uses automatic landmarking plus regularised ICP to register a generic mesh to a facial mesh.
  - A 2023 IEEE VR paper (BSGen) targets blendshapes for stylised characters with differing topology.
  - Sources: [snippet, CG Channel](https://www.cgchannel.com/2018/07/polywink-creates-blendshapes-and-rigs-for-any-head-model/); [snippet, DFKI ICIP2019](https://www.dfki.de/fileadmin/user_upload/import/10613_ICIP2019.pdf); [snippet, BSGen PDF](https://fuxivirtualhuman.github.io/pdf/IEEEVR2023_BSGen.pdf)
- Local repo evidence: the project already holds hand- or semi-automatically fitted eye-socket ellipses for the Tripo family mesh (`figurines/projects/family-of-3/models/family_d_eye_sockets.json`). Half-widths are 2.12–2.85 mm and half-heights 0.72–0.97 mm, so eye openings are about 4.2–5.7 mm wide × 1.4–1.9 mm tall on a 120 mm-tall 3-person bust. The clay render shows sculpted eyelids, eyeballs, a bindi bump on the baby's and mom's foreheads, and a mole bump — local files and local render, 2026-11-17

### Inferences
- For AI meshes the eyes are usually *sculpted* (lids plus a slightly convex eyeball) but shallow. Use geometry only to refine a 2D-detected eye region:
  - Within the MediaPipe eye polygon (dilated about 0.5 mm), compute per-vertex mean curvature or depth relative to a fitted local plane.
  - The lid crease is a concave ridge loop, and the eyeball is the convex patch inside it.
  - Fit an ellipse to the concave loop and use it as the eye-white boundary. This fixes the "a few px off" photo-label speckle the project hit on thin features (README Revision 2).
- Bindi and moles show up as small convex bumps, about 1–2 mm on a 120 mm bust: local maxima of height above a smoothed surface near MediaPipe forehead point 151/9. That gives a geometric bindi detector that does not depend on texture colour.
- Do not attempt FLAME/3DMM fitting on stylised figurines: oversized eyes and heads fall outside the human shape space. The licence (FLAME is distributed under MPI's own terms) also needs checking, and it adds Chumpy (Python-2-era) dependencies for no gain over 2D-landmarks-plus-ray-cast.

### Gaps
- I did not open FLAME's licence page. Its commercial-use status is unverified.
- No paper found evaluates curvature-based eye detection on stylised or cartoon meshes.

## 4. Figurine/miniature eye and face design practice for multi-colour FDM: styles, feature sizes for 0.4/0.2 mm nozzles, Bambu paint-tool tips, Funko conventions

### Takeaway
Practitioner guidance is thin and anecdotal, but it points one way:
- Below about 5 mm of feature size, AMS colour detail is unreliable.
- Fine eyes need a larger print, a 0.2 mm nozzle, separate eye parts, or hand-painting.
- Simplified eyes read better at small scale than detailed ones: a dark iris or pupil shape, off-white whites, an optional catchlight only when large enough.
- Funko convention is large solid black round eyes, often with no brows or mouth.
- In Bambu Studio, use Fill with edge detection or Smart Fill angle for whole eye or lip patches, the Triangle tool for detail, or separate parts/modifiers.

### Cited Findings
**Feature size and nozzle**
- Geeky Inc AMS anime-figure guide (May 3, 2026, AI-assisted editorial):
  - Avoid "tiny detail work under 5mm", since AMS transitions can't handle it, and avoid "subsurface scattering-style face painting".
  - Single-STL painting is "Not recommended for fine detail like eye decals"; multi-body STLs give more control.
  - Budget 20–40 g of purge waste.
  - Source: [geekyinc.com, opened](https://www.geekyinc.com/multi-color-3d-printing-anime-figures-the-ams-guide-for-p1s-x1c-2026/)
- Bambu forum "How to print small fine things" (Apr 20, 2023): user highrise955 prints miniatures and action figures with a **0.2 mm nozzle, 0.05–0.08 mm layers, Arachne walls, 30–50 mm/s**. He avoids supports on the face, says orientation is key, and notes the finer setting matters most "in the face area, especially the eyes, lips and nose" — [Bambu forum, opened](https://forum.bambulab.com/t/how-to-print-small-fine-things/10417)
- Stroke and line width: BCN3D says stroke thickness should always exceed line width, and small text (7 pt) printed only after reducing outer-wall line width to 0.35 mm on a 0.4 mm nozzle. A Prusa moderator suggests about 0.42 mm external extrusion width, while Raise3D says width should be ≥ nozzle diameter (these conflict) — [snippet, BCN3D](https://bcn3d.com/bcn3d-x-flowalistik-slicing-guide-2-line-width/); [snippet, Prusa forum](https://forum.prusa3d.com/forum/prusaslicer/writing-small-text?language=de); [snippet, Raise3D](https://eushop.raise3d.com/pages/vey-small-features-not-being-printed)
- Forum users say finer features need a 0.2 mm nozzle or Arachne walls. A MakerWorld miniature guide recommends raising Quality → Precision → "Resolution" for minis — [snippet, MakerWorld post 402953 (403 on fetch)](https://makerworld.com/en/community/post/402953)

**Designer practice on MakerWorld and Printables (all [snippet]; pages returned 403)**
- A googly-eye plant stake keeps the pupils as separate parts, says to use "Split to parts" so the pupils stay positioned, and offers to print in one colour and paint the pupils after — [MakerWorld 3142565](https://makerworld.com/en/models/3142565-googly-eyes-plant-stake-no-ams-customizable)
- A Gastly figure offers a blank-eye option "if your printer can't do the small pupils, or if you scale down" — [Printables 1053856](https://www.printables.com/model/1053856-gastly-pokemon-multipart)
- A Mewtwo MMU remix says "the eye details are extremely fine", so print large or use a fine nozzle — [Printables 761926](https://www.printables.com/model/761926-mewtwo-mmu-painted-remix)
- A Superman MMU model recommends printing the AMS version face-down with a slow first layer — [Printables 1001035](https://printables.com/model/1001035-superman-v3-mmuams-single-color-models)
- A BJD/figurine eye model makes the pupils as holes to be painted or filled with coloured UV resin — [MakerWorld 2834737](https://makerworld.com/en/models/2834737-eyes-for-bjd-figurines-etc)

**Bambu Studio paint tools**
- Triangle tool colours one facet, or a list of facets when dragged.
- Fill colours connected facets until a different colour, and with "Edge detection" on it also stops at corners sharper than the "Smart Fill Angle" threshold.
- Gap Fill auto-fills small gaps with a neighbour's colour.
- Source: [snippet, Bambu wiki color painting tool (402 on fetch)](https://wiki.bambulab.com/en/software/bambu-studio/color-painting-tool). Creality's equivalent fills gaps with area ≤ a set threshold — [snippet, Creality help](https://www.creality.com/uk/help/help-introduction-to-the-color-painting-feature)
- A MakerWorld creator calls "Fill – Edge Detection" the best brush for colouring single faces and falls back to the Triangle tool when Fill isn't accurate. A forum reply suggests one modifier per colour (right-click → Add Modifier → Load) — [snippet, MakerWorld creator posts](https://makerworld.com/en/@user_2560918044/posts); [snippet, Bambu forum](https://forum.bambulab.com/t/bambu-lab-studio-paint-tool/182646)
- Adafruit "AI 3D Printed Figure" (MasterpieceX image-to-3D, Bambu Studio):
  - Export the retopologised mesh at the "high" setting to make per-polygon colour assignment easier.
  - Colour with the Fill tool and adjust "Smart fill angle".
  - The print took about 15–17 h.
  - No eye-specific advice; author and date not shown.
  - Source: [Adafruit Learn, opened](https://learn.adafruit.com/ai-figure.md?view=all)
- The OrcaSlicer wiki describes painted-area adaptive subdivision (for texture displacement) and warns that uniform subdivision clears unbaked paint. It is unverified whether this applies to colour painting — [snippet, OrcaSlicer wiki](https://www.orcaslicer.com/wiki/print_prepare/prepare_texture_displacement_pro)

**Eye styles from miniature painting (transferable rules)**
- Brush Slinger, "How to Paint Eyes on Miniatures" (Mar 29, 2026):
  - Use a warm off-white rather than pure white.
  - Keep the iris stripe narrower than you think, with white visible on both sides.
  - Dot method (dark socket plus small light dot) reads from 3+ ft.
  - Optional pure-white catchlight in the corner, for hero models only.
  - Add a thin dark upper-lid line, which "hides imprecision at the top edge".
  - By scale: 15 mm and below dot only; 28 mm full technique; 32 mm add a pupil dot; 54 mm+ full iris and pupil.
  - Source: [prime-paint.pages.dev, opened](https://prime-paint.pages.dev/blog/how-to-paint-eyes)
- Hobby forums:
  - A vertical iris line beats a round dot at small scale.
  - A pupil touching the upper lid looks natural; white showing above and below the dot looks "surprised".
  - At 1/35 the whites are usually not visible; dark irises read better than coloured ones at 28 mm.
  - "Most people make the iris too small."
  - Source: [snippet, ENWorld thread](https://www.enworld.org/threads/painting-eyes-advice.112848/page-2); [snippet, DakkaDakka](https://www.dakkadakka.com/dakkaforum/posts/list/502762.page)

**Funko and vinyl-toy conventions**
- Funko Pop! (line created 2010, launched 2011): "modelled in a style similar to the Japanese chibi style", with "large squarish heads, disproportionately small bodies, and large, circular black eyes". It also comes in 6, 10 and 18 inch sizes — [Wikipedia, opened](https://en.wikipedia.org/wiki/Funko)
- The fan wiki says the mouth and eyebrows are "notably missing from a standard Pop! Vinyl". A StarWars.com piece says that on Luke's Pop "you really only have eyebrows and hair style to work with". A review says single black circles made Sonic "look weird" — [snippet, Funko fandom wiki (402)](https://funko.fandom.com/wiki/Pop!); [snippet, starwars.com](https://starwars.com/news/the-mandalorian-funko-pop-exclusive-reveal); [snippet, TheGamer](https://www.thegamer.com/funko-pops-nothing-like-characters/)

**Project's own measured feature sizes** (local files; a 120 mm-tall 3-person bust from Tripo)
- Eye openings: about 4.2–5.7 mm wide × 1.4–1.9 mm tall (`family_d_eye_sockets.json`).
- Rev 5 eye style ("reference-photo style eyes"): one solid black oval pupil per eye, about 60% of eye width and full eye height, with **no white, no lid line, no catchlight**. Pupil semi-axes are 1.08–1.27 × 0.75–0.85 mm, so about 2.2–2.5 × 1.5–1.7 mm ovals. Baby eyebrows are 0.5 mm-wide strokes along the sculpted brow ridges (`figurines/projects/family-of-3/eyes/eyes_v5.spec`).
- The README notes there were not enough slots for bindis, lips, the ring and buttons, which snapped to skin, black or light blue: "A 6th slot (red) would bring back the bindis" (`figurines/projects/family-of-3/README.md`).
- Source: local repo files, read 2026-11-17

### Inferences
- **Size rules of thumb** (my synthesis, not a published standard; test-print to confirm):
  - **Vertical faces.** On a front-facing vertical face, a colour region's horizontal extent is set by where the slicer splits perimeters, at about line-width resolution. Its vertical extent is quantised to layer height (0.08–0.12 mm typical for figurines).
  - **Minimum reliable dimension.** With a 0.4 mm nozzle (~0.42 mm lines), aim for **≥0.8–1.0 mm in the narrowest direction** for any colour island (about 2 lines; BCN3D "stroke > line width"). With a 0.2 mm nozzle that drops to about 0.4–0.5 mm.
- **Applying this to a 120 mm bust** (eyes about 5 × 1.6 mm):
  - A 2.2–2.5 mm black pupil oval prints with a 0.4 mm nozzle. It is what the project shipped.
  - An eye white plus iris plus pupil is marginal on 0.4 mm: the white slivers either side of a 2.4 mm iris are about 1.2 mm, but the slivers above and below are near zero, which is why Rev 5 dropped them.
  - A 0.5 mm catchlight dot or a 0.3 mm lid line will not print reliably on 0.4 mm. A ≥0.8 mm catchlight is plausible on 150 mm figures or with a 0.2 mm nozzle.
- **Style by figure size:**
  - **80–100 mm, or adults on multi-person busts:** a solid dark pupil/iris oval filling about 60% of eye width and full height (Funko/"dot" style). Optionally a 0.5 mm brow stroke where sculpted. Skip whites, lids and catchlights.
  - **120–150 mm single figure, or child/large-eye heads:** off-white eye white + dark iris (pupil merged) touching the upper lid + one ≥0.8 mm catchlight in the upper corner on the same side in both eyes. Add a dark upper-lid line ≥0.8 mm only if a slot is spare (it can share the iris colour).
  - **Brows:** ≥0.8 mm thick (0.5 mm worked in the project for a toddler, but it is marginal).
  - **Lips:** a muted pink or red only if a slot is spare; otherwise leave skin and rely on the sculpt.
  - **Bindi:** a ≥1.5 mm red dot, or leave it as a sculpted bump in skin colour.
  - **Beards:** use the hair colour.
  - **Glasses:** use the hair or black slot. The frame bar is usually ≥1 mm, so it prints well.
- **Colour budget:** eyes and brows should reuse existing slots: pupils and brows use the hair/black slot, whites use a cream or white clothing slot, and catchlights use the same white. That keeps faces within 4–5 AMS slots, consistent with the project's 5-slot palette.
- **Triangle density:** paint-tool fidelity depends on mesh triangles. Tripo's 1.3–1.9M faces are fine for this. If a mesh has been decimated, subdivide locally around eyes before colouring, or do the colouring in Python (split triangles along the shape outline) before writing the 3MF.

### Gaps
- No primary Reddit thread (r/BambuLab, r/3Dprinting, r/PrintedMinis) with measured minimum eye-feature sizes was found or opened. Reddit content came back only as mirrors or snippets.
- MakerWorld, Printables and the Bambu wiki returned 403/402, so designer notes are search-snippet only.
- A [snippet] mentioned a MakerWorld eye set sized for 10/8/6/4 cm chibi figures, with the first plate of four pairs at 6 g. I could not confirm which URL it came from.
- There is no published, measured guide to the smallest colour island an AMS/Bambu printer reproduces on vertical walls. A test coupon (dots and lines at 0.4–2.0 mm on a vertical face) is the reliable answer.

## 5. Existing open-source tools that already automate figurine face painting

### Takeaway
I found **no open-source tool that automatically detects and paints facial features on figurine meshes for multi-colour FDM** (as of 2026-11-17). The adjacent tools are:
- Generic texture → painted 3MF converters, one non-commercial (FullSpectrum Studio) and others commercial (hitem3d, Neural4D).
- Blender's Faceit, which projects manually placed landmarks from the front view for rigging.
- The project's own photo-projection colouriser.

The automation would need to be built from MediaPipe + BiSeNet + ray casting (Q1–Q3).

### Cited Findings
- FullSpectrum Studio converts textured sources into painted 3MF projects for Orca-family slicers. Licence: PolyForm Noncommercial 1.0.0 (not OSI). GLB/OBJ import is "experimental", and OBJ input needs complete UVs and a PNG/JPEG base colour — [snippet, mirror of Gr33k3D/FullSpectrum-Studio](https://gh.r-mj.com/Gr33k3D/FullSpectrum-Studio)
- Printproof is MIT and does 3MF → GLB colour customisation (the opposite direction) — [snippet, AlternativeTo](https://alternativeto.net/software/3mf-to-glb/about/)
- Commercial multicolour exporters: hitem3d multicolor API (GLB only, up to 200 MB) and Neural4D (AI colour regions, exports 3MF/GLB) — [snippet, fal.ai hitem3d](https://fal.ai/models/hitem3d/hi3d/multicolor/api); [snippet, Neural4D](https://www.neural4d.com/features/multicolor-3d-print-file-generator)
- Faceit (Blender add-on) semi-automatically generates ARKit shape keys "for humanoid characters" and claims it handles "arbitrary and even stylized characters". Workflow: position landmarks, "Project the Landmarks from Front View", generate rig, Smart Bind — [snippet, Blender Market](https://blendermarket.com/products/faceit)
- In this repo, `figurines/scripts/photo_project_colorize.py` projects the approved photo onto visible surfaces (Blender BVH visibility, silhouette registration, optical-flow alignment). Eyes were then hand-specified as ellipse/stroke specs (`eyes_v5.spec`), and `detect_spectacles.py` only asks a VLM (Gemini via fal.ai) yes/no about spectacles. No landmark detector is used anywhere in `figurines/`; a grep for mediapipe/dlib/bisenet/insightface found nothing — local repo, 2026-11-17

### Inferences
- The project's hand-written `eyes.spec` format (ellipse/stroke primitives in mm, with `on=` colour masks) is a natural target for automation. Generate the spec from MediaPipe landmarks projected to mesh mm coordinates:
  - eye polygon → skin-reset ellipse
  - iris centre and radius → pupil ellipse
  - brow landmarks → stroke polyline
  - lip contour → lip polygon
  - forehead landmark plus a red-texture or bump test → bindi dot
  - BiSeNet eye_g → frame mask
  
  The existing painter then stays the single writer of 3MF triangles.
- A minimal CPU stack that is all-wheel on Python 3.13: `mediapipe` (Apache-2.0) + `onnxruntime` + BiSeNet-R18 ONNX (MIT code, CelebAMask-HQ weights, so check the licence) + Blender 4.5 `BVHTree` or `open3d` RaycastingScene. The only system dependency is `libgles2`.

### Gaps
- I could not open FullSpectrum Studio's canonical GitHub page (only a mirror snippet), so its exact features and whether it handles eyes are unverified.
- I did not search GitHub code search exhaustively for small personal repos ("auto paint eyes 3mf"). Something niche may exist.
