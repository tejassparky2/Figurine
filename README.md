# everything3d
Mono repo for everything3d

## Modules

- [`nameplates/`](nameplates/) — SVG-to-3MF desk nameplate generator. Multi-color 3MF that auto-assigns filaments on Bambu Studio import. See [nameplates/README.md](nameplates/README.md).

## Scripts

### Watermark (`scripts/add_watermark.py`)

Tiles the Everything3D logo across images to prevent unauthorized use.

**Setup:**
```bash
pip install -r scripts/requirements.txt
```

**Usage:**
```bash
# Single image (default: level 1)
python scripts/add_watermark.py photo.jpg
python scripts/add_watermark.py photo.jpg output.jpg

# Entire directory
python scripts/add_watermark.py ./photos/ ./output/

# Level 2 — bigger, denser, full opacity
python scripts/add_watermark.py --level 2 photo.jpg
```

**Levels:**
- `1` (default) — Visible tiled watermark, semi-transparent
- `2` — Aggressive, dense, full-opacity watermark

Output files get a `_watermarked` suffix if no output path is specified.

### Before/After Composite (`scripts/before_after.py`)

Creates a before/after composite by overlaying circular face crops from the
client photo onto the 3D render, with arrows pointing to the figurine.

**Usage:**
```bash
# Single client (1 face)
python scripts/before_after.py client_photo.jpg render.png

# Couple (2 faces) with explicit output
python scripts/before_after.py couple_photo.jpg render.png output.jpg
```

Supports 1 or 2 faces. Output files get a `_before_after` suffix if no
output path is specified.

## OpenSCAD

Parametric piggy bank generator. The bank body is shaped around the name text, with a coin slot on the side and a snap-in coin lid on top.

**Requirements:** OpenSCAD (at `/Users/apoorv/Desktop/OpenSCAD.app` on this machine)

### Files

- `piggybankGenerator_paris.scad` — "Paris" bank, Shrikhand font, full preview (body + coin lid + name lid)
- `piggybankGenerator_veera.scad` — "Veera" bank, Baby Donuts font, modified version with print-mode name lid

### Key parameters (top of each `.scad` file)

| Parameter | Description |
|-----------|-------------|
| `name` | Name to emboss on the bank |
| `font` | Font name (must be installed on your system) |
| `mode` | `"preview"` — upright preview of all parts; `"print"` — name lid flipped for print-in-place |
| `textSize` | Font size (affects overall bank dimensions) |
| `extrudeHeight` | Height of the box |
| `coinSlotWidth/Length` | Dimensions of the coin slot |

### Rendering

```bash
OPENSCAD="/Users/apoorv/Desktop/OpenSCAD.app/Contents/MacOS/OpenSCAD"

# Preview PNG
"$OPENSCAD" --enable=textmetrics --render -D 'mode="preview"' -o out.png piggybankGenerator_veera.scad

# Export STL (use preview mode to get all parts)
"$OPENSCAD" --enable=textmetrics --render -D 'mode="preview"' -o out.stl piggybankGenerator_veera.scad
```

> `--enable=textmetrics` is required — the scad uses the experimental `textmetrics()` function for precise text positioning.

### Batch generation (`scripts/generate_piggybanks.py`)

Generates individual STLs for a list of names and combines them into one file for printing.
Names with 4 or fewer characters are automatically padded — e.g. `HITA` becomes `<< HITA >>` so the bank body isn't too small.

**Usage:**
```bash
python scripts/generate_piggybanks.py names.txt
python scripts/generate_piggybanks.py names.txt -o my_output/
python scripts/generate_piggybanks.py names.txt --font "Shrikhand"
```

`names.txt` is one name per line. Outputs `<name>.stl` per name plus a `combined.stl` with all models arranged side by side.
