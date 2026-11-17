---
name: figurine-blockcolor
description: Colour a figurine by geometric part instead of by pixel — one flat filament colour per Tripo segment, so major forms come out clean and shading can never bleed. Use when a colorize_3mf result has dark shadows leaking into black, muddy region boundaries, or the user asks for "flat colours", "clean boundaries", "colour per part", "block colouring", or wants to hand-paint from a parts map.
---

# Figurine Blockcolor

Approved render → N-filament 3MF where **the colour decision is made once per geometric part**,
not once per vertex. Major forms (cap, shirt, legs, glasses, shoes) come out as clean flat blocks
with boundaries on real geometric seams. Texture-scale detail is deliberately dropped.

This is the third colouring path:

| Skill | Decides colour per | Good at | Bad at |
|---|---|---|---|
| `figurine-colorize` | **vertex** | fine detail, hair, brows | shading bleeds into black |
| **`figurine-blockcolor`** (this) | **part** | flat clean regions, no bleed | loses detail with no geometry |
| `figurine-split` | — (re-uses existing paint) | fitting a slot budget | not a colouring tool |

## When to use
- A `figurine-colorize` result has **dark creases going black** — under the chin, armpits, inner
  legs, trouser folds. This is the headline fix.
- The user wants "flat colours", "clean boundaries", "colour each part", "block colours".
- The user wants to **hand-paint** and needs to know which region is which — see the parts map.

Not this: if the model needs fine detail more than flatness (a face with distinctive brows and a
moustache), run **hybrid mode** below, or stay on `figurine-colorize`.

## Hard rules
- Run from `figurines/`. Load keys: `set -a; source .env; set +a` (needs `TRIPO_API_KEY`).
- **Never call `mesh_completion` / `quick_cap` here.** Nothing is ever split. The segmentation is
  used only as a *face label map* onto the original mesh, which is never modified — so there is
  nothing to close and nothing to recombine. That call belongs to `figurine-split` and would waste
  30 credits and several minutes.
- **Never sign off on colour with `colorize_3mf.py --preview`** — it fakes speckle (EXP-020).
  Verify with `render_3mf.py`.
- Requires an already-generated model. Get `<n>_textured.glb` + `<n>_geometry.3mf` from
  `figurine-colorize` Phase 1 first.

## Cost

| Step | Credits | Time |
|---|---|---|
| `mesh_segmentation` (v3, one call) | **40** | ~50 s |
| everything else | free, local | ~1 min |

Roughly doubles the per-model Tripo spend (the model itself is 35). The segmentation is cached in
`seg_cache/`, so re-running with different palettes, thresholds or overrides is **free** — tune
freely once you've paid once.

## The two modes

```bash
cd /Users/apoorv/repos/everything3d/figurines
set -a; source .env; set +a
```

**Strict block** — every part one flat colour, nothing per-vertex anywhere. Maximum flatness.

```bash
python3 scripts/segment_paint_3mf.py projects/<n>/models/<m>_textured.glb \
  --geometry projects/<n>/models/<m>_geometry.3mf \
  -o projects/<n>/models/seg/<m>_blockcolor.3mf \
  --palette "#...,#...,#...,#..." --height <mm> \
  --granularity detailed --mixed-frac 0 \
  --color-space lab --luma-weight 0.35 --obj
```

**Hybrid (usually what you want)** — flatten only parts that are ≥95% homogeneous; inside the rest
snap per-vertex, with black gated by chroma. Keeps hair and brows *and* kills the bleed.

```bash
  ... --mixed-frac 0.95 --black-chroma 8 --color-space lab --luma-weight 0.35
```

Then verify — not optional:

```bash
python3 scripts/render_3mf.py projects/<n>/models/seg/<m>_blockcolor.3mf -o <m>_views.png
```

## Measured on docsurgeon (150 mm, 4 filaments, 19 parts)

| | black | white | teal | skin |
|---|---|---|---|---|
| `colorize_3mf` per-vertex | **14.6%** | 8.5% | 50.1% | 26.8% |
| strict block | 3.9% | **2.5%** | 60.5% | 33.1% |
| **hybrid** | **5.3%** | **10.1%** | 57.5% | 27.1% |

Black at 14.6% was mostly shading bleed, not glasses. Strict block killed it — and took the hair
with it. Hybrid gets both.

## The limit you must state up front

**Strict block drops any feature that has no geometry of its own.** On docsurgeon the segmentation
gave separate parts for glasses, ears, nose, eyebrows and each croc — but the whole cranium and
face came back as **one part with the hair fused in**. So flat-filling put white at 2.5%, all of it
at collar height (the mask); the hair, moustache and brows went skin-coloured. Measured, not
guessed: white faces sat only at z/H 0.5–0.8.

No per-part override can rescue this — the hair is not a part. Only the per-vertex fallback
(hybrid) gets it back. Same applies to logos, flag text and printed graphics: those are texture,
not geometry. Say so in the handoff rather than shipping a bald figurine.

## Part-only painting

```bash
  --parts-map projects/<n>/models/seg/<m>_parts_map.3mf
```

Writes a 3MF with one distinct colour per part plus a printed index/face-count/z-range table.
Render it, read the indices off it, then force any part:

```bash
  --part 10=#F0EFEA --part 6=#1A1A1A
```

Overrides run last and beat everything. A colour not already in the palette is appended as a new
slot — watch the filament count.

## Traps

**Tripo returns the parts renormalized into a unit box.** Your mesh is in mm. Map back with **one
global affine** (`make_transform` from `split_painted_3mf.py`) — per-part would inflate each part.
Skip it and every part collapses onto a handful of faces near the origin; the label map degenerates
and the tool **silently emits exactly the per-vertex result**. Tell-tale: `100.00% unclaimed ->
nearest neighbour` and `0.0% of faces differ`. A healthy run reports well under 0.1% unclaimed.

**Anything that isn't a standing figurine needs `--up-axis y --geometry-up-axis z`.** "Up" is
otherwise inferred from whichever axis is longest, and it is inferred *separately* for the Y-up GLB
and the already-Z-up geometry 3MF. A car or a scooter is longer than it is tall, so it gets stood
on its nose — in two different frames — and the colour transfer then samples the wrong surface.
The symptom is a colour landing somewhere absurd (silver tyres on the `girl-and-scooty` scooter,
at 35% of faces instead of 18%); fixing the axes took mint from 46% to 61%. A tall figurine
resolves to those same values anyway, so passing them is never wrong. Note the spelling: several
older project READMEs say `--glb-up` / `--geom-up`, which the script has never accepted.

**Render before reacting to the face histogram.** A face count is not what the eye sees. On
`kia-seltos-mahi` the first pass reported black at 69% against the body colour's 26% — textbook
shading bleed, except it wasn't: the render showed the body reading correctly, with black going to
the roof, the whole glasshouse, the tyres, the arch cladding and the underbody. Those really are
black and really are most of the mesh. Interior and downward-facing surfaces inflate dark slots on
any closed subject, so reach for `render_3mf.py` before you reach for the tuning knobs.

**The segmentation may not be semantic at all.** It is reliable on a human — cap, shirt, shoes.
On `kia-seltos-mahi` the 15 parts cut *across* the car instead of following it: one part spanned
body panels and glass, another spanned a wheel and the side sill. `--part IDX=#HEX` is then
useless and the per-vertex fallback is doing all the real work. Render the parts map before
planning a session of overrides around it.

**Still pass `--color-space lab --luma-weight 0.35`.** This tool defaults to RGB, and in RGB grey
hair is nearer teal than white (see EXP-022). Without it the brows and moustache go teal even in
hybrid mode.

**The chroma gate does most of the work — try it alone first, in `colorize_3mf.py`.**
`--black-chroma 8` lives in both tools. On docsurgeon, `colorize_3mf.py --black-chroma 8` alone
reached black 5.4% / white 10.4% with **no Tripo call**, against 5.3% / 10.1% for the 40-credit
hybrid here. Segmentation flattened only 5 of 19 parts at the 0.95 threshold. **So spend the 40
credits only when flat geometric boundaries are wanted for their own sake** — if the complaint is
just "the shadows went black", the free path already fixes it.

**`--granularity`** is `simple` | `balanced` | `detailed`. Use `detailed`. (EXP-017's finding that
the API exposes no granularity control is **obsolete** — that was the v2 API; v3 `/mesh/segment`
takes `segmentation_granularity`.)

## Handoff

The output is the original mesh with new per-face colour indices — verify and report it as such:
watertight, single body, all edges valence 2, unchanged W×D×H, sitting on z=0. Report the filament
hex list, the face distribution, **and any feature the block pass dropped**. Send the views render
and, if they'll hand-paint, the parts map.

## Background

`docs/auto_coloring.md` EXP-022 (why shading bleeds into black on humans and not animals),
EXP-010/011/012 (the original per-segment colouring work and the texture-detail limit),
EXP-021 (segmentation is a lossless partition — why the label map is exact).
