# Automated Multi-Color Figurine Coloring

**Status:** Working — `--palette` quantization + watertight color transfer shipping (see EXP-019)
**Last updated:** 2026-06-20

A living doc. Findings and decisions go here; experiments get logged at the bottom as we run them.

---

## Goal

Take a generated 3D model + a 2D reference image of the colors, and automatically produce a
**cleanly colored model with N filament colors** (N is a per-model parameter — often ~4, but
sometimes 3, 5, or more) such that:

1. Each segment of the model has a **solid, flat color** (no gradients).
2. The result is **not affected by lighting / baked shadows / AO**.
3. Color regions map to real parts (shirt, pants, hair, skin) — roughly how we paint manually
   in Bambu Studio today.

**N is configurable.** It's an input, not a constant — different figurines warrant different
color counts (a plain outfit might need 3, a detailed one 5–6). The pipeline should take N as a
parameter and the quantization step targets exactly N clusters.

### How we do it today (manual baseline)
In Bambu Studio we hand-paint each region with one filament: shirt one color, hair another,
skin, pants, etc. Works, but it's manual per model. We typically land around **4 colors**, but it
varies per model.

### Why the obvious options fail
- **Tripo textured model:** the texture has *far more colors than wanted* (gradients) and bakes in
  lighting/shading, so it looks bad and isn't printable as clean filament regions.
- **Plain untextured model:** no color info at all.

### Core insight (the direction we're exploring)
Split the model into **submeshes**, give each submesh **one solid color**. That mirrors the
manual workflow and is inherently lighting-independent (it's a flat material color per mesh,
not a shaded texture map).

---

## Tripo API findings

Two relevant Tripo API surfaces. **Conclusion up front: neither produces the finished
4-color print file. They're ingredients; the actual coloring logic has to be ours.**

### Texture API — `texture_model` task
Docs: https://platform.tripo3d.ai/docs/texture

Re-textures an existing model (referenced by `original_model_task_id`). Key params:

| Param | Default | Notes |
|-------|---------|-------|
| `image_prompt` / `image_url` | — | **Can drive texture from a 2D reference image** ✅ |
| `text_prompt` | — | Text guidance (mutually exclusive with image) |
| `style_image` | — | Optional style transfer (+credits) |
| `pbr` | `true` | If false, skips metallic/roughness maps → diffuse only (reacts less to lighting) |
| `texture` | `true` | Whether to generate texture at all |
| `texture_quality` | `standard` | `standard` / `detailed` (a.k.a. HD) |
| `texture_alignment` | `original_image` | `original_image` (align to input view) / `geometry` |
| `texture_seed` | random | Reproducibility |
| `part_names` | — | Texture only specific parts |

**Limitation:** Output is always a continuous UV texture (many colors, gradients), and shading/AO
is partly baked into the albedo. **There is no flat / unlit / N-color mode.** On its own this is
exactly the thing we're rejecting. Useful to us only as a *per-face color hint*, not a final asset.

### Editing API — `mesh_segmentation` + `convert_model`
Docs: https://platform.tripo3d.ai/docs/editing · Feature: https://www.tripo3d.ai/features/ai-model-segmentation

- **`mesh_segmentation(original_model_task_id, model_version="v1.0-20250506")`** — splits the model
  into **separate semantic parts** (head, torso, limbs, hair, …) with clean topology. This is the
  primitive that matches the "submesh per color" idea. ✅
- **`convert_model(original_model_task_id, format, part_names=[...], ...)`** — export (incl. `3MF`),
  optionally selecting parts. Many geom params (`quad`, `face_limit`, `flatten_bottom`,
  `pivot_to_center_bottom`, `texture_size`, `bake`, …).

**Two limitations:**
1. Segments are **body-semantic, not color-semantic**. Tripo gives "torso / legs / head," but our
   paint regions are *shirt / pants / skin / hair*. A shirt may share a part with the torso; pants
   is "legs." So segments don't cleanly map to the 4 filaments.
2. **No API parameter assigns a solid color (#hex) to a part.** Segmentation gives the geometry
   split only; coloring is still on us.

### Other relevant pieces
- `stylize_model` — LEGO / VOXEL / VORONOI / MINECRAFT stylization. Not relevant to flat coloring.
- SDK exposes `part_names` on `convert_model`, `texture_model`, `mesh_completion`, `smart_lowpoly`.
- 3MF export is supported directly from `convert_model`.

Sources: [texture](https://platform.tripo3d.ai/docs/texture) ·
[editing](https://platform.tripo3d.ai/docs/editing) ·
[OpenAPI schema](https://platform.tripo3d.ai/docs/schema) ·
[Python SDK](https://github.com/VAST-AI-Research/tripo-python-sdk) ·
[segmentation feature](https://www.tripo3d.ai/features/ai-model-segmentation)

---

## Verdict

**Automation is feasible, but the "N solid colors, no lighting" property comes from *our*
quantization step, not from Tripo.** Tripo supplies geometry, an optional color hint (texture
guided by the 2D reference), and an optional clean geometric split (segmentation). The mapping to
exactly N flat filament colors and the multi-color 3MF authoring are ours to build.

### Proposed pipeline (v0 — to be validated by experiments)
1. **Geometry** — Tripo `image_to_3d` (already in our pipeline).
2. **Color signal** — Tripo `texture_model` with `image_prompt` = the 2D color reference,
   `pbr=false`. We keep this only as a per-face color hint, not for printing.
3. **Quantize (local)** — load mesh + texture (`trimesh`), sample each face's color, k-means
   **forced to N clusters** (N = requested color count) snapped to chosen filament hexes (sampled
   from reference or specified). Few clusters ⇒ baked shading collapses away ⇒ flat solid colors.
4. **Split** — group faces by cluster into N submeshes.
5. **Export** — multi-object 3MF (one body per color) with extruder/filament mapping preset, so
   Bambu opens it with N colors already assigned (no manual painting).

> **N is a parameter throughout.** Pipeline signature is roughly
> `colorize(model, reference_image, n_colors, palette=None)`. If explicit filament hexes are given
> we snap clusters to them; otherwise we derive the N dominant colors from the reference image.

**Where Tripo fits:** texture API = color hint (step 2); segmentation API = optional cleanup so
region boundaries follow real geometry (e.g. force hair into one clean part). Steps 3–5 (the part
that guarantees "4 solids, no lighting") are ours.

### Open questions / risks to probe with experiments
- **Baked shading in albedo:** if Tripo's texture has heavy shadows, one real region can split
  into two clusters. Need a shading-robust clustering space and/or merge step. *Untested.*
- **Texture-quantization vs segmentation for region boundaries:**
  - *Texture-quantization* — boundaries follow color; risk of speckle at edges.
  - *Segmentation* — boundaries clean; risk of not matching clothing regions.
  - Likely a **hybrid** wins. Needs a bake-off.
- **3MF encoding for Bambu:** multi-object (one body per color, map filament per object) is the
  most reliable path vs. painted per-face color (mmu segmentation extension). To confirm in Bambu.
- **Do we even need Tripo's texture?** Alternative: project the 2D reference directly onto the
  mesh ourselves and skip step 2. Cheaper, fewer dependencies — worth testing.

### Suggested first prototype
Texture-quantization path on `couple-usinlove_person_1` — clean ~4-region case
(hair / black polo / grey jeans / skin), run with `n_colors=4`. Produce the colored 3MF, open in
Bambu, judge. Then re-run the same model with `n_colors=3` and `5` to see how gracefully the
quantizer degrades/refines.

---

## Experiment log

Runner: `scripts/texture_experiments.py` (base / texture / segment subcommands; caches base model
task_id in `<out>/base_models.json`). Test subject: `couple-usinlove_person_1` (regenerated from
`approved/couple-usinlove_person_1.png`; base task `5a7a9de8`). Target regions: hair, black polo,
grey jeans, skin, shoes (~5).

> **Note on previews:** Tripo's `rendered_image.webp` is a *lit scene render* — it shows lighting
> regardless of settings. To judge real flatness, extract the **albedo** texture from the GLB
> (`model.glb` → `albedo.png`) and inspect that, not the preview.

### Key findings so far
- **`texture_model` works on an untextured base** generated with `texture=False`. Output is a GLB
  with a 2048² baked albedo (+ PBR maps when `pbr=true`).
- **`pbr=false` is clearly better for us.** It removes most baked specular/highlights from the
  albedo (the `pbr=true` albedo has bright specular streaks on the jeans and lighter gradients on
  the shirt; `pbr=false` reads near-solid black shirt + more uniform jeans). Use `pbr=false`.
- **Albedo is flatter but still not flat** → quantization is still required. Confirms the doc's
  core plan: Tripo gives a usable color *hint*, we own the flatten-to-N step.
- **Color regions are separable** in the albedo (skin=orange, hair=dark brown, shirt=near-black,
  jeans=mid grey, shoes=dark) → ~5 natural clusters. Encouraging for k-means.
- **UV atlas is fragmented** (many small islands), so quantization should sample color **per
  face** (or per pixel then map to faces), not rely on a clean UV layout.

### EXP-001 — texture_model, pbr=true, standard  (2026-06-03)
- **Hypothesis:** reproduce the "bad" baseline (too many colors + baked lighting).
- **Setup:** `texture --pbr true --texture true --texture-quality standard` on base `person_1`.
- **Result:** Confirmed. Lit preview shows glossy shirt + white highlights; albedo has baked
  specular streaks on jeans and shading gradients. Files: `001_pbr_true/{model.glb,albedo.png,
  rendered_image.webp}`.
- **Decision:** baseline captured; PBR not suitable as-is.

### EXP-002 — texture_model, pbr=false, standard  (2026-06-03)
- **Hypothesis:** disabling PBR flattens the albedo (less baked lighting).
- **Setup:** same but `--pbr false`.
- **Result:** Meaningfully flatter albedo — shirt near-solid black, jeans more uniform, no specular
  streaks. Still has residual shading; not yet N flat colors. Files: `002_pbr_false/...`.
- **Decision:** **adopt `pbr=false` as the default color-hint setting.** Next: quantize this
  albedo to N colors and judge region cleanliness.

### EXP-003 — texture_alignment: geometry vs original_image (pbr=false)  (2026-06-03)
- **What it controls:** `original_image` (default) keeps the texture faithful to the input photo —
  best for surfaces the photo shows (the front); can smear/stretch on unseen surfaces.
  `geometry` fits the texture to the 3D shape instead — more uniform whole-surface coverage, less
  tied to the photo.
- **Setup:** EXP-002 = `original_image` (default); EXP-003 = `--texture-alignment geometry`. Both
  `pbr=false`, standard quality. Compared front renders + extracted albedos.
- **Result:** For this **front-facing portrait input, the two are nearly indistinguishable** — front
  renders almost identical, albedo color composition very similar. The real differentiator (back/
  side faithfulness) isn't visible from the front render or the UV atlas. Files: `003_align_geometry/`.
- **Decision:** Keep default `original_image` for now (front likeness matters most for figurines).
  Revisit `geometry` only if we see back/side artifacts — needs a **back-view render** to judge
  properly, which Tripo's preview doesn't give. TODO: render back view if this becomes a concern.

### EXP-004 — can Tripo give us a *colored* 3MF? NO  (2026-06-05)
- **Question:** the user needs 3MF (Bambu/Orca/Snapmaker), not GLB. Does `convert_model --format 3mf`
  carry the texture?
- **Setup:** `convert` subcommand → `convert_model` with `bake=True`, `texture_format=PNG` on each
  texture task. Inspected the resulting 3MF zip + XML.
- **Result:** **3MF is geometry-only.** Zip contains just `3D/3dmodel.model` (no texture image), and
  the XML has zero color tags (`basematerials`/`colorgroup`/`m:color`/`texture2d` all absent).
  trimesh sees one default color (#666666). **trimesh's own 3MF export also drops color** (sampled
  31k vertex colors fine, exported XML had no color tags). Color only ever lives in the **GLB**.
- **Decision:** **Writing color into the 3MF is 100% on us.** This validates the whole project
  premise. Built `scripts/colorize_3mf.py` (below).

### EXP-005 — quantize GLB → N-color 3MF (k-means)  (2026-06-05)
- **Tool:** `scripts/colorize_3mf.py` — samples the GLB texture to per-vertex colors, k-means to N
  (or snaps to a `--palette`), majority-votes per face, writes a 3MF via the **3MF Materials
  extension** (`<m:colorgroup>` of N colors + per-triangle `p1` index). Also: reorients Y-up→Z-up,
  scales to `--height`, sits on bed, and emits a front|back `--preview` PNG.
- **Setup:** `002_pbr_false/model.glb`, `-n 5 --height 120`.
- **Result:** Produced a valid 5-color 3MF (color confirmed in XML: 1 colorgroup, 5 colors, all
  1.43M triangles carry `p1`). **But blind RGB k-means is not semantic:**
  - merged **hair + shirt + shoes** into one near-black cluster (58% of faces),
  - **over-split skin** into two tones (orange + dark brown),
  - wasted a cluster on tiny highlights (#d0beb0, 0.4% — teeth/eyes),
  - jeans grey came out clean and distinct ✓.
  Net: a "5-color" file that reads as ~4 regions, not the desired skin/hair/shirt/jeans/shoes split.
- **Also confirmed:** k-means is **sensitive to random init** — two runs gave different palette
  allocations. Need deterministic seeding and/or guided palette.
- **Decision:** end-to-end pipeline works and gives a slicer-ready colored 3MF, but **quantization
  needs to be guided**, not blind. Files: `002_pbr_false/colored_n5.3mf` + `_preview.png`.

### EXP-006 — does generating *with texture* yield a colored 3MF? STILL NO  (2026-06-05)
- **Question (user):** EXP-004 converted a *texture_model* task. What if the model is **generated**
  with `texture=True, pbr=True` and then converted — does that 3MF keep color?
- **Setup:** `base --texture true --pbr true` (task `b710434f`) → `convert --format 3mf` → inspect.
- **Result:** **Still geometry-only.** Zip = just `3D/3dmodel.model` (no texture image); XML has zero
  `texture2d`/`colorgroup`/`m:color`/`basematerials`/`uv` tags. Identical to EXP-004.
- **Conclusion:** **Tripo's 3MF exporter strips all color/texture regardless of how the model was
  made.** Color survives only in textured formats (GLB/OBJ/FBX). There is **no Tripo shortcut to a
  colored 3MF** — the GLB→3MF color baking (`colorize_3mf.py`) is mandatory, not optional.
- **Aside:** even a hypothetical textured 3MF wouldn't help printing much — slicers drive multicolor
  from per-object/per-face colors or painted regions, **not** from UV textures. So quantizing to
  flat per-face colors (our approach) is the right target anyway, not preserving the UV texture.
- Files: `010_textured_gen/model.3mf`.

### EXP-007 — colored 3MF *is* possible (texture2d embedding) — correcting EXP-004/006  (2026-06-05)
- **Trigger:** user confirmed Tripo **Studio** downloads a colored 3MF when generated with texture.
  So "Tripo can't give a colored 3MF" (EXP-004/006) was the wrong conclusion.
- **What's actually true:** Tripo's **`convert_model` API** to 3MF strips color (re-confirmed), and
  trimesh's 3MF export does too. But **Tripo Studio embeds the GLB's UV texture into the 3MF** via
  the 3MF Materials extension (`<m:texture2d>` + `<m:texture2dgroup>` + per-triangle UV indices).
  That's a *packaging* step, not a Tripo-API capability. "Conversion is the wrong step" — correct.
- **Solution built:** `scripts/glb_to_textured_3mf.py` — takes the textured GLB (`pbr_model`) and
  writes a textured 3MF itself: embeds `texture.png`, writes `texture2d`/`texture2dgroup` with
  per-vertex UVs (v flipped glTF→3MF), references them per triangle. Also reorients Z-up + scales.
- **Result:** `010_textured_gen/textured_color.3mf` — valid: 1 texture2d, 734k tex2coords, 1.43M
  triangles with UV refs, embedded 2048² PNG. Equivalent to Studio's colored 3MF. *(Render not yet
  verified in a slicer — see below.)*
- **BUT** this is the **full UV texture** = many colors + baked shading — i.e. the *original
  "bad for printing" artifact*. It's great for visualization / a viewer, and some slicers can
  auto-reduce it, but it is **not** the clean N-filament target.

### Two kinds of colored 3MF — pick by purpose
| Script | Encoding | Colors | Use when |
|--------|----------|--------|----------|
| `glb_to_textured_3mf.py` | `texture2d` (UV texture) | full texture (100s) | match Studio; visualize; slicer that auto-reduces |
| `colorize_3mf.py` | `colorgroup` (per-triangle) | exactly N flat | **clean multi-filament printing** (project goal) |

Both are now ours to produce from the GLB. The printing goal still wants the **quantized** one;
the texture2d one mainly answers "how does Studio do it."

### EXP-008 — what color encoding does Bambu actually read?  (2026-06-05)
- **Observation (user):** `textured_color.3mf` (texture2d) opens in Bambu Studio with **NO color**.
- **Research:** Bambu Studio supports **vertex coloring and face coloring on import, but NOT UV
  texture mapping** ([BambuStudio #1892](https://github.com/bambulab/BambuStudio/issues/1892),
  [#4422](https://github.com/bambulab/BambuStudio/issues/4422)). So `texture2d` is a **dead end for
  Bambu** (and explains why a Studio textured 3MF likely wouldn't color there either). Bambu 2.5+ has
  a "Standard 3MF Color Parsing" that maps standard-3MF colors → AMS filament slots; OBJ+MTL face
  color is called out as the **most reliable** import.
- **Likely earlier mistake:** `colored_n5.3mf` used `<m:colorgroup>` (arbitrary *display* colors).
  The element slicers bind to **filament slots** is core-3MF **`<basematerials>`** ("these are the
  print materials"). Switched the default encoding to `basematerials`.
- **Action:** `colorize_3mf.py` now supports `--encoding basematerials|colorgroup` (default
  basematerials) and `--obj` (writes OBJ+MTL, N materials grouped by `usemtl`). Generated both from
  the textured GLB: `010_textured_gen/colored_n5_basemat.{3mf,obj,mtl}`.
- **Status:** awaiting Bambu test of the two new encodings (3MF basematerials vs OBJ+MTL).

### Format scorecard (Bambu Studio) — VERIFIED in-app by user (2026-06-05)
| File | Encoding | Bambu result |
|------|----------|--------------|
| `textured_color.3mf` | `texture2d` (UV texture) | ❌ no color (Bambu can't texture-map) |
| `colored_n5.3mf` | `m:colorgroup` | ✅ **shows color** (softer borders) |
| `colored_n5_basemat.3mf` | `basematerials` | ❌ **no color** (surprise — Bambu ignores it) |
| `colored_n5_basemat.obj` | OBJ+MTL face color | ✅ **best** — color + crispest borders |

**Format decision: OBJ+MTL is primary** (works + cleanest borders). `colorgroup` 3MF is the 3MF
fallback when a `.3mf` is required. `basematerials` is **out** (no color in Bambu). `colorize_3mf.py`
defaults reverted: `--encoding colorgroup`, and `--obj` is the recommended output.

### EXP-009 — quantization quality: RGB vs shading-robust Lab  (2026-06-05)
- **Problem (user):** colors "not very good — skin has darker colors in areas without light"
  (baked shading splits one region into multiple clusters).
- **Setup:** pbr=false GLB, n=5. A = RGB clustering; B = Lab with `--luma-weight 0.4` (downweights
  lightness so lit/shadow skin cluster together). New `colorize_3mf.py` decouples the clustering
  metric (feature space) from the displayed color (true cluster-mean RGB).
- **Result:** B reduced the skin-shadow split slightly (shadow-skin cluster 6.6%→5.2%) **but merged
  more of the grey jeans into black** (jeans 18.6%→12.3%). Net: a wash — helping skin hurts
  dark-region separation.
- **Conclusion:** **blind quantization has a ceiling.** It can't simultaneously (a) keep a
  high-tonal-range region (skin) together and (b) separate distinct *parts* that share a color
  (hair/shirt/shoes, all near-black). No clustering space fixes both at once.

### → Next unlock: segmentation-guided coloring (the original "submesh" idea)
The robust fix is to stop relying on color alone and bring in **geometry**:
- Use Tripo **`mesh_segmentation`** to split into parts (hair, torso/shirt, legs/jeans, etc.).
- Assign **each part one solid color** sampled from the texture / 2D reference.
- This fixes BOTH failure modes: a part = one flat color (shading can't split it), and hair vs
  shirt vs shoes are separate parts even though similarly dark.
This is exactly the user's original instinct (color per submesh). EXP-009 is the evidence it's
needed. **Try `mesh_segmentation` next** and see if part granularity matches the paint regions.

### EXP-010 — segment-based coloring: THE breakthrough  (2026-06-05)
- **Setup:** `mesh_segmentation` on base `person_1` → **11 parts** (GLB sub-meshes). New
  `scripts/segment_colorize.py`: samples each part's dominant color from the textured GLB
  (`002_pbr_false`, via nearest-vertex KD-tree median), groups the 11 parts into N filament colors
  by size-weighted k-means, merges parts into one mesh with per-face filament labels, exports
  OBJ+MTL / colorgroup-3MF + preview.
- **Segmentation quality:** parts map cleanly to real regions — **hair is separate from face skin**
  (the exact thing blind quant couldn't do), plus distinct shirt / jeans / shoes / ears / hands /
  eyes. Per-part dominant colors are clean: face `#a54717`, hair `#1f1611`, shirt `#212018`, jeans
  `#403e3a`, shoes `#14130f`.
- **Result:** the colored preview is **dramatically cleaner** than blind quant — **skin is uniform
  (no shadow-split)**, every region a flat solid color, crisp part boundaries. Solves the EXP-009
  complaint. Files: `031_segment_colored/person1_seg_n5.{obj,mtl,3mf}` + preview.
- **Minor warts:** (1) tiny **hands** part got its own filament (`#7c2707`) instead of merging into
  skin — wastes a slot; (2) the two near-blacks (hair+shoes vs shirt+eyes) split into 2 filaments
  (fine, or merge to free a slot). Both are k-means-grouping nits, easily tuned (force skin parts
  together / pick N / hand-map parts→filament).

### ✅ Working pipeline (v1)
```
image_to_model (texture=false)            # geometry  -> base task
  ├─ texture_model (pbr=false)            # color hint -> textured GLB
  └─ mesh_segmentation                    # parts      -> segmented GLB
segment_colorize.py(segmented, textured)  # per-part color -> N filaments
  -> OBJ+MTL (primary) / colorgroup 3MF   # slicer-ready, flat colors, no shading
```
Color count N is a parameter; segmentation removes both blind-quant failure modes (shading splits,
same-color parts). **Next: verify `person1_seg_n5.obj` in Bambu; tune part→filament grouping.**

### EXP-011 — semantic 3-color (hair / skin / clothes)  (2026-06-05)
- **Why:** user feedback on EXP-010's k-means grouping — beard uncolored (got skin), hands black,
  neck too red. For 3 colors, k-means-by-color fails (hair≈clothes≈near-black). Need **semantic**
  classification: skin by color, then hair-vs-clothes by **height** (head region vs body).
- **Identified all 11 parts** (rendered `parts_grid.png`): 0/10=ears, 4=face (skin); 1/2=eyes,
  8=hair, 5=beard (hair); 3/9=shoes, 6=jeans, 7=torso **with arms+hands fused in** (clothes).
- **Tool:** `segment_colorize.py --scheme semantic3` — `is_skin()` (warm + bright R) → skin;
  else height > `--head-line` (0.45) → hair, else clothes. Configurable `--skin-min-r` excludes
  facial hair from skin.
- **Result:** clean 3-color — hair `#1f1610`, skin `#a64413`, clothes `#2b2923`. **Beard now hair,
  skin uniform (no shadow split), shirt+jeans+shoes one clothes color** (as requested). Files:
  `032_semantic3/person1_hsc.{obj,mtl,3mf}`.
- **Known limitations (honest):**
  1. **Hands stay clothes-colored** — segmentation fused hands+forearms into the shirt/torso part
     (#7), so they can't get skin color from geometry alone. Fix options: a per-face skin-color
     *override* within clothes parts (rescues hands, small risk), or finer segmentation. Not done yet.
  2. **Clothes = 1 color** merges black shirt + grey jeans (the 3-color ask). Bump to 4 (split
     jeans) trivially later.
  3. `--head-line`/`--skin-min-r` defaults are tuned on this model; may need per-figurine nudging
     until we make them adaptive.

### EXP-012 — beard/eyebrow fix + cheap iteration cycle  (2026-06-06)
- **Two problems:** (1) beard & eyebrows still uncolored — they're **texture-only detail baked into
  the face mesh**, no separate geometry, so segmentation can't catch them; (2) the splat preview was
  too speckly to even verify fixes.
- **Cheap cycle:** everything after the segmented + textured GLBs is **local, no API** — one
  `segment_colorize.py` run is **~10s**. Rebuilt `render_preview` (3×3 disk-splat + occlusion +
  supersample, **front-face | side** views) so beard/brows are clearly visible. Iterate freely.
- **Fix:** within-skin override — faces inside a SKIN part whose actual texture color is very dark
  (`max(rgb) < --hair-dark-max`, default 95) get reassigned to **hair**. Catches beard, mustache,
  eyebrows; doesn't touch shaded skin (still warm/brighter). Recolored 64.8k faces here.
- **Result:** clean 3-color with **eyebrows + mustache + beard now hair**, skin uniform, clothes
  dark. Files: `033_semantic3_override/person1_hsc.{obj,mtl,3mf}` + preview.
- **Still open:** hands remain clothes-colored (fused into the shirt/torso part). Same trick in
  reverse (clothes→skin for skin-colored faces) would rescue bare forearms/hands — not done yet;
  they're mostly hidden in-pocket here.

### Current best recipe (per person)
```
base = image_to_model(approved.png, texture=false)
texture_model(base, pbr=false)      -> textured GLB   (color hint, flatter)
mesh_segmentation(base)             -> segmented GLB   (parts)
segment_colorize.py --scheme semantic3 --obj           # hair/skin/clothes + beard override
```
Tunables: `--head-line` (hair/clothes height split), `--skin-min-r`, `--hair-dark-max`.

### EXP-013 — re-segment a part? (user idea) — shatters  (2026-06-06)
- **Idea (user):** beard/brows have real relief, so re-segment the head part on its own to split
  them out. (Correct that they have geometry — my "flat" claim was wrong.)
- **New capability built:** Tripo `import_model` — STS upload (`POST /upload/sts/token` → boto3 to
  the returned bucket → `{"type":"import_model","file":{"object":{bucket,key}}}`), and
  `mesh_segmentation` accepts the imported task_id. So **we can now segment any local mesh.**
  (`/upload` is images-only / size-limited; STS handles models. Decimate first — used
  `fast-simplification` to 60k faces.)
- **Result:** segmenting the isolated head → **205 confetti fragments**, not clean beard/brow/eye
  parts. Tripo's segmentation is trained on whole objects; a lone head over-fragments. **Dead end
  for facial features.** Files: `040_face_reseg/`.

### EXP-014 — clean beard/brow override via connected-components  (2026-06-06)
- **Real problem with the override:** the `<hair_dark_max` test grabs shadowed skin (nostrils, eye
  sockets, lip line) → blotchy face. Morphological erode/close barely helped (dark faces are
  contiguous, not speckle).
- **Fix:** facial hair forms a few **large** connected dark masses; shadows are **many small** ones.
  Keep only dark connected-components ≥ `--override-min-faces` (default **400**); drop the rest.
  (scipy `connected_components` over candidate-face adjacency.)
- **Result:** dropped ~11k shadow specks, kept brows/mustache/soul-patch full and clean. 400 is the
  sweet spot (800 starts eroding the brows). Files: `042_cc_override/mf400.*`.
- **Net:** beard/brows colored cleanly **without** Tripo re-segmentation. Current best for the guy.

### EXP-015 — the girl (person_2): 3-color fails, semantic4 works  (2026-06-06)
- **3-color (semantic3) fails for her:** her **pink top is a warm color → classified as skin**
  (skin-colored torso), and even fixed, one "clothes" color would muddily merge pink top + black
  pants. The guy worked only because all his clothing was dark.
- **k-means N=4/5 also bad:** the shaded pink top fragments into 2–3 shades while hair+pants+shoes
  collapse to one black — wastes slots, over-merges.
- **Fix — `--scheme semantic4`** (hair/skin/top/bottom): warm parts split by height (face=skin
  above `--face-line`, top below); dark parts split by height (hair/bottom). With `--skin-min-r 105`
  to include her darker-pink top. Clean result: dark hair, skin face, pink top, black bottoms.
  Files: `052_p2_colored/person2_sem4.{obj,mtl,3mf}`.
- **Takeaway:** color count should match the subject — monochrome outfit → semantic3, two-tone
  outfit → semantic4. Same machinery, one more height split.

### EXP-017 — Studio segmentation >> API segmentation  (2026-06-06)
- **Observation (user):** Tripo **Studio** WebUI segments the girl into **5 clean semantic parts**
  (head, top, pants, 2 hands), crisp boundaries — vs our API's 15–17 fragments.
- **Tested:** API `mesh_segmentation` with default model_version (not pinned) → still **15 parts**.
  So it's not the model_version.
- **Why:** Studio's UI exposes **granularity + Merge + Fill Parts** controls (visible in its
  toolbar) that consolidate raw fragments into clean parts. The **public API exposes none of these**
  (confirmed: SDK/Runware/3daistudio list no granularity or merge param). API runs one fixed fine
  granularity. **We cannot replicate Studio's clean segmentation from code.**
- **Workaround (good):** segment in Studio → **Export** segmented GLB/OBJ (parts kept as sub-meshes)
  → feed to `segment_colorize.py` (our `import_model` path already accepts any segmented mesh). Gets
  Studio-quality boundaries + our automated coloring.
- **Caveat:** Studio's coarse 5-part split merges **face+hair into one head part** → would lose
  hair/skin color separation. Bump Studio granularity to split hair from face for the ideal input.

### EXP-018 — API mesh_completion ("Fill Parts") — doesn't give solids  (2026-06-06)
- **Why test:** user found Studio's exported parts are **watertight solids** = easy to paint; our
  segmentation parts are **open shells** → Bambu treats them as non-solid → "weird behaviour,"
  hard to paint. `mesh_completion` (HoloPart) is supposed to close parts into solids.
- **Test:** `mesh_completion` (task type confirmed) on girl's segmentation (191b43a4). Ran ~7min.
- **Result:** **still 17 parts, still NOT watertight** (after weld, part_0 open edges 371→1386).
  It added some geometry but did not close the parts into solids. API completion ≠ Studio Fill Parts.
- **Conclusion:** Studio's clean+solid 5-part export comes from its UI pipeline
  (granularity + Merge + Fill Parts + export processing) that the raw API tasks don't reproduce.
  **Recommendation: use Studio as the segmentation source** (Segment → Fill Parts → Export GLB),
  then optionally run `segment_colorize.py` on that export for automated per-part filament colors.
  Our open-shell API segmentation is the root cause of the hard-to-paint behaviour.

### ⚠️ Unverified link
- **Does Bambu/Orca/Snapmaker actually read `<m:colorgroup>` per-triangle colors and map them to
  filaments?** The 3MF is spec-compliant, but slicer support for this encoding is **not yet
  confirmed in the real app.** If not, fall back to **multi-object 3MF** (one body per color) —
  universally supported. *Needs a human to open `colored_n5.3mf` in the slicer.*

### New scripts
- `scripts/texture_experiments.py` — `base` / `texture` / `segment` / `convert` subcommands.
- `scripts/colorize_3mf.py` — GLB → N-color 3MF (k-means or `--palette`), with preview + reorient.

### Ideas not yet run
- **Guided palette:** `--palette` with hand-picked filament hexes (skin/hair/shirt/jeans/shoes) so
  clusters map to real regions instead of collapsing by color similarity.
- **Segmentation-guided coloring (most promising):** `mesh_segmentation` → assign each *part* one
  solid color sampled from the texture/2D reference. Fixes the hair≈shirt≈shoes merge because parts
  are split by geometry, not color.
- **Multi-object 3MF export mode** in `colorize_3mf.py` as a slicer-safe fallback.
- `texture_quality=detailed`; back-view render for `original_image` vs `geometry`.
- Quantize in a perceptual space (Lab) instead of RGB; deterministic k-means seeding.

### EXP-019 — Watertight colored 3MF: textured GLB color + convert_model geometry  (2026-06-20)
- **Problem:** colored figurines (`colorize_3mf.py` on the Tripo textured GLB) opened in the slicer
  as **non-watertight**, while plain uncolored prints from `image_to_3d.py` were watertight. Why?
- **Root cause (diagnosed):** the two paths get geometry from different Tripo steps.
  - Plain pipeline: `image_to_model(texture=False)` → **`convert_model(format=3mf)`**. That convert
    is a server-side remesh/repair → single watertight manifold.
  - Coloring used the textured `output.model` GLB directly = Tripo's **raw, pre-repair** mesh:
    measured **170 disconnected shells, ~47k open edges, `fill_holes()` fails**. `colorize_3mf.py`
    only reassigns colors, so it passed that broken geometry straight through. Coloring never broke
    anything — the textured branch just **skipped the repair step** the plain branch gets for free.
- **Fix (shipped in `colorize_3mf.py`):** get geometry and color from the *same* model task and fuse.
  1. `image_to_model(texture=True)` — **save the `model_task_id`**.
  2. Download textured GLB (`output.model`) = **color source** (messy geometry).
  3. `convert_model(format=3mf, texture=True, original_model_task_id=…)` = **watertight geometry**,
     but arrives flat-gray `#666` (color does NOT survive into 3MF — zip has no texture).
  4. `colorize_3mf.py <textured.glb> --geometry <convert.3mf> -o out.3mf …` — new `--geometry` flag
     outputs the watertight mesh and transfers GLB texture colors onto it by **nearest-vertex
     KDTree**. After identical normalization both meshes share the exact coord frame
     (**measured NN distance ≈ 0.000mm**), so the transfer is lossless.
- **Results:** dad (5-color) and suckit2 (3-color) → strictly watertight, single body. suckit1 →
  single body, 0 open edges, but **3 non-manifold edges / 2.2M** (inherent to that generated mesh;
  re-running convert is deterministic, gives the same). That's cosmetically irrelevant — Bambu
  auto-repairs on import; a voxel remesh to fix 3 edges would soften all detail, so don't.
- **Gotchas:**
  - `convert_model` format must be `3mf` — `format:glb` returns **HTTP 400**.
  - Verify watertightness with `trimesh.load(..., process=False)` (as-authored). Reloading with
    `process=True` re-welds a few vertices and **falsely** reports non-watertight.
  - Dark clothing → force palette + `--color-space lab --luma-weight 0.3` so near-neutral shaded
    fabric snaps to black instead of speckling skin-tone (EXP earlier).
- **Decision / next:** this is the standard path for any colored figurine — never colorize the raw
  textured GLB alone. Could fold steps 1–3 into a `scripts/` helper (currently done via inline Tripo
  calls); the recipe above is reproducible as-is.

### EXP-020 — the `--preview` speckle is a renderer lie; the mesh defects behind it don't matter  (2026-08-05)
- **Context:** Goga ji set (krishna 120mm/5c, horse 100mm/4c, snake 70mm/3c) via the EXP-019 path.
- **The false alarm:** every horse variant's `--preview` showed heavy salt-and-pepper on the muzzle
  and chest. Burned several colorize runs chasing it with `--dark-below` 15/20/28 and
  `--color-space lab` at luma 0.35/1.0 — **the speckle never moved**, and the side view in the same
  PNG was always clean. Tell-tale: front view speckled, side view clean, on the same mesh.
  `render_preview`'s 3×3 disk-splat has an imperfect occlusion test, so on front-facing surfaces
  occluded back geometry punches through. **The models were correct the whole time.**
  → **Verify color with a real z-buffer render, not `--preview`.** Parse the shipped 3MF's
  per-triangle `p1` indices against its `<m:colorgroup>` and rasterize with a depth test; that shows
  exactly what the slicer will show. Worth folding into `scripts/` as `render_3mf.py`.
- **Real bug 1 — `colorize_3mf.py` was breaking watertight meshes it was handed.** The `--geometry`
  branch loaded the convert_model 3MF with `process=True`, which re-welds near-duplicate vertices.
  On krishna that weld (737893 → 737892 verts, face count unchanged) collapsed 6 valence-2 edges
  into **3 non-manifold (valence-4) edges** out of 2.21M — clean mesh in, non-manifold mesh out,
  silently, because the welded mesh is what gets written. EXP-019 noted `process=True` *reports*
  false non-watertightness — it also *causes* a (small) real defect here. **Fixed: `process=False`.**
  Hit 1 of the 3 models; horse and snake were byte-identical either way.
  ⚠️ **Severity: cosmetic.** This is the exact defect class EXP-019 already ruled not worth chasing
  ("3 non-manifold edges / 2.2M … Bambu auto-repairs on import"). Worth the one-word fix because
  it's free and we shouldn't degrade a clean mesh — **not** worth a debugging session.
- **Bug 2 — one genuine hole in Tripo's horse mesh, and it did not matter either.** 6 boundary
  edges / 2.17M forming a single 6-vertex loop, measuring **0.17 × 0.008 × 0.003 mm at print
  scale** — orders of magnitude under a 0.4mm nozzle. `trimesh.fill_holes()` silently declines it
  (two of the six vertices are exact coordinate duplicates). Patched with a manual triangle fan +
  `fix_winding`/`fix_normals` → 4 triangles, watertight, kept as `horse_geometry_sealed.3mf`.
  Detail-preserving and ~free, but **optional** — the unsealed mesh would have printed identically.
- **Standing conclusion: Tripo's `convert_model` geometry is good enough; stop auditing it.**
  Across these 3 models Tripo delivered 2 strictly watertight meshes and 1 with a sub-nozzle sliver.
  Don't spend time on mesh integrity unless the slicer actually complains or a print actually fails.
  Spend it on the **color** pass, which is where every real defect in this pipeline has come from.
- **Palette tuning that did matter (both confirmed on the z-buffer render):**
  - *Snake:* warm-shadowed white belly snapped to gold in RGB (gold 11.9% of faces, smeared over
    the bottom coil). `--color-space lab --luma-weight 0.35` → gold 6.5%, confined to the necklace.
  - *Horse:* white body + black mane is **bimodal in Lab L** (black L=10–20, white L=75–90, only
    ~4% in the valley between). Histogram the neutral-chroma verts to find the gap, then set
    `--dark-below` inside it (20 here). Note plain `--dark-below` still snaps the leftover greys in
    **RGB**, where mid-grey is nearer `#C4201E` than white — at `--dark-below 15` the whole mane
    went *red*. Pair the floor with `--color-space lab` so the greys resolve to white.
- **Decision / next:** `--dark-below` should probably imply Lab, or warn when it doesn't. And
  `--geometry` should assert the output is no less watertight than the input it was given.

### EXP-021 — split a painted model without repainting; `quick_cap` beats PyMeshFix  (2026-08-07)
- **Problem:** a finished, hand-cleaned figurine (juthikasis sister) needed **5 filaments** but the
  printer has 4 slots. Splitting it into parts should mean no single part needs the whole palette —
  but only if the paint survives the split.
- **Why the paint survives (measured, not assumed):**
  1. Bambu writes `paint_color` as a per-triangle attribute on the **unmodified** mesh —
     1,483,703 attributes on 1,483,703 faces, 741,834 verts, identical to the source. Colour is
     therefore just an array indexed by face.
  2. Tripo `mesh_segmentation` is a **lossless partition, not a resample**: face count −0.03%,
     and vertex count *rises* (boundary verts duplicated into both parts). On the cached
     couple-usinlove run, **99.90% of part vertices land within 1e-6 of an original vertex**.
  3. So mapping part faces → source faces by centroid KDTree transfers paint at
     **0.000mm mean and max**. 97.07% of the capped output inherits verbatim; the other 2.93% is
     new interior cap geometry and takes its nearest neighbour's code.
- **`quick_cap` vs PyMeshFix (head-to-head, same 4 parts, drift = original-surface displacement):**

  | part | quick_cap | PyMeshFix |
  |---|---|---|
  | head 900k | watertight, 1 body, **0.0007mm** | watertight, 0.0002mm |
  | skirt 496k | watertight, 1 body, **0.0037mm** | watertight, 0.0117mm |
  | torso 66k | watertight, **0.0016mm** | **5.6mm — deleted 8,371 faces** |
  | hem 19k | watertight, 1 body, **0.029mm** | **7.5mm** |

  quick_cap closed all four in 35s. MeshFix only competes on the large parts and **mangles small
  ones**, so it drops to fallback. This supersedes the "PyMeshFix is the right tool" guidance.
- **`completion_mode` matters — EXP-018 is still right about the other mode.** v3
  `/mesh/complete` now takes `completion_mode`; the default `ai_completion` is the one EXP-018
  measured (resamples the whole surface — 0% of vertices preserved, ~1.7% of height mean drift —
  and still doesn't close the parts). `quick_cap` is a separate code path: seals boundaries with
  no AI generation. Always pass it explicitly.
- **v3 also unblocks the input side:** `POST /v3/mesh/segment` accepts your own uploaded mesh
  (`file_token` or URL, GLB/OBJ/STL ≤150MB), so you can segment a mesh you edited locally. v2
  needed a prior Tripo `task_id`. Note **v2 retires 2026-11-01** (no updates after 10-01) and
  every other script here is still on `api.tripo3d.ai/v2/openapi`.
- **Result:** head = black/skin/cream/magenta, body = pink/magenta/skin/cream. Union is 5,
  **neither part exceeds 4**. Both watertight, 0 open edges. Tool: `scripts/split_painted_3mf.py`,
  skill `figurine-split`.
- **Gotchas that cost real time:**
  - `scene.geometry` hands back parts in **local** frames; you must apply `scene.graph[node]`
    transforms or every part sits at the origin and the colour match is garbage.
  - Compute the part-space→mm affine **once globally**. Doing it per part re-centres and re-scales
    each part to the full model — every part then reports the whole z range and ~17mm match error.
  - **Don't infer paint code → colour from area rank.** The user had swapped gold for cream and
    repainted; rank-matching produced a gold skirt. Read `filament_colour` from
    `Metadata/project_settings.config`. Codes map monotonically: `4`,`8`,`0C`,`1C`,`2C` → slots 1..5.
  - Segmentation boundaries leave strays (5,810 black hair faces landed on the body). Sweep any
    sub-1% colour into its nearest neighbour or the part still demands that filament.
  - A single horizontal cut plane cannot solve this — her hair hangs to waist height, so every
    plane leaves 5 colours on one side. It has to be a semantic split.

### EXP-022 — why shading bleeds into black on humans but not animals; block colouring  (2026-08-12)

- **Observation (user):** human figurines consistently get dark creases turned **black** (docsurgeon:
  under the chin, armpits, inner legs, trouser folds), while the dogs/cats/horse/snake come out
  "pixel perfect". Asked why, and how to mitigate.

- **Mechanism.** Black in a palette is a **nearest-neighbour attractor**. Tripo bakes ambient
  occlusion into the texture, and shading is *multiplicative* — it scales RGB toward zero, dragging
  down **both** lightness and chroma. Every shaded pixel therefore travels along a ray that
  terminates exactly at the black centroid. Whether it defects depends on how much chroma survives.

  Measured over vertices with Lab L<30:

  | model | median chroma when dark | dark px that are *shaded colour*, not real black | outcome |
  |---|---|---|---|
  | horse | 1.2 | 2.1% | clean |
  | snake | 0.0 | 0.9% | clean |
  | krishna (**human**) | 29.9 | 65.7% | clean anyway |
  | docsurgeon | **8.3** | 51.5% | **bleeds** |

- **So it is not human-vs-animal.** Krishna is human and fine. Four real factors:
  1. **Base-colour chroma.** Krishna's `#1B3C9E`/`#B81E1E` are saturated, so shaded navy is still
     emphatically navy and hue decides. Teal scrubs (chroma ~25) and skin desaturate to chroma 8 in
     shadow — effectively grey, and dark grey's nearest neighbour is black. Real clothing (scrubs,
     denim, khaki, grey suits) sits in this danger zone; mythological dress and animal coats don't.
  2. **Self-occlusion.** Folded arms, chin over neck, cap brim, inner legs. A horse's barrel and a
     snake's coil are convex. 23.9% of docsurgeon's surface is below L=40.
  3. **Palette luminance gaps.** docsurgeon: black L=9.3 → next colour (teal) L=52.6, a **43-point
     empty band**; anything shaded into it below the midpoint defects. Krishna's palette L values
     are 5.0/29.2/39.9/69.7/78.4 — biggest gap 24, so shaded pixels land on a real colour.
  4. **The horse also had a flag the doctor didn't** — `--dark-below 20`, which at
     `colorize_3mf.py:316` *removes black from the candidate set* and gates it behind a hard
     luminance test. Structural immunity, not luck.

- **`--luma-weight` cannot fix this.** Simulated on docsurgeon's GLB: RGB → 14.5% black; Lab luma
  0.35 → **14.7%**, marginally *worse*. Structural: black is at chroma 0 and shading drives chroma
  to 0, so down-weighting luma helps black capture desaturated shadows. Luma-weight is for the
  *other* bug (grey hair snapping to teal — see below). Do not reach for it here.

- **Two things that do work:**
  - `--dark-below 18` (valley of the low-chroma L histogram; real-black mode at L 10–15, shading
    bump at 20–30) → black 14.7% → **4.7%**, contamination 62% → **9.2%**, i.e. the horse's number.
  - **`--black-chroma 8`** (in **both** `colorize_3mf.py` and `segment_paint_3mf.py`): a vertex may
    take the darkest slot only if its Lab chroma is below the gate. This is the discriminator the
    table above proves. Pulled 9.1% of vertices out of black with **no Tripo call**, landing at
    black 5.4% / white 10.4% — i.e. it reproduces the 40-credit segmentation hybrid (5.3% / 10.1%)
    for free. In `colorize_3mf.py` it composes with `--dark-below` (black must then be both dark
    *and* achromatic: 4.3%); `--dark-below 18` alone gives 4.7%, unchanged from before the port.

- **Preflight rule:** sort the palette by Lab L. If the gap between black and the next-lowest
  exceeds ~30, expect bleed — gate it. Muted mid-tone garments make it near-certain.

#### Block colouring — decide colour per part, not per vertex

- **Setup (user's idea):** segment into many parts, give each one flat colour, recombine. Built
  `scripts/segment_paint_3mf.py`. **Improvement on the plan: never split at all** — use the
  segmentation purely as a *face label map* onto the untouched watertight mesh. Nothing to
  recombine, mesh stays watertight/1-body, and `mesh_completion` is not needed (**saves 30 credits
  and a task**). Costs: `mesh_segmentation` 40 credits / ~50 s; `image_to_model` 30; `convert_model`
  5; `mesh_completion` 30 (not used here).
- **Segmentation quality (v3, `granularity=detailed`, 1.44M tris):** 19 parts, total part faces
  within **0.008%** of the source — the lossless partition EXP-021 measured. Separate parts for
  glasses, ears, nose, eyebrows and each croc.
- **Results (docsurgeon, 150 mm, 4 filaments):**

  | | black | white | teal | skin |
  |---|---|---|---|---|
  | per-vertex (`colorize_3mf`) | **14.6%** | 8.5% | 50.1% | 26.8% |
  | strict block (`--mixed-frac 0`) | 3.9% | **2.5%** | 60.5% | 33.1% |
  | hybrid (`--mixed-frac 0.95 --black-chroma 8`) | **5.3%** | **10.1%** | 57.5% | 27.1% |

- **The limit (reproduces EXP-012):** strict block **drops any feature with no geometry of its own**.
  The cranium and face came back as one part with the hair fused in, so flat-filling put white at
  2.5%, all of it at z/H 0.5–0.8 (the collar mask) — hair, moustache and brows went skin. No
  per-part override can rescue it; only the per-vertex fallback can. Same for logos and flag text.
- **⚠ The trap that silently fakes success:** Tripo returns parts renormalized into a **unit box**
  while the mesh is in mm. Without one global affine (`make_transform`) every part collapses onto a
  handful of faces near the origin and the tool emits *exactly the per-vertex result*. Tell-tales:
  `100.00% unclaimed` and `0.0% of faces differ`. Cost us one full 40-credit run before it was spotted.
- **Also obsolete now:** EXP-017's "the API exposes no granularity control" was the **v2** API. v3
  `/mesh/segment` takes `segmentation_granularity` = simple | balanced | detailed.
- **Decision:** shipped as skill `figurine-blockcolor`. Hybrid is the default recommendation. Try
  `--black-chroma` alone first — it did most of the work for free; spend the 40 credits when flat
  geometric boundaries are also wanted.
- **Not tried:** projection painting from the approved PNG. Unlikely to help the bleed (the source
  render is itself shaded) and adds occlusion + silhouette-match problems — but it is the right
  tool for the one gap nothing else covers: **flat graphic detail with no geometry** (Krishna's
  flag text, a logo on a shirt).

### EXP-023 — the white boundary fringe, and why a majority filter can't fix it  (2026-08-12)

- **Observation (user, worstsister):** in Bambu, a **white rim along every colour boundary** —
  hairline, eyebrows, both figures' eyes, ears, teeth edges. Palette was skin/black/white/blue and
  the shading itself was clean (EXP-022's `--black-chroma` gate had already done its job).

- **Cause — two, both upstream and neither fixable in the palette:**
  1. **Texture resolution.** A ~2K texture on a 1.5M-face mesh is roughly **3 faces per texel**, and
     filtering blends across every seam. The transition band is genuinely ~10 faces wide.
  2. **Baked specular.** The source art is a glossy Pixar-style render. Rim highlights on black hair
     are bright and near-neutral, so they read as *white albedo*, not as lighting.

  Both produce pixels that are genuinely light and low-chroma, so they snap to the lightest
  low-chroma slot. Note this is **not** the EXP-022 problem and no colour-space knob touches it:
  the fringe pixel really is white-ish, whatever weighting you use. It is a spatial artifact and
  needs a spatial fix.

- **What did NOT work — 3-neighbour majority filter** (tried first, on the assumption of a 1-face
  fringe). It only roughens the edges of a 10-wide band:

  | | white faces | components | tiny (<50f) |
  |---|---|---|---|
  | before | 312,312 | 842 total (all colours) | 705 |
  | after 2 passes | 312,165 | **1777** | **1649** |

  Worse on every measure. Don't retry it.

- **What worked — morphological opening on the offending colour.** Erode N, dilate N back within
  the original mask: any region **thinner than 2N faces** vanishes, anything thicker returns to its
  exact original boundary. Removed faces are re-snapped against the palette *minus* that colour
  using their own vertex colours, so they take the colour they actually are.

  `--open "#F0E9DC=6"` → white 312,312 → 285,653 faces, components **518 → 31**, tiny **424 → 0**.
  Onesie (274k→264k), teeth (7038→6931) and all four eyes (2561/2546/1705/1536/1130) survive.

  The key property: opening removes what is **thin**, not what is **small**. That is exactly the
  distinction between a rim and an eye white, which is why a size threshold alone is the wrong tool
  and why this is safe on faces.

- **Honest limit:** user's verdict was "not perfect but way better" — some fringe survives where the
  band exceeds 12 faces or where it merges into a genuinely white region. Raising N eats real
  features, so N≈6 is the practical ceiling on a ~1.5M-face model. The complete fix for boundary
  crispness is `figurine-blockcolor`, whose boundaries are geometric seams and which therefore has
  no transition band at all — 40 credits, and worth it when the fringe matters more than fine detail.

- **Decision:** `--open` shipped in `colorize_3mf.py`. Reach for it on any glossy source art —
  which is all of the `pixar-figurine-render` output, so expect it on most human models.

### EXP-NNN — <title>  (<date>)
- **Hypothesis:**
- **Setup:**
- **Result:**
- **Decision / next:**
