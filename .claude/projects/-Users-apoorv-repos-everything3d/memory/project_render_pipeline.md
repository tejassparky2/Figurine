---
name: Render pipeline
description: Photo-to-render automation using fal.ai APIs
type: project
---

## Photo → Styled Render Pipeline

Automates converting client photos into funko pop (or other style) figurine renders using fal.ai APIs.

### Quick Start — What to tell Claude

"I have a folder of client photos at `figurines/<folder_name>/`. Run the render pipeline on it — BG removal, funko pop renders (medium quality), spectacles detection & fix, and generate a review PDF. FAL_KEY is `<key>`."

The steps Claude should run (all from `figurines/` directory):

```bash
# Load API keys (stored in figurines/.env, gitignored)
export $(cat figurines/.env | xargs)

# Step 1: Remove backgrounds (parallel, free)
python remove_bg.py <folder>

# Step 2: Generate funko pop renders (parallel, ~$0.05/image at medium)
python generate_render.py <folder>_nobg -q medium

# Step 3: Detect spectacles in source images
python detect_spectacles.py <folder>_nobg -o /tmp/specs.json

# Step 4: Fix spectacles — copy detected ones to temp, run fix, copy back
mkdir -p /tmp/specs_fix_input
# For each name with specs=true in specs.json:
cp "<folder>_nobg_renders/<name>.png" /tmp/specs_fix_input/
python generate_render.py /tmp/specs_fix_input -s fix_spectacles -q medium -o /tmp/specs_fix_output
cp /tmp/specs_fix_output/*.png <folder>_nobg_renders/

# Step 5: Generate review PDF
python make_review_pdf.py <folder>_nobg <folder>_nobg_renders -o <client>_review.pdf --title "<Client> - Funko Pop Figurines"
```

After client approval, run 3D conversion:
```bash
TRIPO_API_KEY="..." python image_to_3d.py <folder>_nobg_renders -o <output_dir> --height 120
```

### Scripts (all in `figurines/`)

1. **`remove_bg.py`** — Background removal using fal.ai BiRefNet (Portrait model)
   - Supports: jpg, jpeg, png, webp, heic (via sips), pdf (via pymupdf)
   - Outputs white background + auto-cropped PNGs
   - Parallel (default 5 workers, `-w` to change)
   - `FAL_KEY=... python remove_bg.py <input_dir> [-o output_dir] [-n limit]`

2. **`generate_render.py`** — Styled render generation using GPT-image-2 via fal.ai
   - Parallel processing with ThreadPoolExecutor (default 5 workers)
   - Built-in 1 retry on failure (content policy can be flaky)
   - Styles stored in `PROMPTS` dict (currently: `funko`, `fix_spectacles`)
   - Quality tiers: low ($0.006), medium ($0.053), high ($0.211) per image
   - `FAL_KEY=... python generate_render.py <nobg_dir> [-s style] [-q quality] [-n limit]`

3. **`detect_spectacles.py`** — VLM-based spectacles detection using fal.ai any-llm/vision
   - Uses Gemini Flash Lite ($0.01/request)
   - Outputs JSON mapping name → has_spectacles boolean
   - `FAL_KEY=... python detect_spectacles.py <nobg_dir> [-o results.json]`

4. **`make_review_pdf.py`** — Before/after PDF generator for client review
   - A4 landscape, one person per page, name from filename
   - Images compressed to JPEG 80% quality, max 800px for small file size
   - `python make_review_pdf.py <before_dir> <render_dir> [-o output.pdf] [--title "..."]`

5. **`image_to_3d.py`** — Batch 3D model generation using Tripo API
   - Parallel task submission, native 3MF conversion, height scaling
   - 25 credits per figurine (20 model + 5 convert, no texture/PBR)
   - `TRIPO_API_KEY=... python image_to_3d.py <renders_dir> -o <output_dir> --height 120`

### Naming Convention
- Input folder: `<folder>/` (e.g. `actual_images_sagility/`)
- BG removed: `<folder>_nobg/` (auto-created)
- Renders: `<folder>_nobg_renders/` (auto-created)
- 3MF output: separate output dir (e.g. `sagility_output/`)
- Filenames = person names (from input filenames), carried through all steps

### API Keys & Costs
- **FAL_KEY** env var — for BG removal, render generation, spectacles detection
- **TRIPO_API_KEY** env var — for 3D model generation
- Both stored in `figurines/.env` (gitignored). Load with: `export $(cat figurines/.env | xargs)`
- BG removal: ~free (BiRefNet)
- Render generation: $0.006-$0.211/image depending on quality
- Spectacles detection: $0.01/image
- 3D generation: 25 Tripo credits per figurine
- Typical batch of 21 at medium quality: ~$1.30 for renders + 525 Tripo credits for 3D

### Future
- Unify into single orchestrator script (`photo_to_render.py`)
- Auto-fix spectacles without manual copy step
- Web-based review page (renders.everything3dindia.com) instead of PDF
- Add more styles (pixar, etc.) with proportion adjustment pass
