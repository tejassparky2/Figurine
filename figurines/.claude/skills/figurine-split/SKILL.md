---
name: figurine-split
description: Split an already-painted 3MF into parts so no single part needs more filaments than the printer has slots — without repainting anything. Use when the user says a finished model "has 5 colors", "too many colors", "only 4 slots / AMS", "split the head off", "split it into parts", or wants a multi-part print of a model they already coloured. Picks up after figurine-colorize and after the user has painted in Bambu.
---

# Figurine Split

A finished, painted 3MF → two or more watertight parts, each needing fewer filaments, with the
**original paint carried over face-by-face**. Nobody repaints anything.

## When to use
- "it's 5 colors but I only have 4 slots" / "too many colours"
- "split the head off", "split it into parts", "print it in pieces"
- Anything where the model is already coloured/painted and the *palette* is the problem.

Not this: if the model isn't coloured yet, use `figurine-colorize`. If you want fewer colours by
merging similar ones, that's a palette change — re-run `colorize_3mf.py` with a smaller
`--palette`, don't split.

## Hard rules
- **Never write to the user's painted file.** Work on a copy; verify with `md5 -q` before and
  after and say so in the handoff. They have hand-cleanup in that file that cannot be regenerated.
- **The input must be a real Bambu project.** If it came straight from `colorize_3mf.py` or
  `segment_paint_3mf.py` it is a *bare* 3MF — run `colorgroup_to_painted.py` on it first. See
  "The blank-output trap".
- **Verify with `scripts/verify_3mf.py`, not with your own parser.** See "Verify before handoff".
- Run from `figurines/`. Load keys: `set -a; source .env; set +a` (needs `TRIPO_API_KEY`).
- **Read the palette out of the file, never infer it.** See "The rank-matching trap".
- **Always pass `completion_mode: quick_cap`.** The default `ai_completion` destroys the surface.

## Why this works at all

Three facts, each measured (docs/auto_coloring.md EXP-021):

1. Bambu stores `paint_color` as a **per-triangle attribute on the unmodified mesh** — attribute
   count == face count, vertex count unchanged. So colour is just an array indexed by face.
2. Tripo `mesh_segmentation` is a **lossless partition, not a resample** — face count −0.03%,
   vertex count *rises* (boundary verts duplicated into both parts), 99.90% of part vertices
   within 1e-6 of an original.
3. So a centroid KDTree from part faces back to source faces transfers paint at **0.000mm**.

That's the whole trick. ~97% of faces inherit verbatim; the remaining ~3% is new interior cap
geometry, which takes its nearest neighbour's code and is never visible.

## The tool

```bash
cd /Users/apoorv/repos/everything3d/figurines
set -a; source .env; set +a

# pass 1 — segment, close, and report what came back
python3 scripts/split_painted_3mf.py projects/<name>/models/<painted>.3mf \
    -o projects/<name>/models/split

# pass 2 — group the parts and write them out
python3 scripts/split_painted_3mf.py projects/<name>/models/<painted>.3mf \
    -o projects/<name>/models/split \
    --group HEAD=0 --group BODY=1,2,3 --sweep HEAD=1C --sweep BODY=4
```

Pass 1 prints each part's face count and filament inventory so **you** choose the grouping. Parts
are indexed largest-first, so `part_0` is usually the head-and-hair mass on a figurine — but check
rather than assume: on Krishna `part_0` was the body and `part_1` the head, with the flag and staff
coming back as their own parts. Every Tripo step is cached in the output dir — pass 2 is free.

Add **`--single-file`** to get one 3MF containing every group as a separate object, spread along
the plate and each dropped to z=0, rather than one file per group. Same project settings and
palette either way. Use it when the user wants to keep one file to hand around; use separate
files when they'll print the parts on different days with different spools loaded.

**Identify the parts before grouping.** Print each part's z-range and render them in flat
distinct colours — it takes one pass and tells you immediately which blob is the head. Guessing
from face count alone will get it wrong.

`--sweep NAME=code` reassigns stray paint codes inside a group to their nearest neighbour. You
almost always need it: segmentation boundaries drag a little of the neighbour's colour across
(5,810 black hair faces landed on the sister's body). **Without sweeping, the part still demands
that filament for 1% of its faces and the whole exercise fails.**

## Choosing the split

Look at pass 1's inventory and find a grouping where every group is within the slot budget. For a
figurine the natural line is **head/hair vs everything else**: hair is one huge blob of one colour
and the garments are another cluster.

Sanity-check with the user's actual constraint. Union of 5 across two parts is fine — what matters
is that **no single part exceeds the slot count**.

**The split does not always reduce the count — say so when it doesn't.** It worked on the sister
because her hair was one huge near-pure-black mass. Krishna's red/gold/black/blue/skin are spread
over his robe, flag and staff, so his head came down to 4 but the body stayed at 5, and no
regrouping fixes that (flag and staff each need 5 on their own too). When that happens, the honest
answer is that this model needs a palette change instead — merge two near-identical filaments
(Krishna's slots 2 and 7 are both `#D9A128`, slots 1 and 6 are both near-red) and re-colorize.

Do not reach for a horizontal cut plane. On the sister every plane left 5 colours on one side,
because her hair hangs to waist height. It has to be semantic.

## The blank-output trap

`write_3mf()` clones the source project and swaps the new mesh into `obj_entry`. On a real Bambu
project that is `3D/Objects/object_1.model`, and the `<build>` items — which place the object on
the plate — live separately in `3D/3dmodel.model`, untouched. On a **bare** 3MF from
`colorize_3mf.py` / `segment_paint_3mf.py` there is only the one file, so `obj_entry` *is* the
build-bearing file. It gets replaced by a mesh with an empty `<build/>`, and Bambu opens the
result on a blank plate with "no geometry data".

Two parts shipped this way. What made it survive review: the mesh really is in the file, so every
triangle-level check passes — face counts, watertightness, filament inventory, even a render made
by re-parsing the output. Only a slicer notices. `trimesh.load()` also notices (`KeyError:
'world'`, because it walks the build graph and finds nothing placed) — that error is the tell, not
a quirk of trimesh, and must never be waved away.

The script now hard-stops on bare input and prints the conversion command, so this should not
recur. If you are hand-rolling anything in this area, run `verify_3mf.py` on the result.

## Closing the parts — `quick_cap`, not PyMeshFix

Segmented parts come back as **open surface patches**. The script closes them with v3
`/mesh/complete` in `completion_mode: quick_cap` ("seal open boundaries without AI generation").

Measured against local PyMeshFix on the same four parts:

| part | quick_cap | PyMeshFix |
|---|---|---|
| head 900k | watertight, **0.0007mm** drift | watertight, 0.0002mm |
| skirt 496k | watertight, **0.0037mm** | watertight, 0.0117mm |
| torso 66k | watertight, **0.0016mm** | **5.6mm — deleted 8,371 faces** |
| hem 19k | watertight, **0.029mm** | **7.5mm** |

MeshFix competes only on big parts and **mangles small ones**. Keep it as fallback only
(`meshfix/fix_parts.py`). And the *other* completion mode, `ai_completion`, is the one EXP-018
rejected: it resamples the entire surface and still doesn't close the parts. Never use it here.

## The rank-matching trap

Paint codes are slot indices, not colours. Do **not** guess which code is which colour by matching
face-area percentages against whatever palette you used at colorize time — the user will have
repainted. On the sister they had swapped gold for cream and moved regions around; rank-matching
rendered her lehenga gold and her face pink, and it looked plausible enough to nearly ship.

Read the truth out of the file:

```python
cfg = json.loads(z.read("Metadata/project_settings.config"))
cfg["filament_colour"]   # ['#1A1611', '#BE2F4E', '#EDA468', '#F792A5', '#FDFEF2']
```

Codes map monotonically to slots: `4`,`8`,`0C`,`1C`,`2C` → slots 1..5.

**Keep the codes and the palette exactly as they are** when writing the parts. Remapping to
"compact" a part down to slots 1-4 risks silently swapping colours for zero benefit — the slicer
only consumes the filaments actually referenced. Each part just leaves one slot unused.

## Two mapping bugs that will bite you

Both produce output that looks superficially fine:

- `scene.geometry` returns parts in **local** frames. You must apply the `scene.graph[node]`
  transforms, or every part sits at the origin and the colour match is nonsense.
- Compute the part-space→mm affine **once, globally**. Per-part centring re-scales each part to
  the full model; the tell is every part reporting the whole z-range and a ~17mm match error.

The health check is the match error. It should read **0.000mm mean and max**. Anything else means
the alignment is wrong — stop and fix it rather than accepting a fuzzy colour transfer.

## Verify before handoff

```bash
python3 scripts/verify_3mf.py <part>.3mf                          # structural — always
python3 scripts/render_3mf.py <part>.3mf -o <part>_views.png      # visual, if colorgroup-encoded
```

`verify_3mf.py` is the one that catches a file which will not open: zip order, `<build>` items,
and an independent `trimesh.load()`. Run it on every part, every time. **Do not substitute your
own parser** — a parser you wrote to read the mesh will happily read a file with no build items
and tell you it is fine, which is exactly how the blank parts got shipped.

For paint_color parts, re-parse the written file (don't trust intermediates) and render from it.
Check per part: watertight, open edges, bodies, W×D×H, and the filament list. Then **look at the
render** — the rank-matching trap is invisible in the numbers and obvious in the picture.

## Handoff

Report per part: path, dimensions, face count, watertight/open-edges/bodies, and **the filament
list with hexes** so they load the right spools. State the source file's md5 before and after to
prove it's untouched. Call out:

- how many cap faces were invented and that they're interior
- how many stray faces were swept, and from which colour
- any part with `bodies > 1` (merged groups have one shell per member; they abut on their shared
  cut curve and slice as one mass, but Bambu will show them as separate parts)
- that parts keep the source coordinate frame, so loading both reassembles them exactly

Say plainly that you have not opened them in a slicer, if you haven't — and say which checks you
actually ran, since "verified" meant "my own parser read it back" the time this went wrong.

## Before you build a new tool

Check whether it already exists, in this order: the other skills in `.claude/skills/`, then
`git status` and `git worktree list` in the main checkout. Uncommitted work-in-progress is
invisible to a grep of committed code, and this repo usually has several worktrees live at once.
Both `colorgroup_to_painted.py` and `reorient()`/`--up-axis` were sitting uncommitted in the main
checkout while a fresh session reinvented them badly in a worktree.
