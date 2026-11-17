#!/usr/bin/env python3
"""Merge several single-model 3MF files (OpenSCAD lazy-union + basematerial
export) into one 3MF, laid out in a row, preserving materials so each part
stays independently colorable in the slicer.

All inputs must share the same <basematerials id="1"> group (they do, when they
come from the same .scad). Object ids are renumbered globally; each source
file's objects get a shared X translation via its <build> item transform.

Swatches are named "Color 1", "Color 2", ... in the OpenSCAD export. Pass
`colors` to override them in order — 2 for the 2-color design (box, name),
3 for the 3-layer design (box, outline rim, letter face).

Usage:
    python scripts/merge_3mf.py OUT.3mf --colors "#7A3FAE,#F07DB0" a.3mf b.3mf
"""
import argparse
import re
import zipfile
from pathlib import Path

GAP = 15.0  # mm between models

CONTENT_TYPES = '''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
\t<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
\t<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
</Types>'''

RELS = '''<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
\t<Relationship Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" Target="/3D/3dmodel.model" Id="rel0"/>
</Relationships>'''

OBJ_RE = re.compile(r'<object\b.*?</object>', re.S)
VX_RE = re.compile(r'<vertex x="([-0-9.eE]+)"')


def read_model(p):
    with zipfile.ZipFile(p) as z:
        return z.read('3D/3dmodel.model').decode('utf-8')


def minmax_x(model):
    xs = [float(x) for x in VX_RE.findall(model)]
    return min(xs), max(xs)


def merge(paths, out_path, colors=None):
    """Merge `paths` into `out_path`. `colors` overrides the Color N swatches."""
    paths = [str(p) for p in paths]
    template = read_model(paths[0])
    header = template[:template.index('<object')]

    for i, hexcolor in enumerate(colors or [], start=1):
        header = re.sub(
            rf'(<base name="Color {i}" displaycolor=")#[0-9A-Fa-f]{{6,8}}(")',
            rf'\g<1>{hexcolor}\g<2>', header)

    next_id = 2
    objects_xml = []
    items = []
    cursor = 0.0
    for p in paths:
        m = read_model(p)
        min_x, max_x = minmax_x(m)
        tx = cursor - min_x
        for obj in OBJ_RE.findall(m):
            obj = re.sub(r'^(<object id=")\d+(")', rf'\g<1>{next_id}\g<2>', obj, count=1)
            objects_xml.append(obj)
            items.append(f'<item objectid="{next_id}" '
                         f'transform="1 0 0 0 1 0 0 0 1 {tx:.4f} 0 0"/>')
            next_id += 1
        cursor += (max_x - min_x) + GAP

    build = '<build>\n' + '\n'.join(items) + '\n</build>'
    model = header + '\n'.join(objects_xml) + '\n</resources>\n' + build + '\n</model>\n'

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', CONTENT_TYPES)
        z.writestr('_rels/.rels', RELS)
        z.writestr('3D/3dmodel.model', model)
    return len(objects_xml)


def main():
    ap = argparse.ArgumentParser(description="Merge colored 3MF files into one")
    ap.add_argument("out", help="Output .3mf")
    ap.add_argument("files", nargs="+", help="Input .3mf files")
    ap.add_argument("--colors", help="Comma-separated hex colors, in swatch order")
    args = ap.parse_args()

    colors = [c.strip() for c in args.colors.split(",")] if args.colors else None
    n = merge(args.files, args.out, colors)
    print(f'{args.out}: {n} objects from {len(args.files)} models')


if __name__ == '__main__':
    main()
