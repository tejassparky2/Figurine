#!/usr/bin/env python3
"""Build a clean ONE-object Bambu Studio project template from any saved Bambu project.

colorgroup_to_painted.py clones a template project and swaps its first object for the coloured
mesh. A real saved project usually holds many objects, assemblies and plates (piggybanks_boys.3mf
has 14), and every one of them would be carried into the output. This keeps only what the
converter needs from the source project:

  * Metadata/project_settings.config  (printer profile, filament types, process settings)
  * [Content_Types].xml, _rels/.rels

and writes fresh, minimal versions of the rest: one object (id 2) whose single component points at
3D/Objects/object_1.model (a placeholder tetrahedron), one build item centred on the bed, and a
matching Metadata/model_settings.config with one plate. Personal metadata (Designer,
DesignerUserId, Title...) is dropped.

    python3 scripts/make_bambu_template.py ../piggybanks_boys.3mf -o templates/bambu_a1_single.3mf
    python3 scripts/colorgroup_to_painted.py <colored>.3mf -o <painted>.3mf --template templates/bambu_a1_single.3mf
"""
import argparse
import json
import re
import zipfile
from pathlib import Path

CORE = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
        'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
        'requiredextensions="p">\n')
KEEP_META = ("Application", "BambuStudio:3mfVersion")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="any project 3MF saved by Bambu Studio")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--bed", type=float, default=None,
                    help="bed size in mm for centring (default: from printable_area, else 256)")
    a = ap.parse_args()

    with zipfile.ZipFile(a.source) as z:
        src = {n: z.read(n) for n in z.namelist()}
    for need in ("Metadata/project_settings.config", "3D/3dmodel.model"):
        if need not in src:
            raise SystemExit(f"{a.source.name}: missing {need} — not a Bambu Studio project")
    cfg = json.loads(src["Metadata/project_settings.config"])

    cx = cy = (a.bed or 256.0) / 2
    if a.bed is None and isinstance(cfg.get("printable_area"), list):   # e.g. ["0x0","256x0","256x256","0x256"]
        pts = [tuple(map(float, p.split("x"))) for p in cfg["printable_area"]]
        cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
        cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2

    top_src = src["3D/3dmodel.model"].decode()
    meta = "".join(f' <metadata name="{k}">{v}</metadata>\n'
                   for k, v in re.findall(r'<metadata name="([^"]+)">([^<]*)</metadata>', top_src)
                   if k in KEEP_META)
    T = f"1 0 0 0 1 0 0 0 1 {cx:g} {cy:g} 0"
    top = (CORE + meta + ' <resources>\n'
           '  <object id="2" p:UUID="00000001-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
           '   <components>\n'
           '    <component p:path="/3D/Objects/object_1.model" objectid="1" '
           'p:UUID="00010000-b206-40ff-9872-83e8017abed1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
           '   </components>\n  </object>\n </resources>\n <build p:UUID="2c7c17d8-22b5-4d84-8835-1976022ea369">\n'
           f'  <item objectid="2" p:UUID="00000002-b1ec-4553-aec9-835e5b724bb4" transform="{T}" printable="1"/>\n'
           ' </build>\n</model>\n')
    placeholder = (CORE + ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
                   '  <object id="1" p:UUID="00010000-81cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
                   '   <mesh>\n    <vertices>\n'
                   '     <vertex x="0" y="0" z="0"/>\n     <vertex x="10" y="0" z="0"/>\n'
                   '     <vertex x="0" y="10" z="0"/>\n     <vertex x="0" y="0" z="10"/>\n'
                   '    </vertices>\n    <triangles>\n'
                   '     <triangle v1="0" v2="2" v3="1"/>\n     <triangle v1="0" v2="1" v3="3"/>\n'
                   '     <triangle v1="1" v2="2" v3="3"/>\n     <triangle v1="0" v2="3" v3="2"/>\n'
                   '    </triangles>\n   </mesh>\n  </object>\n </resources>\n <build/>\n</model>\n')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/Objects/object_1.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')
    ms = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <object id="2">\n'
          '    <metadata key="name" value="figurine"/>\n    <metadata key="extruder" value="1"/>\n'
          '    <metadata face_count="4"/>\n    <part id="1" subtype="normal_part">\n'
          '      <metadata key="name" value="figurine"/>\n'
          '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
          '      <metadata key="source_file" value="figurine.3mf"/>\n'
          '      <metadata key="source_object_id" value="0"/>\n      <metadata key="source_volume_id" value="0"/>\n'
          '      <metadata key="source_offset_x" value="0"/>\n      <metadata key="source_offset_y" value="0"/>\n'
          '      <metadata key="source_offset_z" value="0"/>\n      <metadata key="extruder" value="1"/>\n'
          '      <mesh_stat face_count="4" edges_fixed="0" degenerate_facets="0" facets_removed="0" '
          'facets_reversed="0" backwards_edges="0"/>\n    </part>\n  </object>\n'
          '  <plate>\n    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
          '    <metadata key="locked" value="false"/>\n    <model_instance>\n'
          '      <metadata key="object_id" value="2"/>\n      <metadata key="instance_id" value="0"/>\n'
          '      <metadata key="identify_id" value="1"/>\n    </model_instance>\n  </plate>\n'
          '  <assemble>\n'
          f'   <assemble_item object_id="2" instance_id="0" transform="{T}" offset="0 0 0" />\n'
          '  </assemble>\n</config>\n')

    out = {
        "[Content_Types].xml": src.get("[Content_Types].xml"),
        "_rels/.rels": src.get("_rels/.rels"),
        "3D/3dmodel.model": top.encode(),
        "3D/_rels/3dmodel.model.rels": rels.encode(),
        "3D/Objects/object_1.model": placeholder.encode(),
        "Metadata/model_settings.config": ms.encode(),
        "Metadata/project_settings.config": src["Metadata/project_settings.config"],
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as zo:
        for k, v in out.items():           # [Content_Types].xml first, as OPC readers expect
            if v is not None:
                zo.writestr(k, v)
    print(f"Wrote {a.out}: 1 object centred at ({cx:g}, {cy:g}); printer "
          f"{cfg.get('printer_model', cfg.get('printer_settings_id', '?'))}, "
          f"{len(cfg.get('filament_colour', []))} filament slots in source")


if __name__ == "__main__":
    main()
