---
name: figurine-colorize
description: Turn an approved figurine render into a multi-color, slicer-ready 3MF with N filament colors. Use whenever the user wants "the 3D model", "make the models", a "colored 3mf", "5 colors / 4 colors", or a printable multi-material figurine from an approved image. Picks up exactly where pixar-figurine-render stops.
---

# Figurine Colorize

Approved 2D render → watertight, N-color 3MF that a slicer can print with one filament per color.

This is the **colored** path. For a plain single-color print use `scripts/image_to_3d.py` instead
(`figurines/README.md`, Pipeline C) — it's one call and much simpler.

## When to use
- "make the models" / "make the 3D models" after renders have been approved
- "5 colors", "4 colors", "3 colors", "multi-color", "MMU", "colored 3mf"
- Follows on from `pixar-figurine-render`, which deliberately stops before any 3D generation.

## Hard rules
- **Never run Tripo until the user has approved the render.** It costs credits. If you're not
  certain a render is approved, ask.
- Run everything from `figurines/`.
- Load keys first: `set -a; source .env; set +a` — needs `TRIPO_API_KEY`.
  **The keys are in `figurines/.env`** — there is no repo-root `.env` at all.
- **Never sign off on color using `colorize_3mf.py --preview`.** See "The `--preview` trap" below.

## Cost model — where to spend your time

| Phase | Cost | Time | Iterate here? |
|-------|------|------|---------------|
| 1. Tripo generation | **credits** | 2–4 min/model | No — run once per image |
| 2–5. Palette, colorize, verify | free, local | ~1–2 min/run | **Yes, freely** |

Everything after Tripo is local. Get the geometry once, then tune the palette as many times as
you like. Run the three Tripo jobs in parallel in the background if you have several models.

## Project layout

```
projects/<name>/
  approved/     # the approved renders — one PNG per model
  models/       # everything below lands here
    <n>_textured.glb          # Tripo: color source (messy geometry)
    <n>_geometry.3mf          # Tripo: watertight geometry (arrives flat grey)
    <n>_colored.3mf           # DELIVERABLE — colorgroup 3MF
    <n>_colored.obj + .mtl    # DELIVERABLE — crispest face-color import in Bambu
    <n>_views.png             # verification render
  README.md     # palette, exact commands, deviations from the reference art
```

Write that per-project README — it's the only place the chosen palette and per-model tuning
survive. Note `figurines/projects/` is **gitignored**, so it never reaches the repo; anything
worth keeping permanently belongs in `docs/auto_coloring.md` or this skill.

## Phase 1 — Tripo, twice, off the same task

```bash
cd /Users/apoorv/repos/everything3d/figurines
set -a; source .env; set +a

python3 scripts/gen_textured_for_color.py projects/<name>/approved/<n>.png projects/<name>/models
```

That single script makes both calls:

1. **`image_to_model`** with `texture=True, pbr=False` → textured GLB = the **color source**.
   Its geometry is Tripo's raw pre-repair mesh (many shells, thousands of open edges) — unusable
   for printing. `pbr=False` matters: PBR bakes specular/lighting into the texture and makes flat
   quantization much harder.
2. **`convert_model`** with `format=3mf, texture=True, original_model_task_id=<same task>` →
   repaired, watertight, single-body 3MF = the **geometry**. It arrives flat grey `#666`; color
   does not survive into the 3MF.

You need both halves and they must come from the **same model task** — that's what makes them
share a coordinate frame so Phase 3 can fuse them. `format: glb` returns HTTP 400; it must be `3mf`.

## Phase 2 — choose the palette

N filament hexes, N = the color budget the user gave. Seed by k-means on the source PNG with the
white background dropped, then **clean the results up by eye** — raw cluster means come back
shading-averaged and muddy (`#7b260c`, `#c17535`) and make poor filament choices. Aim for
saturated, filament-like colors.

Spend the budget on regions, not on fidelity to every detail. A 5-color figure typically wants
skin / hair-and-dark / two garment colors / metal-gold. If something in the reference has no slot
left (e.g. white flag text), say so explicitly in the handoff rather than silently dropping it.

## Phase 3 — fuse and quantize

```bash
python3 scripts/colorize_3mf.py projects/<name>/models/<n>_textured.glb \
  --geometry projects/<name>/models/<n>_geometry.3mf \
  -o projects/<name>/models/<n>_colored.3mf \
  --palette "#RRGGBB,#RRGGBB,..." --height <mm> --obj
```

What it does: texture → per-vertex RGB; reorient Y-up → Z-up; scale to `--height` on Z, center
X/Y, sit on Z=0; load the watertight mesh and apply the *identical* normalization; KDTree
nearest-vertex transfer of color onto it (measured ≈0.000mm, lossless); snap each vertex to the
nearest palette color; face color = majority vote of its 3 vertices; write `<m:colorgroup>`
per-triangle indices (the encoding Bambu actually reads) plus OBJ/MTL.

**Height conventions:** default 120mm. Couples: man 120mm, woman 110mm. Otherwise use what the
user specified per model — `--height` is per-run, so run each model separately.

## Phase 4 — tuning: which knob, and when

Start plain. Add a knob only when the verification render (Phase 5) or the printed face
distribution shows a region going to the wrong color.

| Symptom | Knob | Why |
|---|---|---|
| Hues are far apart, looks right already | *(nothing)* | Default RGB is fine — e.g. blue/red/gold/skin/black |
| A shaded light region bleeds into a warm color (white → gold) | `--color-space lab --luma-weight 0.35` | Down-weights lightness so hue/chroma decides; shadow stops mattering |
| **Dark creases (chin, armpits, folds) bleeding into black** | `--black-chroma 8` | Black is only reachable by genuinely achromatic verts. The single most common defect on human models — see below |
| **Light rim along every hairline / brow / eye** | `--open "#<lightest>=6"` | Deletes colour bands thinner than 12 faces. Texture blur + baked specular, not a palette problem — see below |
| Light body + dark detail (white horse, black mane) speckles between the two | `--dark-below <L> --color-space lab` | Hard luminance floor: below L → darkest color, rest snap among the others |
| Feet/base painted the wrong color | `--floor-color <hex> --floor-frac 0.05` | Forces the bottom band |

### Shadows going black — check this on every human model

The default failure mode on people in ordinary clothes. Tripo bakes ambient occlusion into the
texture, and shading is *multiplicative*, so it drives lightness **and chroma** toward zero —
aiming every shaded pixel straight at the black centroid. On docsurgeon that was **14.6% of faces
black**, of which 62% was shaded teal and skin rather than anything actually black.

`--black-chroma 8` gates the darkest slot on the discriminator that separates the two: real black
sits at chroma ~0–1, shaded garments keep chroma 8–30. It took black to **5.4%** and cost nothing.

**Preflight:** sort the palette by Lab L. If the gap between black and the next-lowest colour
exceeds ~30, expect bleed. docsurgeon was 9.3 → 52.6, a 43-point empty band; Krishna's palette
(5.0/29.2/39.9/69.7/78.4) has no gap over 24 and never bled. Saturated dress and near-white/
near-black subjects are naturally immune — which is why the horse and snake always looked perfect.

⚠️ **`--luma-weight` cannot fix this** and makes it marginally worse (14.5% → 14.7%): black is at
chroma 0, so down-weighting lightness helps it capture desaturated shadow. Use luma-weight for the
*other* bug — grey hair snapping to a mid-tone garment colour. Full analysis: EXP-022.

### A light rim on every boundary — expect this on glossy source art

The second standard defect, and it looks alarming in Bambu: a white/cream band tracing every
hairline, eyebrow, eye and ear. It is **not** a quantization mistake. Two upstream causes: a ~2K
texture on a 1.5M-face mesh is ~3 faces per texel so filtering blends across every seam, and the
`pixar-figurine-render` output is glossy, so baked specular rims on dark hair read as white albedo.
The fringe pixels genuinely *are* light and neutral, so **no colour-space or weighting knob touches
this** — it is spatial and needs a spatial fix.

```bash
  --open "#F0E9DC=6"      # the lightest palette slot, radius 6
```

Morphological opening: erode 6, dilate 6 back inside the original region, so anything **thinner
than 12 faces** disappears while thicker regions keep their exact boundary. On worstsister: white
components 518 → 31, tiny ones 424 → 0, with the onesie, teeth and all four eyes intact.

It removes what is **thin**, not what is **small** — that distinction is what makes it safe on eye
whites, and why a min-component-size threshold is the wrong tool.

⚠️ **Do not try a majority filter.** It assumes a one-face fringe; measured on a 10-wide band it
left white at 312,165 faces (from 312,312) and made components *worse*, 842 → 1777. EXP-023.

Some fringe survives where the band is wider than 12 faces; raising the radius starts eating real
features. If boundary crispness matters more than fine detail, that's the case for
`figurine-blockcolor`, whose boundaries are geometric seams with no transition band at all.

**Picking `--dark-below`:** histogram Lab L of the low-chroma vertices and put the threshold in
the gap between the two modes. The horse was cleanly bimodal — black 10–20, white 75–90, only ~4%
between — so 20.

```python
lab = srgb_to_lab(vcol); L = lab[:,0]; C = np.hypot(lab[:,1], lab[:,2])
np.histogram(L[C < 12], bins=20, range=(0,100))   # find the valley
```

⚠️ **`--dark-below` snaps the leftovers in whatever `--color-space` you passed**, and in RGB a
mid-grey is nearer `#C4201E` than white. At `--dark-below 15` the horse's entire mane came out
**red**. Always pair `--dark-below` with `--color-space lab`.

## Phase 5 — verify (do not skip)

```bash
python3 scripts/render_3mf.py projects/<name>/models/<n>_colored.3mf \
  -o projects/<name>/models/<n>_views.png
```

Renders the shipped file — parsing its per-triangle `p1` against its own `<m:colorgroup>` — with a
real depth test, from 5 angles. This is what the slicer will show. Look at it, and compare against
the approved render.

Also read the **face distribution percentages** both scripts print. They catch bleed numerically
before you can see it: a necklace has no business being 12% of faces (the snake's was — shadowed
white belly leaking into gold; Lab luma 0.35 brought it to 6.5%).

### The `--preview` trap
`colorize_3mf.py --preview` uses a point-splat renderer with a weak occlusion test. Occluded back
geometry punches through on **front-facing** surfaces and fakes heavy salt-and-pepper speckle that
**is not in the model**. Tell-tale: front view speckled, side view clean in the same PNG, and the
speckle doesn't move no matter what you change. Several tuning runs have been burned on this.
Use `render_3mf.py`. (docs/auto_coloring.md EXP-020)

## Phase 6 — final checks before handoff

```python
s = trimesh.load(path, process=False)   # process=False — as authored
m = s.to_geometry() if isinstance(s, trimesh.Scene) else s
c = Counter(map(tuple, m.edges_sorted))
# extents vs target height, m.is_watertight, m.body_count, edge valences, color count
```

Load with **`process=False`**. `process=True` re-welds vertices and will report false
non-watertightness (and can cause it — that's what the `--geometry` fix was about).

**Don't audit Tripo's geometry beyond this.** Across the Goga ji set `convert_model` gave 2
strictly watertight meshes and 1 with a 0.17 × 0.008 × 0.003 mm sliver hole — orders of magnitude
under a 0.4mm nozzle, and Bambu auto-repairs it on import. Chasing sub-nozzle mesh defects has
never improved a print. Every real defect in this pipeline has been in the **color** pass.

## Script reference

| Script | What it does |
|---|---|
| `gen_textured_for_color.py <image> <out_dir>` | Phase 1 — both Tripo calls, writes `<n>_textured.glb` + `<n>_geometry.3mf` |
| `colorize_3mf.py <glb> --geometry <3mf> -o <out>` | Phase 3 — fuse + quantize. `--palette`, `--height`, `--obj`, `--color-space`, `--luma-weight`, `--black-chroma`, `--open`, `--dark-below`, `--floor-color`, `--encoding` |
| `render_3mf.py <colored.3mf> -o <png>` | Phase 5 — verification render. `--angles`, `--width`, `--height` |

`--encoding colorgroup` is the default and is what Bambu reads; `basematerials` does **not** show
color in Bambu Studio. Always pass `--obj` too — OBJ+MTL gives the crispest face-color import.

## Handoff

Report per model: file path, height, color count, W×D×H, watertight/bodies, and the filament hex
list so the user can load the right spools. Call out **any deviation from the approved art**
explicitly — a color the budget couldn't cover, or a surface Tripo invented (it fabricates
back faces it can't see; Krishna's flag was blue in front and red behind). Send the
`<n>_views.png` files.

## Background

`docs/auto_coloring.md` is the experiment log. EXP-019 established the two-call Tripo path,
EXP-020 covers the `--preview` trap, the `--dark-below` color-space gotcha, and why not to audit
Tripo geometry. Read those two entries before changing anything here.
