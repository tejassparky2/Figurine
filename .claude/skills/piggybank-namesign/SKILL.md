---
name: piggybank-namesign
description: Produce a name-sign piggy bank order — one 3D-printable colored 3MF per name, laid out and combined per colour group. Use whenever the user asks for "name signs", "namesigns", "name-sign piggy banks", "piggy banks with names", "make N piggy banks", or gives a list of names + colours (e.g. "2 layer, yellow and blue, 10 signs"). This is a DIFFERENT product from the `nameplates/` desk plaques — see "Not this" below.
---

# Piggy Bank Name Sign

A list of names + a colour choice → a folder of slicer-ready colored 3MFs: one bank
per name plus a combined file per colour group, with a README. The bank body is
shaped along the name; the name itself is the "sign".

Driven entirely by `scripts/generate_piggybanks.py` — do **not** hand-build geometry
or invent a new generator.

## Not this ⚠️
The word "sign" collides with `nameplates/`, a **separate** product (flat desk plaques
built from an SVG logo — podium / xcelerate / sagility). "name sign" / "namesign" /
"piggy bank" almost always means THIS skill. Only touch `nameplates/` if the user
explicitly says desk plaque / podium / logo plate.

## Two designs — the customer picks one

| | **2color** (default) | **3layer** |
|---|---|---|
| `--design` | `2color` | `3layer` |
| SCAD | `openscad/piggybankGenerator_veera.scad` | `openscad/piggybankGenerator_veera_3layer.scad` |
| Font | **Baby Donuts** | **Spicy Sale** |
| Name | flat letters on the plate | darker outline rim + lighter letter face |
| Colours (order for `--colors`) | box, name | box, rim, face |
| Objects per bank | 3 (box body, coin lid, name plate) | 3 (box, outline, face) |
| Extra knobs | — | `nameXScale` (X-squish, default 0.75), `--back-text` |

"**2 layer**" / "**2 color**" → `--design 2color`. "**3 layer**" → `--design 3layer`.

## Standard palette
- **girls** — box Purple `#7A3FAE` / name Pink `#F07DB0`
- **boys**  — box Blue `#2E6FDB` / name Yellow `#F2C200`
- "**yellow and blue**" = the boys palette: **blue box `#2E6FDB`, yellow name `#F2C200`**
  (colours bake in `box,name` order; flip to `#F2C200,#2E6FDB` for yellow box / blue name).

`--colors` bakes a group's palette into that group's **combined** file only. Individual
files keep the .scad defaults (teal box / orange name) for slicer-side swapping.

## How to run — one invocation per colour group

Split names by colour group into `<group>_names.txt` (one name per line), then:

```bash
python scripts/generate_piggybanks.py girls_names.txt -o girls --design 2color --colors "#7A3FAE,#F07DB0"
python scripts/generate_piggybanks.py boys_names.txt  -o boys  --design 2color --colors "#2E6FDB,#F2C200"
```

If everyone shares one palette (e.g. "just yellow and blue, 10 signs"), use a **single
group** — name it `banks` (`banks_names.txt`, `-o banks`). Don't force a girls/boys split
the user didn't ask for.

`--format` is `3mf` (colored) by default; `stl` for geometry only. The script auto-writes
`<group>/combined.3mf` when a group has >1 name.

## Output location & structure — CONVENTION, follow exactly
- Output goes in the **MAIN repo**: `piggybank_orders/YYYY-MM-DD_<count>/`.
  **Never a worktree.** That tree is gitignored (regenerate from the .scad any time).
  Pass an absolute `-o` into the main repo, and run the main-repo copy of the script
  (`/Users/apoorv/repos/everything3d/scripts/generate_piggybanks.py`) so its `REPO_ROOT`
  resolves to the main repo.
- Per order folder:
  ```
  <group>_combined.3mf     # top level — mv up from <group>/combined.3mf
  <group>/                 # individual banks, one per name
  <group>_names.txt
  README.md
  ```
- **After generating, rename each `<group>/combined.3mf` → `<group>_combined.3mf`** at the
  top level.

## Short names
Names ≤4 chars get **`letterSpacing 1.2`** automatically (a 4-char name at spacing 1.0
gives an awkwardly small body). `--short-spacing` changes the amount, `--short-len` the
cutoff. **Do NOT reintroduce `<< NAME >>` bracket padding** — dropped 2026-07-28, it
printed badly and *oversized* the bank (`<< Hiya >>` → 218 mm, wider than a 6-letter name).

## 3-layer specifics
- The look customers pick: **white middle rim** (`fontColor2` = `#FFFFFF`) between box and
  letter face. Colour order is **box, rim, face**.
- `--back-text "From Karnika"` engraves a line 0.4 mm into the underside (3layer only; the
  2color design has no `backText` — the script errors if you pass it there). `{name}` is
  substituted per bank, e.g. `--back-text "From {name}"`.
- Spicy Sale is very wide; `nameXScale` (default 0.75) condenses glyphs in X so the sign
  fits the bed without shrinking letter height. Only tune it if a long name overflows ~256 mm.

## Validate before handoff
```bash
cd piggybank_orders/YYYY-MM-DD_<count>
unzip -p <group>_combined.3mf 3D/3dmodel.model | grep -c '<object '          # = 3 × (#names)
unzip -p <group>/<Name>.3mf   3D/3dmodel.model | grep -c '<object '          # = 3
unzip -p <group>_combined.3mf 3D/3dmodel.model | python3 -c "import sys,xml.dom.minidom as m; m.parseString(sys.stdin.buffer.read()); print('OK')"
unzip -p <group>_combined.3mf 3D/3dmodel.model | grep -oE '<base name="[^"]*" displaycolor="[^"]*"'
```
Expect: object count = 3 per bank; XML well-formed; `Color 1`/`Color 2`(/`Color 3`) = the
group palette. A third swatch `Default #F9D72C` is OpenSCAD's standard unused placeholder —
**not** a defect. Banks lay out in a row (distinct increasing X offsets in `<build>`).

## Preview (optional, to eyeball a name)
```bash
/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD --enable=textmetrics \
  -D 'name="Harper"' -D 'mode="preview"' \
  --camera=0,0,0,55,0,25,600 --viewall --autocenter --imgsize=1000,700 \
  --colorscheme=Tomorrow -o preview.png openscad/piggybankGenerator_veera.scad
```
Preview shows the .scad default teal/orange, not the baked order palette — that's expected.

## Write the order README
Mirror prior orders (`piggybank_orders/2026-07-28_12/README.md` is a good template): design +
font, per-group name list with short-name flags, baked colours, file list, and a "Regenerate"
block with the exact commands. It's the only record of the palette chosen for the order.

## Handoff
Report: order folder path, design, groups with their palettes, per-group counts, any
short-name spacing bumps, and validation results. Send a preview PNG if useful.

## Background
Full rationale in `openscad/README.md` ("Name-sign piggy banks — two designs"). The 3MF
colour-export trick (lazy-union + basematerial, per-triangle material regions) is shared with
the keychains — see `openscad/README.md` "Exporting separate objects per color".
