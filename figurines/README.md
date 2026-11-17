# Figurine Pipeline

Photo → extract people → background removal → styled render → proportion fix → client review → 3D model (.3mf).

> **Read the skill before colouring or splitting**, not just this file. `.claude/skills/`
> (`figurine-colorize`, `figurine-blockcolor`, `figurine-split`) is where the *negative* results
> live — the approaches that were tried, measured and rejected. This README tells you the happy
> path; the skills tell you which clever idea not to have. `figurine-split` already rules out the
> horizontal cut plane, for instance, and says `bodies > 1` on a merged group is expected.

## Folder Structure

```
figurines/
├── scripts/              # Pipeline code
├── projects/             # One folder per client batch
│   └── <batch>/
│       ├── input/        # Original photos (single or group)
│       ├── extracted/    # Individual person crops (only for group photos)
│       ├── nobg/         # Background removed (white BG, cropped, square)
│       ├── renders/      # Styled renders (pixar/funko), may have variants (_v1, _v2)
│       ├── renders_fixed/# After proportion fix (larger head, smaller body)
│       ├── approved/     # Client-approved final renders (for 3D conversion)
│       ├── models/       # 3MF files scaled to 120mm
│       └── review.pdf
└── archive/              # Old test runs
```

## Pipeline A: Group Photo → Review PDF

For group photos where you need to extract each person, generate multiple options, and get client approval.

```bash
cd figurines
export FAL_KEY=...

# 1. Extract individual people from group photo (uses Moondream2 detection)
python scripts/extract_people.py projects/<batch>/input -o projects/<batch>/extracted

# 2. Remove backgrounds (outputs square images on white BG)
python scripts/remove_bg.py projects/<batch>/extracted -o projects/<batch>/nobg

# 3. Generate styled renders (pixar style, 2 variants per person)
python scripts/generate_render.py projects/<batch>/nobg -o projects/<batch>/renders -s pixar -v 2

# 4. Fix proportions for 3D printing (bigger head, smaller body)
python scripts/generate_render.py projects/<batch>/renders -o projects/<batch>/renders_fixed -s proportion_fix

# 5. Make review PDF (shows before + all variants side by side)
python scripts/make_review_pdf.py projects/<batch>/nobg projects/<batch>/renders_fixed \
    -o projects/<batch>/review.pdf \
    --title "Project Name" \
    --source-dir projects/<batch>/input
```

## Pipeline B: Single Person Photos → Review PDF

For folders of individual photos (one person per image). Skip the extraction step.

```bash
# 1. Remove backgrounds
python scripts/remove_bg.py projects/<batch>/input -o projects/<batch>/nobg

# 2-5. Same as above (generate renders, proportion fix, review PDF)
```

## Pipeline C: Approved Renders → 3D Models (single color)

After client picks their preferred renders, put them in `approved/` folder and generate 3D models.

> **Want a multi-color model?** This pipeline produces an uncolored 3MF. For an N-filament colored
> model, use **Pipeline D** below instead — it's a different set of Tripo calls, not a post-step.

```bash
export TRIPO_API_KEY=...

python scripts/image_to_3d.py projects/<batch>/approved -o projects/<batch>/models --height 120
```

**Height convention:** default is **120mm**. For **couple figurines (man + woman), the man is 120mm and the woman is 110mm** so the pair looks proportionate together. Since `--height` applies to the whole batch, run the two separately — e.g. put each person's render in its own folder (or use `-n`) and convert with the right `--height`:

```bash
# man at 120mm
python scripts/image_to_3d.py projects/<batch>/approved/man   -o projects/<batch>/models --height 120
# woman at 110mm
python scripts/image_to_3d.py projects/<batch>/approved/woman -o projects/<batch>/models --height 110
```

## Pipeline D: Approved Renders → Colored (multi-filament) 3D Models

Produces a watertight 3MF with N flat filament colors, one per region — the printable equivalent
of hand-painting regions in Bambu Studio. **Full procedure: the `figurine-colorize` skill**
(`.claude/skills/figurine-colorize/SKILL.md`); background and rationale in `docs/auto_coloring.md`
(EXP-019, EXP-020).

```bash
set -a; source .env; set +a          # TRIPO_API_KEY lives in figurines/.env

# 1. Tripo, twice off one task: textured GLB (color) + convert_model 3MF (watertight geometry)
python3 scripts/gen_textured_for_color.py projects/<batch>/approved/<n>.png projects/<batch>/models

# 2. Fuse them and quantize to your filament palette
python3 scripts/colorize_3mf.py projects/<batch>/models/<n>_textured.glb \
  --geometry projects/<batch>/models/<n>_geometry.3mf \
  -o projects/<batch>/models/<n>_colored.3mf \
  --palette "#1B3C9E,#B81E1E,#D9A128,#E8B98F,#14100E" --height 120 --obj

# 3. Verify — render the shipped file as the slicer will show it
python3 scripts/render_3mf.py projects/<batch>/models/<n>_colored.3mf \
  -o projects/<batch>/models/<n>_views.png
```

Step 3 is not optional, and **do not** substitute `colorize_3mf.py --preview` for it — that
renderer fakes speckle that isn't in the model (EXP-020).

Same height conventions as Pipeline C. Tuning knobs (`--color-space`, `--dark-below`,
`--floor-color`) and when to reach for each are in the skill.

## Pipeline F: Block colouring — one flat colour per geometric part

Same inputs as Pipeline D, but the colour decision is made **once per Tripo segment** instead of
once per vertex. Fixes the failure mode where baked shading drags dark creases into black — on
humans in muted clothing that reached 14.6% of faces. **Full procedure: the `figurine-blockcolor`
skill**; rationale and measurements in `docs/auto_coloring.md` EXP-022.

```bash
set -a; source .env; set +a          # after Pipeline D step 1 has produced the GLB + geometry 3MF

python3 scripts/segment_paint_3mf.py projects/<batch>/models/<n>_textured.glb \
  --geometry projects/<batch>/models/<n>_geometry.3mf \
  -o projects/<batch>/models/seg/<n>_blockcolor.3mf \
  --palette "#2C8B85,#DDA070,#1A1A1A,#F0EFEA" --height 150 \
  --granularity detailed --mixed-frac 0.95 --black-chroma 8 \
  --color-space lab --luma-weight 0.35 --obj
```

Costs one `mesh_segmentation` call (**40 credits**, ~50 s), cached so re-runs are free. It does
**not** call `mesh_completion` — nothing is split, the segmentation is only a face label map and
the original watertight mesh is never modified.

`--mixed-frac 0` gives strict block colour (every part flat); note that drops features with no
geometry of their own — on docsurgeon that cost the hair and moustache. `0.95` plus
`--black-chroma 8` keeps them. Add `--parts-map <path>.3mf` for a per-part colour key, then
`--part 10=#F0EFEA` to force any individual part when hand-painting.

## Pipeline E: Painted 3MF → parts, when it needs more filaments than you have slots

For a model that is **already coloured and hand-cleaned** but wants (say) 5 filaments on a 4-slot
printer. Splitting it into semantic parts means no single part needs the whole palette — and the
paint carries over face-by-face, so nothing gets repainted.

> **The input must be a real Bambu project, not a bare 3MF.** Pipeline D/F output is bare: its
> mesh and its `<build>` items live in the same `3D/3dmodel.model`, so writing the parts blanks
> the build and Bambu opens them empty with "no geometry data". Convert first — the splitter now
> refuses bare input and prints this command rather than producing the broken file:
>
> ```bash
> python3 scripts/colorgroup_to_painted.py <colored>.3mf -o <colored>_painted.3mf
> ```
>
> The mesh is copied verbatim; only the colour encoding and the project shell change.

```bash
# 1. segment + close, then read the per-part filament inventory
python3 scripts/split_painted_3mf.py projects/<batch>/models/<painted>.3mf \
    -o projects/<batch>/models/split

# 2. group the parts and write them out
python3 scripts/split_painted_3mf.py projects/<batch>/models/<painted>.3mf \
    -o projects/<batch>/models/split \
    --group HEAD=0 --group BODY=1,2,3 --sweep HEAD=1C --sweep BODY=4
```

Add `--single-file` to get **one** 3MF holding every group as its own object, laid out side by
side on the plate and each sitting on z=0, instead of one file per group. The Bambu project
settings (filament palette included) are carried over either way.

**Verify every part before handing it over:**

```bash
python3 scripts/verify_3mf.py <part>.3mf
```

Checking the triangles is not enough — a file can have every vertex right and still open blank,
because what places it on the plate is the `<build>` item, not the mesh. `verify_3mf.py` checks
zip order, build items, and loads the file with trimesh (an independent reader that walks the
build graph, so it fails exactly where a hand-rolled parser succeeds). It caught nothing for
weeks because it didn't exist; it exists because two parts shipped blank.

The input file is only ever read. Tripo results are cached in the output dir, so pass 2 is free.
`--sweep` is usually required: segmentation boundaries drag a little of the neighbour's colour
across, and un-swept strays keep the part on the full palette.

Works because Bambu's `paint_color` is a per-triangle attribute on the unmodified mesh and Tripo's
segmentation is a lossless partition, so the transfer measures 0.000mm. Parts are closed with
`quick_cap`, **not** PyMeshFix (which mangles small parts) and **not** `ai_completion` (which
resamples the surface and doesn't close anything). Details and the traps: skill `figurine-split`,
docs/auto_coloring.md EXP-021.

## Post-Approval Edits

Use `generate_render.py` styles to make targeted edits on approved renders:

```bash
# Remove tikka/bindi, fix spectacles, etc. — edit in place or to a new dir
python scripts/generate_render.py projects/<batch>/approved -o projects/<batch>/approved -s fix_spectacles
```

Or use the GPT-image-2 API directly for one-off edits (remove tikka, add shoes, etc.):

```python
import fal_client, requests
url = fal_client.upload_file("path/to/image.png")
result = fal_client.subscribe("openai/gpt-image-2/edit", arguments={
    "prompt": "Remove the tikka from the forehead. DO NOT CHANGE ANYTHING ELSE.",
    "image_urls": [url], "quality": "low", "output_format": "png",
})
resp = requests.get(result["images"][0]["url"], timeout=120)
Path("output.png").write_bytes(resp.content)
```

## Scripts

| Script | API | What it does |
|--------|-----|-------------|
| `extract_people.py` | fal.ai Moondream2 | Detects people in group photos, crops each individually |
| `remove_bg.py` | fal.ai BiRefNet v2 | Removes background, composites on white, crops, pads to square |
| `generate_render.py` | fal.ai → GPT-image-2 | Generates styled figurine renders with variant support |
| `image_to_3d.py` | Tripo3D v2 | Converts render to 3MF, scales to target height |
| `make_review_pdf.py` | — (local) | Before/after PDF with variant columns, source photo on title page |
| `detect_spectacles.py` | — | Detects glasses for render touch-ups |
| `gen_textured_for_color.py` | Tripo3D v2 | Colored path: textured GLB (color) + watertight 3MF (geometry) |
| `colorize_3mf.py` | — (local) | Colored path: fuses those two into an N-filament 3MF |
| `render_3mf.py` | — (local) | Renders a colored 3MF as the slicer shows it — use to verify color |
| `split_painted_3mf.py` | Tripo3D v3 | Splits a painted 3MF into parts, carrying the paint over (fewer filaments per part) |
| `segment_paint_3mf.py` | Tripo3D v3 | Block colouring: one flat filament colour per geometric part, no shading bleed |
| `colorgroup_to_painted.py` | — (local) | Bridge: bare colorgroup 3MF → real Bambu project with `paint_color`. Required before `split_painted_3mf.py` |
| `verify_3mf.py` | — (local) | Structural check: zip order, `<build>` items, independent load, geometry, filaments. Run before every handoff |

## Render Styles (`-s` flag)

| Style | Description |
|-------|-------------|
| `pixar` | DreamWorks/Pixar-style 3D figurine. Single-color clothing with golden/silver borders. |
| `funko` | Funko Pop style. Arms folded, simple smile. |
| `proportion_fix` | Post-processing pass: enlarges head to ~40% of image. Run on renders, not on photos. |
| `fix_spectacles` | Makes spectacles black and slightly thick. |

## Key Options

All scripts support:
- `-n / --limit N` — process only first N images
- `-w / --workers N` — parallel workers (default: 5)
- Idempotent: skips images that already have output

`generate_render.py` extras:
- `-v / --variants N` — generate N variants per image (default: 1). Names: `name_v1.png`, `name_v2.png`
- `-s / --style` — render style (see table above)
- `-q / --quality` — `low` (default), `medium`, `high`

`extract_people.py` extras:
- `--padding` — padding fraction around each person crop (default: 0.05)

`image_to_3d.py` extras:
- `--height MM` — target height in mm (default: 120)

`make_review_pdf.py` extras:
- `--source-dir` — directory with original photos (displayed on title page)
- Automatically detects variants (`_v1`, `_v2`) and shows them as Option 1, Option 2, etc.

## Dependencies

```bash
pip install -r scripts/requirements.txt
# Needs: fal-client, Pillow, requests, pymupdf, trimesh
```

## API Keys

Set in `.env` at repo root:
- `FAL_KEY` — for all fal.ai calls (Moondream2, BiRefNet, GPT-image-2)
- `TRIPO_API_KEY` — for Tripo3D 3D model generation
