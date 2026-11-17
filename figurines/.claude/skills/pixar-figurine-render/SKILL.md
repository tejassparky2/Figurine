---
name: pixar-figurine-render
description: Turn a client photo into stylized Pixar/DreamWorks 3D-figurine renders and a before/after review PDF. Use whenever the user wants a "pixar style render", "figurine render", "funko render", N "options/variants" from a photo, or to send a client a render PDF for approval. Runs the figurines/ pipeline (bg removal → GPT-image-2 render → review PDF). Stops before 3D printing.
---

# Pixar Figurine Render

End-to-end pipeline that converts a source photo into stylized figurine renders and a client-facing review PDF. Used by the figurines business to get a render approved **before** spending Tripo credits on actual 3D.

## When to use
- "make a pixar style render" / "funko render" / "figurine render" from a photo
- "2 options", "give me a few variants", "render PDF to send the client"
- Source is usually the latest photo in `~/Downloads` (the user often refers to it by a short name like `client-jun17`).

## Hard rules
- **Never run 3D generation (`scripts/image_to_3d.py`, Tripo) until the user approves a render.** It costs credits. Renders + PDF only, then stop and ask which option to take to 3D.
- Once a render **is** approved and the user asks for the model: plain single-color → `scripts/image_to_3d.py` (README Pipeline C); multi-color/N-filament → use the **`figurine-colorize`** skill (README Pipeline D), which is a different set of Tripo calls, not a post-step.
- Run everything from the `figurines/` directory.
- All scripts need `FAL_KEY`. It lives in `figurines/.env` — load it first: `set -a; source .env; set +a`.

## Project layout convention
One folder per job under `projects/<name>/`:
```
projects/<name>/
  input/        # original source photo(s), copied in
  nobg/         # background-removed PNGs
  renders/      # raw rendered variants: <name>_v1.png, <name>_v2.png, ...
  renders_fixed/ # head-enlarged variants (proportion_fix) — this is what ships
  review.pdf    # before/after deliverable sent to client (built from renders_fixed)
```
`<name>` is a short slug (e.g. `client-jun17`, `devanshi`). One photo per person; multiple people = multiple files in `input/`.

## Pipeline

```bash
cd /Users/apoorv/repos/everything3d/figurines
set -a; source .env; set +a              # load FAL_KEY

NAME=client-jun17                          # job slug
mkdir -p projects/$NAME/input
cp ~/Downloads/<photo>.jpeg projects/$NAME/input/

# 1. Remove background
python3 scripts/remove_bg.py projects/$NAME/input -o projects/$NAME/nobg

# 2. Render variants (default: pixar, medium quality, 2 variants)
#    NOTE: default to -q medium to control cost. gpt-image 'high' is ~3-4x the
#    price and every pixar job is TWO passes (render + proportion_fix), so 'high'
#    everywhere = 4 high-tier gens/person. Only use -q high on the FINAL pose the
#    client has approved.
python3 scripts/generate_render.py projects/$NAME/nobg -o projects/$NAME/renders \
  -s pixar -q medium -v 2

# 3. ALWAYS enlarge the head — the base pixar render comes out too realistic in
#    proportion. Run proportion_fix on the renders into renders_fixed. This is a
#    REQUIRED step for pixar, not optional. (Skip only for pets → see below.)
python3 scripts/generate_render.py projects/$NAME/renders -o projects/$NAME/renders_fixed \
  -s proportion_fix -q medium

# 4. LOOK at renders_fixed (Read each PNG) before building the PDF — check the head
#    is clearly oversized (~40%), likeness, clothing colors, no stray text/logos/base.

# 5. Before/after review PDF — built from renders_fixed, NOT renders
python3 scripts/make_review_pdf.py projects/$NAME/nobg projects/$NAME/renders_fixed \
  -o projects/$NAME/review.pdf \
  --source-dir projects/$NAME/input \
  --title "Pixar-Style Figurine Render - Review"
```

Then send the PDF with `SendUserFile` and ask the user to pick an option.

## Script reference

**`generate_render.py <input_dir>`** (renders via fal.ai GPT-image-2)
- `-s/--style`: `pixar` (DreamWorks figurine, big head), `funko` (Funko Pop, arms folded), `proportion_fix` (enlarge head, fix existing render), `proportion_fix_pet` (keep natural head size for pets), `fix_spectacles` (make glasses black/thick). Default `funko` — **pass `-s pixar` for pixar requests.**
- `-q/--quality`: `low|medium|high` (default `medium`. `high` costs ~3-4x — reserve it for the final approved pose, not drafts).
- `-v/--variants`: number of options per image (default 1; use `2` for "options").
- `-e/--extra`: extra text appended to prompt, e.g. clothing details ("red saree with gold border").
- `-o/--output-dir`, `-w/--workers`, `-n/--limit`.
- Skips outputs that already exist — delete a variant PNG to regenerate it.

**`remove_bg.py <input_dir>`** — fal.ai BiRefNet. `-o` output dir (default `<input_dir>_nobg`).

**`make_review_pdf.py <before_dir> <render_dir>`** — `-o` output, `--title`, `--source-dir` (originals on title page). Handles `_vN` variants automatically.

Other scripts in `scripts/` (not part of this flow): `image_to_3d.py` (Tripo — gated, see Hard rules), `glb_to_textured_3mf.py`, `colorize_3mf.py`, `segment_colorize.py`, `extract_people.py` (multi-person photos), `detect_spectacles.py`.

## Iterating on a render
- Bad proportions → rerun on the render with `-s proportion_fix` (head too small) or `-s proportion_fix_pet` (pets).
- Glasses look wrong → `-s fix_spectacles`.
- Wrong clothing color/detail → add `-e "..."` and delete+regenerate the variant.

## Couple / multi-person jobs
- Use `extract_people.py` to split a multi-person photo, or one input file per person.
- Couple figurine print heights: **man 120mm, woman 110mm** (applied later at the 3D stage).
