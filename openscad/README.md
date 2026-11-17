# OpenSCAD Notes

## Name-sign piggy banks — two designs

Both are live and supported; customers pick one. Same body/coin mechanism, the
difference is the font and how the name is built.

| | **2-color** | **3-layer** |
|---|---|---|
| File | `piggybankGenerator_veera.scad` | `piggybankGenerator_veera_3layer.scad` |
| Font | Baby Donuts | Spicy Sale |
| Name | flat letters on the plate | darker outline rim + lighter letter face |
| Colors | 2 (box, name) | 3 (box, rim, face) |
| Width knob | `textSize` | `textSize` + `nameXScale` |

Generate either one with the batch script:

```bash
python scripts/generate_piggybanks.py names.txt -o out/ --design 2color
python scripts/generate_piggybanks.py names.txt -o out/ --design 3layer
```

`--format` is `3mf` (colored) by default, `stl` for geometry only. `--colors`
bakes a group's palette into the combined file, in swatch order.

### Short names

Names of 4 characters or fewer would give an awkwardly small bank body, so they
get their `letterSpacing` nudged to **1.2** (`--short-spacing` to change). Both
designs accept `letterSpacing`.

This replaced the old `<< NAME >>` bracket padding, dropped 2026-07-28 — it
printed badly and *oversized* the bank rather than merely padding it:
`<< Hiya >>` came out 218 mm, wider than a normal 6-letter name (Prisha, 157 mm).
Spacing 1.2 puts Hiya at 129 mm.

### Why `nameXScale` exists (3-layer only)

Spicy Sale is a very wide face — "Karnika" at `textSize=40` comes out 265 mm,
wider than a 256 mm bed. Shrinking `textSize` fixes the width but also makes the
letters short and stubby. `nameXScale` condenses the glyphs in **X only**, so the
sign narrows while letter height stays put:

| | width | letter height |
|---|---|---|
| `textSize=40`, no squish | 265 mm | 45.5 mm |
| `textSize=30` | 199 mm | 34.1 mm |
| **`textSize=40`, `nameXScale=0.75`** | **204 mm** | **45.5 mm** |

It is applied inside `name_text()`, which every part of the name routes through,
*before* the padding and rim offsets — so the rim and border keep an even
thickness instead of being squished with the letters. The downward tenon that
seats the name into the plate uses the same helper, so the parts still fit.

## Two color-export strategies — pick by slicer workflow

- **Separate object per color** (keychains, anything where you assign a filament
  per part in the slicer) — use `--enable=lazy-union` + `material-type=basematerial`.
  See [Exporting separate objects per color](#exporting-separate-objects-per-color).
- **Single object with per-triangle colors** — use `material-type=color`.
  See [Exporting 3MF with per-triangle colors](#exporting-3mf-with-per-triangle-colors).

## Exporting separate objects per color

For models where each `color()` part should be its own object so you can assign a
filament/color per object in the slicer (e.g. the name keychains in `keychains/`):

```bash
/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD \
  --enable=textmetrics --enable=lazy-union \
  -O export-3mf/material-type=basematerial \
  -o output.3mf \
  input.scad
```

- **`--enable=lazy-union`** — keeps each top-level object separate instead of
  fusing them into one. Success output reads `Top level object is a list of objects`.
- **`material-type=basematerial`** — each object gets its own material.
- Verify object count: `unzip -p output.3mf 3D/3dmodel.model | grep -c '<object '`.
- Override a parameter without editing the file: `-D 'name_text="Rishaan"'`.

## Exporting 3MF with per-triangle colors

To export a multi-color `.scad` file to `.3mf` with per-triangle colors (single
merged object):

```bash
/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD \
  --enable=textmetrics \
  -O export-3mf/material-type=color \
  -o output.3mf \
  input.scad
```

Key settings:

- **`-O export-3mf/material-type=color`** — Use `color` instead of the default `basematerial`. `basematerial` embeds color data but most slicers/viewers ignore it.
- **`--enable=textmetrics`** — Required for `.scad` files that use `textmetrics()`. Only enable what you need — `--enable=all` causes the export to produce separate objects per `color()` call, which triggers a "multiple objects at different heights" dialog in slicers.

### Other useful 3MF export options

All settable via `-O export-3mf/<key>=<value>`:

| Key | Default | Notes |
|-----|---------|-------|
| `color-mode` | `model` | `none` to strip colors, `selected-only` for partial |
| `unit` | `millimeter` | Also: `micron`, `centimeter`, `meter`, `inch`, `foot` |
| `decimal-precision` | `6` | Range 1–16 |
| `color` | `#f9d72c` | Default color for uncolored geometry |

### Known slicer issues

- **Snapmaker Luban / Bambu Studio** — These slicers may not display per-triangle colors from 3MF files correctly (model appears uncolored). The exported 3MF is fine — try opening in a different slicer (e.g. PrusaSlicer, OrcaSlicer) to verify colors are present.
