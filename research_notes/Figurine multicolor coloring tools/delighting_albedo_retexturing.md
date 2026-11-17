# De-lighting, Albedo Extraction and Re-texturing for Flat-Colour AI Figurines (as of 2026-11-17)

Legend: every bullet has a link. Unmarked = page/file actually opened (WebFetch or raw file / API via curl). **[snippet]** = seen only in a search-engine result summary, not opened; treat as lower confidence. "Checked 2026-11-17" = live state observed from this container on that date (HF Spaces API, `pip index versions`). Target box: Linux container, CPU only, Python 3.13.18; currently installed: numpy 2.5.3, pillow 12.3.0, trimesh 5.2.1, **no torch / no opencv** (local `pip list`, 2026-11-17). `pip index versions` on this interpreter reports installable: torch 2.15.0 (+cpu wheel on download.pytorch.org), opencv-contrib-python-headless 5.0.0.93, scikit-image 0.26.0, diffusers 0.43.0, sam2 1.1.0, pymeshlab 2025.7.post1, embreex 4.4.0.post1 (local check, 2026-11-17).

## 1. Image intrinsic decomposition / albedo estimation with public code (CPU feasibility, stylised renders)

### Takeaway
Three families exist: (a) non-diffusion, multi-stage networks (Careaga & Aksoy "Intrinsic", v2/v2.1 weights; has a `device` argument, so CPU inference is possible, academic-use-only licence, patent pending); (b) diffusion decomposers (Marigold-IID lighting/appearance – Apache-2.0 code, OpenRAIL++-M weights, 1–50 DDIM steps; RGB↔X – Adobe non-commercial, NVIDIA-GPU-only; IntrinsicAnything – object-centric albedo + specular, new 2026 "registration" licence); (c) specular-only removers (StableDelight, Apache-2.0) which fix white highlights but not dark crease shading. None publishes CPU timings and none is validated on Pixar-style figurine renders; IntrinsicAnything (object-centric, trained on synthetic Objaverse renders [snippet]) is the closest domain match, while Careaga/Marigold are trained on photographs / indoor synthetic scenes.

### Cited Findings
**Careaga & Aksoy – `compphoto/Intrinsic` (TOG 2023 "Ordinal Shading" + TOG/SIGGRAPH Asia 2024 "Colorful Diffuse Intrinsic Image Decomposition in the Wild")**
- One repo covers both papers; pipeline = grayscale ordinal shading → low-res chromaticity → high-res sparse albedo → diffuse-shading network trained "using only a single rendered indoor dataset"; supports per-pixel white balance and specularity removal — [GitHub README](https://github.com/compphoto/Intrinsic)
- arXiv 2409.13690, submitted 20 Sep 2024; decomposes in-the-wild photos into albedo, diffuse shading and a non-diffuse residual — [arXiv](https://arxiv.org/abs/2409.13690); [project page](https://yaksoy.github.io/ColorfulShading)
- Licence: "This implementation is provided for academic use only"; "Patent pending"; `setup.py` has `license=""`, version 0.0.1 — [GitHub README](https://github.com/compphoto/Intrinsic); [setup.py](https://raw.githubusercontent.com/compphoto/Intrinsic/main/setup.py)
- Install: `pip install https://github.com/compphoto/Intrinsic/archive/main.zip` (or clone + `pip install .`); depends on pinned git commits `altered_midas@fb51e3a` and `chrislib@9a4c63f`; `python_requires=">3.6"` — [setup.py](https://raw.githubusercontent.com/compphoto/Intrinsic/main/setup.py)
- `load_models(path, stage=4, device='cuda', compiled=False, ...)` – device is a parameter (default CUDA); weights `v2` and `v2.1` are downloaded from GitHub releases with `map_location=device` (stage_0…stage_4 .pt files) — [pipeline.py](https://raw.githubusercontent.com/compphoto/Intrinsic/main/intrinsic/pipeline.py)
- Output dict keys include `hr_alb` (final high-res albedo), `dif_shd` (diffuse shading), `residual` (img − dif_img), plus `gry_shd`, `wb_img`, `pos_res`, `neg_res` — [GitHub README](https://github.com/compphoto/Intrinsic)
- Hosted: HF Space `ccareaga/Intrinsic` (running on `zero-a10g`, checked 2026-11-17) and a Colab notebook — [HF Space](https://huggingface.co/spaces/ccareaga/Intrinsic); [HF API](https://huggingface.co/api/spaces/ccareaga/Intrinsic); [README](https://github.com/compphoto/Intrinsic)
- README says nothing about CPU runtime, resolution limits or stylised/non-photo images — [GitHub README](https://github.com/compphoto/Intrinsic)

**Marigold-IID (ETH PRS) – diffusers `MarigoldIntrinsicsPipeline`**
- `prs-eth/marigold-iid-lighting-v1-1`: fine-tuned from Stable Diffusion 2, trained on HyperSim; outputs albedo, diffuse shading, non-diffuse residual (I = A·S + R), sRGB in / linear out; resize longer side to ~768 px; DDIM 1–50 steps; uncertainty only with ensemble > 2; weights licence CreativeML Open RAIL++-M; journal paper arXiv 2505.09358 (14 May 2025) — [model card](https://huggingface.co/prs-eth/marigold-iid-lighting-v1-1)
- `prs-eth/marigold-iid-appearance-v1-1`: trained on InteriorVerse; albedo + roughness + metallicity — [model card [snippet]](https://huggingface.co/prs-eth/marigold-iid-appearance-v1-1)
- Code repo licence Apache-2.0 — [LICENSE.txt](https://raw.githubusercontent.com/prs-eth/Marigold/main/LICENSE.txt)
- Official diffusers example loads fp16 and `.to("cuda")` — [Diffusers docs [snippet]](https://huggingface.co/docs/diffusers/api/pipelines/marigold)
- Marigold journal paper claims single-step + lightweight VAE + quantisation gives "<100 ms on most commodity hardware" — for depth, hardware unspecified — [arXiv 2505.09358 [snippet]](https://arxiv.org/html/2505.09358)
- Community Replicate wrapper notes FP16 on GPU / FP32 on CPU — [Replicate readme [snippet]](https://replicate.com/jasonod888/marigold-intrinsics/readme); official HF Space `prs-eth/marigold-intrinsics` exists (last modified 2026-08-05) — [HF API](https://huggingface.co/api/spaces/prs-eth/marigold-intrinsics)
- No CPU timing for the intrinsics checkpoints found anywhere — (search returned none; see Gaps)

**RGB↔X (Zeng et al., Adobe, SIGGRAPH 2024)**
- RGB→X estimates albedo, normals, roughness, metallicity, lighting; built on SD 2.1; weights `zheng95z/rgb-to-x` on HF — [README](https://raw.githubusercontent.com/zheng95z/rgbx/main/README.md); [project page](https://zheng95z.github.io/publications/rgbx24)
- "this environment is only compatible with NVIDIA GPUs … recommend … a minimum of 12GB" — [README](https://raw.githubusercontent.com/zheng95z/rgbx/main/README.md)
- Adobe Research License: use/redistribution "for noncommercial research purposes only", explicitly excluding "development of commercial products" — [LICENSE](https://raw.githubusercontent.com/zheng95z/rgbx/main/LICENSE)
- Community Space `blanchon/rgb2x` is PAUSED (cpu-basic requested), checked 2026-11-17 — [HF API](https://huggingface.co/api/spaces/blanchon/rgb2x)

**IntrinsicAnything (ZJU3DV, arXiv 2404.11593)**
- Diffusion models for **albedo** and **specular shading** of an object; foreground mask via RGBA input, `--mask_dir`, SAM, or bundled rembg script; optional high-res refinement guided by a low-res albedo pass; weights downloaded from the HF Space — [README](https://raw.githubusercontent.com/zju3dv/IntrinsicAnything/master/README.md)
- Live demo Space `LittleFrog/IntrinsicAnything` running on `zero-a10g` (last modified 2026-10-15) — [HF API](https://huggingface.co/api/spaces/LittleFrog/IntrinsicAnything)
- Licence is now "Project Registration License (PRL) v1.0, Copyright (c) 2026": free for research/education/personal; any company/organisation "Project Use" (commercial or not) is free but must be registered via a Google Form before use — [LICENSE](https://raw.githubusercontent.com/zju3dv/IntrinsicAnything/master/LICENSE)
- Trained on synthetic Objaverse; a 2025 follow-up (IntrinsicReal, arXiv 2509.00777) says it "fails under certain circumstances" on real MVImgNet photos — [IntrinsicReal [snippet]](https://arxiv.org/html/2509.00777v1)

**StableDelight / StableNormal (Stable-X)**
- StableDelight = "specular reflection removal from textured surfaces", built on StableNormal; trained on Hypersim, Lumos and TSHRNet specular-highlight datasets; one-step diffusion with multi-scale SSIM loss; `torch.hub.load("Stable-X/StableDelight", "StableDelight_turbo", trust_repo=True)`; README badge Apache-2.0 — [README](https://raw.githubusercontent.com/Stable-X/StableDelight/main/README.md)
- Weights `Stable-X/yoso-delight-v0-4-base` — [HF model](https://huggingface.co/Stable-X/yoso-delight-v0-4-base); official Space status CONFIG_ERROR (checked 2026-11-17) — [HF API](https://huggingface.co/api/spaces/Stable-X/StableDelight)
- StableNormal licence Apache-2.0 — [LICENSE.txt](https://raw.githubusercontent.com/Stable-X/StableNormal/main/LICENSE.txt)

**Others checked**
- "IID-Anything": no paper/repo of that name found; closest is IntrinsicAnything — [search result set incl. IntrinsicReal [snippet]](https://arxiv.org/pdf/2509.00777)
- IntrinsiX (Kocsis, Höllein, Nießner, arXiv 2504.01008) is **text-to-PBR generation** (LoRAs for albedo / normal / roughness+metallic), not decomposition of an existing image — [project page [snippet]](https://peter-kocsis.github.io/IntrinsiX); [arXiv [snippet]](https://arxiv.org/html/2504.01008v2)
- FlowIID (arXiv 2601.12329, 18 Jan 2026): single-step latent flow-matching IID, "parameter-efficient", "suited for resource-constrained" deployment; no parameter count, timing or code link on the abstract page — [arXiv](https://arxiv.org/abs/2601.12329)
- LumiX (arXiv 2512.02781) reportedly decomposes real images into albedo/irradiance/normal and compares to RGB↔X and Colorful Shading — aggregator only — [EmergentMind [snippet]](https://www.emergentmind.com/topics/lumix)

### Inferences
- For the "highlights turn white" failure, a residual/specular-aware method is needed (Careaga `residual`, Marigold-lighting `R`, IntrinsicAnything specular, or StableDelight). For "creases turn black", a shading-removing method is needed (Careaga `dif_shd`, Marigold-lighting `S`, IntrinsicAnything albedo). StableDelight alone will not lift crease shadows.
- CPU ranking (unbenchmarked, from architecture): Careaga/Aksoy (feed-forward DPT/MiDaS-style stages, no denoising loop) is likely the fastest learned option on CPU and is directly `device='cpu'`-capable; Marigold at 1–4 DDIM steps on an SD2-size UNet at 768 px is plausible but probably tens of seconds+ per image in FP32; RGB↔X is GPU-only by its own README; IntrinsicAnything is an LDM with refinement pass (likely slow on CPU). Verify by benchmarking.
- Licensing for a paid figurine business: only Marigold (Apache-2.0 code + OpenRAIL++-M weights) and StableDelight (Apache-2.0 badge) look commercially usable without negotiation; Careaga = academic only + patent pending; RGB↔X = non-commercial; IntrinsicAnything = free but requires project registration.
- Because the pipeline only needs to de-light ONE 2D reference render per figurine (not hundreds of views), a hosted GPU Space (ccareaga/Intrinsic, LittleFrog/IntrinsicAnything, prs-eth/marigold-intrinsics) or Colab is a viable fallback to slow CPU inference — subject to each licence.
- Stylised renders: GPT-image-style Pixar renders have smooth, saturated albedo regions and soft global illumination; methods trained on synthetic CG (HyperSim, Objaverse) may transfer better than photo-trained ones, but a decomposition can also re-tint saturated colours (albedo/shading ambiguity). Expect to snap albedo outputs to an N-colour palette rather than use them raw.

### Gaps
- No published CPU runtimes for any of these intrinsic models; no Python-3.13 install reports (Careaga's pinned git deps may conflict with torch 2.15). A local benchmark (e.g., `load_models('v2.1', device='cpu')` on a 1024 px render) is needed.
- No evaluation of any method on stylised/Pixar/figurine renders was found.
- StableDelight's licence is stated only via README badge (no LICENSE file found at main/master).

## 2. Texture de-lighting for 3D assets (generator-side and post-hoc)

### Takeaway
In practice the most reliable de-lighting happens **before or during texture generation**: Hunyuan3D-2 runs a 1.3B InstructPix2Pix "delight" model on the reference image then bakes white-light multi-views; Hunyuan3D-2.1 / MaterialMVP generate albedo+metal-rough directly; Meshy (`remove_lighting`, Meshy-6 only; Meshy-7 automatic) and Tripo (`delight`, texture model v3.5-20260815 only, default true) expose switches. Post-hoc texture de-lighters (Unity De-Lighting Tool, Agisoft De-Lighter, Substance AO Cancellation) target photogrammetry and need AO/bent-normal maps or manual strokes. Open-source re-texturers (MaterialAnything, Paint-it, TEXGen, SyncMVD, TRELLIS.2) all need 24–48 GB NVIDIA GPUs.

### Cited Findings
**Hunyuan3D-2 delight + paint (Tencent, Jan 2025)**
- `Hunyuan3D-Delight-v2-0`: "Image Delight Model", released 2025-01-21, 1.3B params; Paint-v2-0 (1.3B) and Paint-v2-0-Turbo (2025-04-01) — [README](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/README.md); weights folder — [HF](https://huggingface.co/tencent/Hunyuan3D-2/tree/main/hunyuan3d-delight-v2-0)
- Implementation (`Light_Shadow_Remover`): `StableDiffusionInstructPix2PixPipeline`, `torch_dtype=torch.float16`, EulerAncestral scheduler, image resized to **512×512**, empty prompt, **50 steps**, `image_guidance_scale=1.5`, `guidance_scale=1.0`, seed 42; alpha eroded, background set white; output then colour-corrected per channel (mean/std matching to the input with `scale=0.95`, reverted if MSE gets worse) — [dehighlight_utils.py](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/hy3dgen/texgen/utils/dehighlight_utils.py)
- Texture pipeline: delight applied to the (recentred) prompt image; candidate views azimuth 0/90/180/270 + top/bottom with weights [1, 0.1, 0.5, 0.1, 0.05, 0.05]; render/texture size 2048; baking weights views by `project_cos_map ** bake_exp` with `bake_exp = 4`, then UV inpainting; `enable_model_cpu_offload` used for the delight model in low-VRAM mode — [pipelines.py](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/hy3dgen/texgen/pipelines.py)
- Paper: delight model trained on pairs rendered "under the illumination of a random HDRI environmental map and an even white light"; multi-view model trained on white-light renders for "illumination-invariant texture synthesis"; without delighting, "illumination and shadows" get "baked into the texture maps"; 8–12 bake views; UV holes filled by reciprocal-geometric-distance weighting — [arXiv 2501.12202v3](https://arxiv.org/html/2501.12202v3)
- VRAM: 6 GB shape, 16 GB shape+texture; `--low_vram_mode` flag — [README](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/README.md)
- Licence: "Tencent Hunyuan 3D 2.0 Community License … DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA" — [LICENSE](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/LICENSE); but source headers say "TENCENT HUNYUAN NON-COMMERCIAL LICENSE AGREEMENT" — [dehighlight_utils.py](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/hy3dgen/texgen/utils/dehighlight_utils.py) (conflict; read the LICENSE)
- Official Space `tencent/Hunyuan3D-2` running on zero-a10g (checked 2026-11-17) — [HF API](https://huggingface.co/api/spaces/tencent/Hunyuan3D-2)

**Hunyuan3D-2.1 (June 2025) / MaterialMVP**
- Replaces the RGB texture model with a PBR pipeline; Paint-v2-1 (2B, 2025-06-14); "10 GB VRAM for shape generation, 21GB for texture generation and 29GB … in total" — [README](https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2.1/main/README.md)
- `textureGenPipeline.py` has no separate delight call: the multiview model returns `multiviews_pbr["albedo"]` and `["mr"]`, super-resolved and baked separately; render 2048, texture 4096 — [textureGenPipeline.py](https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2.1/main/hy3dpaint/textureGenPipeline.py)
- Hunyuan3D-2 README pointed to "PBR material generation MaterialMVP" — [README](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/README.md); MaterialMVP = "Illumination-Invariant Material Generation via Multi-view PBR Diffusion" (arXiv 2503.10289) — [arXiv [snippet]](https://arxiv.org/html/2503.10289v2)
- Licence: Tencent Hunyuan 3D 2.1 Community License (release 13 Jun 2025), same EU/UK/South Korea exclusion — [LICENSE](https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2.1/main/LICENSE); Space running on zero-a10g — [HF API](https://huggingface.co/api/spaces/tencent/Hunyuan3D-2.1)

**Commercial generators' switches**
- Meshy Retexture API `remove_lighting` (default true): "remove highlights and shadows from the base color texture"; applied **only with `meshy-6` at 2k/4k**; `meshy-7`/`latest`/8k accept and ignore it; `meshy-6-lite`/`meshy-n1` return 400. `enable_pbr` default false; `multiview_image_urls` (1–4 views) need `meshy-7` or `meshy-n1`; `enable_original_uv` keeps UVs — [Meshy retexture docs](https://docs.meshy.ai/api/retexture.md)
- Meshy webapp guide: "Meshy 7 - Flagship … removes baked lighting automatically"; troubleshooting "Baked shadows stay in the texture" → use Meshy 7 or Meshy 6 + Remove Lighting — [Meshy AI Texturing guide](https://docs.meshy.ai/en/webapp/guides/3d-model/ai-texturing)
- Tripo `/v3/models/texture`: `delight` (default true) "Removes baked-in lighting from the reference image before texturing … Only the v3.5-20260815 texture model reads this; older texture versions ignore it"; default texture model is still `v3.0-20250812`; `bake` (default true) "Bake advanced material effects into base textures"; `pbr` default true; `texture_alignment` = `original_image` (match input colours) or `geometry`; `texture_quality` fast/standard/detailed/extreme(8K); `part_names` lets you retexture only parts from a prior segmentation task — [Tripo texture API](https://developers.tripo3d.com/en/docs/models-texture.md)

**Post-hoc texture de-lighting tools (photogrammetry heritage)**
- Unity De-Lighting Tool (Unity Labs, July 2017): free, originally on Unity's GitHub; needs "just ambient occlusion, normal and bent normal maps"; output used as albedo; "experimental"; Unity 5.6 / 2017.1 beta; original blog offline, compiled version on Asset Store — [CG Channel](https://www.cgchannel.com/2017/07/download-unity-labs-free-texture-de-lighting-tool/). The GitHub repo URL `Unity-Technologies/DeLightingTool` returned 403/404 from this container (checked 2026-11-17).
- Agisoft De-Lighter 1.5.4 (2019): free for Windows/Linux/macOS; works on textured models (not photos); removes "cast shadows and ambient occlusion"; no AO/bent-normal maps needed, but the user sketches light/shadow strokes; optimised for 8-bit JPEG textures — [CG Channel](https://www.cgchannel.com/2019/07/download-free-texture-de-lighting-tool-agisoft-de-lighter)
- Substance 3D Designer "AO Cancellation" node removes AO from albedo given a separate AO map, adjustable strength — [Adobe docs [snippet]](https://helpx.adobe.com/substance-3d-designer/substance-compositing-graphs/nodes-reference-for-substance-compositing-graphs/node-library/material-filters/scan-processing/ao-cancellation.html)

**Open-source re-texturing / material models**
- MaterialAnything (CVPR 2025, arXiv 2411.15138): MIT; generates albedo, roughness, metallic, bump for "texture-less, albedo-only, generated, and scanned objects" under "diverse lighting conditions"; needs PyTorch + PyTorch3D; example uses `--num_gpus 8` for rendering — [README](https://github.com/3DTopia/MaterialAnything); [LICENSE](https://raw.githubusercontent.com/3DTopia/MaterialAnything/main/LICENSE)
- Paint-it (text-driven PBR): MIT; developed on RTX A6000 48 GB, Python 3.8 / CUDA 11.3 — [README](https://github.com/postech-ami/Paint-it)
- TEXGen: feed-forward diffusion of **albedo** directly in UV space; testing needs a 24 GB GPU (training 40 GB+) — [README](https://github.com/CVMI-Lab/TEXGen)
- SyncMVD: text-guided multi-view texturing, MIT, Linux + NVIDIA GPU — [README](https://github.com/LIU-Yuxin/SyncMVD)
- TRELLIS (MIT): outputs radiance fields / Gaussians / meshes, GLB texture baked (default texture_size 1024) — [README](https://github.com/microsoft/TRELLIS); TRELLIS.2 (MIT, 4B): models "Base Color, Roughness, Metallic, and Opacity", shape-conditioned texture generation code released, needs ≥24 GB NVIDIA GPU (A100/H100 verified) — [README](https://github.com/microsoft/TRELLIS.2)

### Inferences
- Hunyuan's "unlit" target is a render under *even white light*, which (if rendered with occlusion) still contains ambient-occlusion-like darkening in creases; so Hunyuan delight likely removes directional shadows/highlights but not all crease AO. This matches the user's need to additionally divide by mesh AO. (Inference; paper does not say whether occlusion was disabled.)
- Running Hunyuan delight on CPU requires editing the hard-coded `torch.float16` to float32; 50 steps of an SD-1.x-size UNet (3.46 GB UNet file) at 512² on CPU will likely take minutes per image. It is only applied to the single reference image, so this is tolerable for an offline job. Note 512² resolution loses fine detail (eyes, logos) – use its output to pick palette colours, not as the final texture.
- The cheapest high-impact fix for Tripo-sourced figurines is to re-request texture with `model="v3.5-20260815"`, `delight=true`, possibly `pbr=true` and `bake=false` (so metal/roughness effects are not baked into base colour), and to re-supply the reference image as the docs recommend. `part_names` allows re-texturing only problem parts. Effect of `bake=false` on AO is undocumented.
- For Meshy, explicitly set `ai_model="meshy-6"` + `remove_lighting=true` at 2k/4k if you want the documented switch; with meshy-7 it is automatic and not controllable.
- Open-source re-texturers are impractical on the CPU box; use hosted Spaces (Hunyuan3D-2/2.1) or vendor APIs.

### Gaps
- No quantitative evaluation of how much crease AO each generator's delight leaves in the base colour.
- Unity De-Lighting Tool's licence and current repo location could not be verified (GitHub blocked/404 from container).
- MaterialAnything VRAM needs and TEXGen licence file not found.

## 3. Image-space flat-colour / posterisation preserving region semantics, and projecting flat labels back onto the mesh

### Takeaway
A CPU-friendly stack exists entirely in pip-installable packages: de-light/albedo (optional) → edge-aware flattening (OpenCV-contrib `ximgproc.l0Smooth`, guided filter, bilateral; scikit-image SLIC/felzenszwalb) → palette fitting in a perceptual space (k-means in CIELAB, or palette-based decomposition à la Tan et al. 2018) → small-region cleanup (paint-by-numbers style facet merging) → optionally SAM2 masks for semantic regions (~7–12 s/image on CPU for hiera-tiny [snippet]) → back-projection to mesh by camera-aligned rendering with face IDs, visibility, cos-weighted **label voting** (SAMesh and Hunyuan3D bake code are good templates).

### Cited Findings
- OpenCV ximgproc provides `l0Smooth` (L0-gradient-minimisation smoothing, defaults lambda=0.02, kappa=2.0), `guidedFilter`/`createGuidedFilter`; these live in opencv-contrib, not base OpenCV — [OpenCV 3.3.1 ximgproc filters [snippet]](https://docs.opencv.org/3.3.1/da/d17/group__ximgproc__filters.html); opencv-contrib-python-headless 5.0.0.93 installable on this Python 3.13 box (local `pip index versions`, 2026-11-17)
- Palette-based decomposition: Tan, Echevarria, Gingold (SIGGRAPH Asia 2018) compute a 5D RGBXY convex hull + Delaunay tessellation; decomposition into additive mixing layers per palette colour; "48 lines of Python"; code CraGL/fastLayerDecomposition with recolouring web GUI — [project page [snippet]](https://cragl.cs.gmu.edu/fastlayers/)
- Chang et al., "Palette-based Photo Recoloring", ACM TOG 34(4) (SIGGRAPH 2015): k-means-based palette extraction + palette-edit recolouring GUI; no official code located — [Princeton PIXL [snippet]](https://pixl.cs.princeton.edu/pubs/Chang_2015_PPR/index.php)
- Paint-by-numbers generators: drake7707/paintbynumbersgenerator (MIT, CLI + web demo, SVG output) — [ecosyste.ms [snippet]](https://awesome.ecosyste.ms/projects/github.com%2Fdrake7707%2Fpaintbynumbersgenerator); `strokemap` (PyPI) runs k-means on superpixel mean colours in CIELAB — [PyPI [snippet]](https://pypi.org/project/strokemap/)
- SAM2 on CPU: Colab-CPU benchmark measured `sam2.1_hiera_tiny` ≈ 7.2–11.7 s/image and large ≈ 38–47 s/image — [Zenn [snippet]](https://zenn.dev/piment/articles/ee78e816e1d05b); `sam2` 1.1.0 is pip-installable here (local check)
- SAMesh (Segment Any Mesh, arXiv 2408.13679): renders the mesh from multiple views, runs SAM2, lifts 2D masks to 3D using per-view **face IDs** and a match graph; zero-shot part segmentation; tested on Python 3.12 + CUDA 11.8 — [arXiv](https://arxiv.org/html/2408.13679v2); [README](https://raw.githubusercontent.com/gtangg12/samesh/main/README.md)
- Hunyuan3D-2 bake = template for projecting view images into UV: per-view cosine map raised to power 4 as weight, fixed view weights favouring front (1.0) and back (0.5), then UV inpainting — [pipelines.py](https://raw.githubusercontent.com/Tencent/Hunyuan3D-2/main/hy3dgen/texgen/pipelines.py); paper fills residual holes by inverse-geometric-distance weighting — [arXiv 2501.12202v3](https://arxiv.org/html/2501.12202v3)
- Bambu Studio's own OBJ-colour import clusters to Color Count 4/8/16 with a "Smooth Level"; at 4 clusters orange and white merged into one peach cluster in a Tripo test — [3DPrinting.com review](https://3dprinting.com/reviews/tripo-h3-1-review-from-image-to-3d-print/)

### Inferences
- Recommended order for segment-friendly colour on the 2D reference: (1) remove specular + shading (Section 1) or at least apply an edge-aware L0/guided smoothing on luminance-normalised colour (e.g., chroma a*b* plus clipped L*) so shading gradients don't create extra clusters; (2) fit N palette colours in CIELAB with a reduced L* weight (shadows mostly change L*, so down-weighting L* reduces "crease → black" mis-assignment; keep a dedicated dark label only if the palette genuinely has black); (3) merge facets below a minimum area (paint-by-numbers style); (4) optionally constrain labels inside SAM2 masks (majority label per mask) to give region-consistent colours.
- Projection back onto mesh: since the reference render and the Tripo mesh share a front view, render face IDs from a camera fitted to the reference (trimesh + embreex ray casting runs on CPU), assign each visible face the **mode** of the label pixels it covers (never average colours — averaging re-creates intermediate shades), weight by cos(view, normal)^k as Hunyuan does, and fill occluded/back faces by mesh-adjacency label propagation or by Tripo part segments (the existing per-segment block-colour skill). For multi-view renders of the textured mesh, render **unlit** (emissive/albedo only) so the viewer's lighting is not added on top of baked shading, then vote per face across views.
- Label voting on faces also sidesteps UV-seam bleeding because the output (3MF per-triangle paint) is face-based, not texel-based.

### Gaps
- No open-source tool found that does exactly "reference image → N filament labels → mesh faces" end-to-end; it must be assembled.
- Licence of fastLayerDecomposition not verified; Chang et al. 2015 code not found.
- No measured comparison of L0 vs guided vs bilateral smoothing for posterising stylised renders.

## 4. Ambient-occlusion division ("de-shading" by dividing out mesh AO)

### Takeaway
Dividing (or inverse-blending) a baked AO map out of a colour texture is a long-standing photogrammetry practice (Unity De-Lighting Tool takes AO + bent normals as inputs; Substance has an "AO Cancellation" node; community posts use Photoshop Divide or inverted-AO Linear-Light at ~50 %). No peer-reviewed or AI-figurine-specific write-up was found; all sources stress strength control because full division over-brightens and amplifies noise in deep creases.

### Cited Findings
- Unity De-Lighting Tool needs AO, normal and bent-normal maps (bakeable in Knald, xNormal, Substance) and outputs an albedo — [CG Channel](https://www.cgchannel.com/2017/07/download-unity-labs-free-texture-de-lighting-tool/)
- Substance Designer AO Cancellation: removes AO from base colour using a separate AO map, adjustable strength — [Adobe docs [snippet]](https://helpx.adobe.com/substance-3d-designer/substance-compositing-graphs/nodes-reference-for-substance-compositing-graphs/node-library/material-filters/scan-processing/ao-cancellation.html)
- Polycount user: lit scan ≈ albedo × light, so divide by an estimated AO/ambient term (Photoshop Divide blend) — [Polycount [snippet]](https://polycount.com/discussion/comment/2400577)
- David Miranda (12 Sep 2015): emulate capture lighting (sky hemisphere + small ground bounce), bake AO from that scene, invert it and blend over the diffuse with Linear Light at 50 % (Lighten also "seems to work"); judged visually on one stone — [dmg3d blog](https://dmg3d.blogspot.com/2015/09/removing-ambient-occlusion-from-photo.html)
- Agisoft De-Lighter removes "cast shadows and ambient occlusion" without needing AO maps, guided by user strokes — [CG Channel](https://www.cgchannel.com/2019/07/download-free-texture-de-lighting-tool-agisoft-de-lighter)
- Artists report over-removal: "higher values were too destructive"; albedo "feels a bit unreal" after aggressive shadow removal — [search summary of ArtStation/3dvf posts [snippet]](https://3dvf.com/actualite-25992-comment-supprimer-occlusion-ambiante-texture-d-un-scan-3d-avec-substance-designer-html/)
- Generators' own delight targets are "even white light" renders (Hunyuan) — [arXiv 2501.12202v3](https://arxiv.org/html/2501.12202v3)

### Inferences
- Practical form: albedo ≈ colour / (1 − s·(1 − AO))^γ with s∈[0.5,0.9], computed in **linear** RGB (not sRGB), with AO clamped to a floor (e.g., ≥0.2) so deep creases don't explode; then palette-snap. Partial strength + palette snapping is safer than full division, because the snapping step only needs crease pixels to move closer to the right palette entry than to black.
- Mesh AO should be computed with a ray distance roughly matching the generator's apparent occlusion radius (small for figurines); vertex/face AO via trimesh+embreex ray casting is CPU-feasible and maps directly to per-face labels.
- AO division cannot fix directional shadows or highlights baked from the reference image's key light; combine with an image-space delight (Section 1) or a generator-side delight (Section 2).

### Gaps
- No published quantitative study of AO-division on AI-generated textures; parameters above are engineering suggestions, not sourced numbers.

## 5. What practitioners report about getting flat/unlit textures from Tripo / Meshy / Hunyuan3D for printing

### Takeaway
Evidence is thin and mostly vendor docs plus one independent review: turning on the generator's lighting-removal switch measurably improves slicer colour clustering (Tripo H3.1 test: 3 clusters with grey rocks turned cream when off vs all 4 colours when on), but low cluster counts still merge similar colours. Meshy and Tripo now market dedicated multi-colour-print exports; no substantive Reddit threads (r/BambuLab, r/3Dprinting) on this specific problem were found.

### Cited Findings
- Tripo H3.1 review (Peter Strikwerda, 3DPrinting.com, 4 Nov 2026): Remove Lighting tooltip "reduces the impact of environmental lighting"; costs no extra credits; changes texture not mesh; ON → flat saturated colours, OFF → soft shading, duller colours; author suspects Tripo "paints the shaded side of the model into the texture"; default file "carries baked shadows" that Bambu Studio turns into muddy/merged colours; OFF → Bambu Studio found only three clusters and grey rocks came out cream; ON → all four lighthouse colours plus an extra green; Color Count 4 merged orange+white into peach; "Export Multi-Color Printable File" gave a 161 MB OBJ with per-mesh colours; one test per setting ("an indication") — [3DPrinting.com](https://3dprinting.com/reviews/tripo-h3-1-review-from-image-to-3d-print/)
- Meshy help: Meshy colours are PBR textures but Bambu Studio needs colour regions → use Print → Multi-Color Print, choose colour count (1–16, 4 recommended), export 3MF — [Meshy help [snippet]](https://help.meshy.ai/en/articles/15029992-how-to-get-multi-color-3d-prints-with-meshy); [Meshy help: missing colours in Bambu [snippet]](https://help.meshy.ai/en/articles/12141876-why-do-my-models-show-up-without-colors-or-textures-when-i-import-them-into-bambu-studio)
- Meshy docs: Remove Lighting "suits PBR pipelines"; Meshy 7 removes baked lighting automatically — [Meshy AI Texturing guide](https://docs.meshy.ai/en/webapp/guides/3d-model/ai-texturing)
- r/StableDiffusion (Apr 2025): a Hunyuan3D character printed via a ColorJet service; commenter notes printing differs from making models for animation — [Reddit mirror [snippet]](https://redlib.ssps.io/r/StableDiffusion/comments/1ju3wbh/i_successfully_3dprinted_my_illustriousgenerated/mm0eolb/?context=3)
- Neural4D: AI workflows often project the source photo's shadows/highlights onto the texture; a flat unlit base colour is required — [Neural4D [snippet]](https://www.neural4d.com/how-tos/how-to-solve-baked-shadows-and-lighting-issues); Hitem3D's AI Texture has a de-lighting intensity control, recommended higher for strongly directionally-lit references — [Hitem3D blog [snippet]](https://www.hitem3d.ai/blog/Bring-Your-3D-Models-to-Life-Introducing-Hitem3D-AI-Texture)

### Inferences
- Practitioner consensus (weak evidence): (1) start from an evenly lit, low-contrast reference render (prompt the image model for flat/ambient lighting, no rim light); (2) enable generator delight; (3) still expect to post-process into N filament labels, because slicer-side k-means clustering merges perceptually close colours and splits shaded ones.
- Since the figurine reference renders are generated in-house (GPT-image), asking the image model for "flat, evenly lit, no cast shadows, toy-like matte" lighting is the cheapest upstream de-lighting lever (untested here).

### Gaps
- Could not find substantive Reddit/forum threads specifically about unlit textures for multi-colour printing from Tripo/Meshy/Hunyuan; GitHub issues on Hunyuan delight leaving shadows were not found by search (issue tracker not directly browsable from this container).
- Meshy multi-colour print internals (palette fitting method) are undocumented.
