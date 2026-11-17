"""
Build a multi-color 3MF that Bambu Studio recognizes as separate parts AND
auto-assigns to the right filaments on import (no manual fix-up).

Why this script exists
----------------------
There are three problems we have to solve, in order:

1. OpenSCAD's default 3MF export merges every top-level statement into a single
   <object>. The colors are encoded as per-triangle p1 attributes, but Bambu
   Studio only honors object-level color, so the whole thing prints in one
   filament.
   → Fix: render with --enable=lazy-union so each top-level color() block
     becomes its own <object>.

2. After lazy-union, each <object> still carries pindex="0" (the yellow
   Default). The triangles know which color they are; the object header
   doesn't.
   → Fix: scan each object's triangles, find the dominant p1, and set the
     object's pindex to match. Now Bambu shows the right color in the plate
     preview.

3. Bambu Studio still maps every imported object to filament 1 by default. The
   pindex tells it the *intended* color but not which slot to print from.
   → Fix: write Metadata/model_settings.config mapping each object id to an
     extruder index (1, 2, ...). Bambu reads this on import and assigns
     filaments automatically.

Convention: pindex N → extruder N, matching the order of color() blocks in the
SCAD file. So load filament 1 = white (first color), filament 2 = black.

Usage
-----
    uv run scripts/build_3mf.py
    # or with explicit paths:
    uv run scripts/build_3mf.py path/to/file.scad exports/out.3mf
"""

import json
import os
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT  = Path(__file__).parent.parent
DEFAULT_OPENSCAD_PATHS = [
    "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    str(Path.home() / "Desktop/OpenSCAD.app/Contents/MacOS/OpenSCAD"),
]
OPENSCAD = os.environ.get("OPENSCAD") or next(
    (p for p in DEFAULT_OPENSCAD_PATHS if Path(p).exists()),
    DEFAULT_OPENSCAD_PATHS[0],
)

# 3MF namespaces — register so ET.tostring preserves them on round-trip.
NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS_MAP = {
    "":   NS_CORE,
    "p":  "http://schemas.microsoft.com/3dmanufacturing/production/2015/06",
    "m":  "http://schemas.microsoft.com/3dmanufacturing/material/2015/02",
    "b":  "http://schemas.microsoft.com/3dmanufacturing/beamlattice/2017/02",
    "s":  "http://schemas.microsoft.com/3dmanufacturing/slice/2015/07",
    "t":  "http://schemas.microsoft.com/3dmanufacturing/trianglesets/2021/07",
    "sc": "http://schemas.microsoft.com/3dmanufacturing/securecontent/2019/04",
    "v":  "http://schemas.3mf.io/3dmanufacturing/volumetric/2022/01",
    "i":  "http://schemas.3mf.io/3dmanufacturing/implicit/2023/12",
}
for prefix, ns in NS_MAP.items():
    ET.register_namespace(prefix, ns)


def render_scad(scad_path: Path, out_3mf: Path) -> None:
    print(f"Rendering {scad_path.name} → {out_3mf}")
    subprocess.run(
        [OPENSCAD, "--enable=lazy-union", "--enable=textmetrics",
         "-o", str(out_3mf), str(scad_path)],
        check=True,
    )


def patch_object_pindex(threemf_path: Path) -> None:
    """Patch the 3MF in-place:
       1. Set each <object>'s pindex to its triangles' dominant p1.
       2. Wrap the per-color mesh objects under one assembly <object> so Bambu
          Studio imports them as a single object with parts (no "load as
          single object?" prompt on import).
       3. Add Metadata/model_settings.config mapping each part to an extruder
          so Bambu auto-assigns filaments.
       4. Add Metadata/project_settings.config declaring filament_colour
          explicitly, so Bambu uses our colors in our order instead of
          merging with the user's existing filament slots.
    """
    with zipfile.ZipFile(threemf_path, "r") as z:
        members = {name: z.read(name) for name in z.namelist()}

    model_xml = members["3D/3dmodel.model"]
    root = ET.fromstring(model_xml)

    # Extract pindex → color from <basematerials>. pindex is 0-based position
    # in the basematerials list; element 0 is OpenSCAD's unused "Default"
    # entry, real colors start at index 1.
    pindex_to_color: dict[str, str] = {}
    bm = root.find(f".//{{{NS_CORE}}}basematerials")
    if bm is not None:
        for i, base in enumerate(bm.findall(f"{{{NS_CORE}}}base")):
            displaycolor = base.get("displaycolor") or "#FFFFFF"
            pindex_to_color[str(i)] = displaycolor[:7]  # drop alpha

    objects = root.findall(f".//{{{NS_CORE}}}object")
    if not objects:
        raise RuntimeError("No <object> elements found in 3MF")

    # Step 1: set object pindex from triangles, and remember object→pindex mapping.
    object_pindex: dict[str, str] = {}
    for obj in objects:
        triangles = obj.findall(f".//{{{NS_CORE}}}triangle")
        p1_counts = Counter(t.get("p1") for t in triangles if t.get("p1"))
        if not p1_counts:
            print(f"  object {obj.get('id')}: no per-triangle color, skipping")
            continue
        dominant, count = p1_counts.most_common(1)[0]
        obj.set("pindex", dominant)
        object_pindex[obj.get("id")] = dominant
        print(
            f"  object {obj.get('id')} ({obj.get('name')}): pindex → {dominant} "
            f"({count} of {sum(p1_counts.values())} triangles)"
        )

    # Step 2: wrap mesh objects under one assembly object via <components>, and
    # replace <build> items with a single item referencing the assembly. Bambu
    # treats it as one object with parts → no "load as single object?" prompt.
    resources = root.find(f".//{{{NS_CORE}}}resources")
    build = root.find(f".//{{{NS_CORE}}}build")
    if resources is None or build is None:
        raise RuntimeError("3MF missing <resources> or <build>")

    part_ids = list(object_pindex.keys())
    assembly_id = str(max(int(obj.get("id") or "0") for obj in objects) + 1)

    assembly = ET.SubElement(resources, f"{{{NS_CORE}}}object")
    assembly.set("id", assembly_id)
    assembly.set("type", "model")
    assembly.set("name", threemf_path.stem)
    components = ET.SubElement(assembly, f"{{{NS_CORE}}}components")
    for pid in part_ids:
        comp = ET.SubElement(components, f"{{{NS_CORE}}}component")
        comp.set("objectid", pid)

    for item in list(build.findall(f"{{{NS_CORE}}}item")):
        build.remove(item)
    new_item = ET.SubElement(build, f"{{{NS_CORE}}}item")
    new_item.set("objectid", assembly_id)

    members["3D/3dmodel.model"] = ET.tostring(root, xml_declaration=True, encoding="UTF-8")

    # Step 3: write Bambu's filament assignment as nested <part> entries under
    # the assembly object. Convention: extruder index = pindex.
    config_lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    config_lines.append(f'  <object id="{assembly_id}">')
    config_lines.append(f'    <metadata key="name" value="{threemf_path.stem}"/>')
    for pid, pindex in object_pindex.items():
        config_lines.append(f'    <part id="{pid}" subtype="normal_part">')
        config_lines.append(f'      <metadata key="extruder" value="{pindex}"/>')
        config_lines.append("    </part>")
    config_lines.append("  </object>")
    config_lines.append("</config>")
    config_lines.append("")
    members["Metadata/model_settings.config"] = "\n".join(config_lines).encode("utf-8")

    # Step 3: declare filaments explicitly so Bambu uses our colors. The N-th
    # filament (1-based) maps to the basematerial at index N (skipping the
    # unused Default at index 0).
    used_pindexes = sorted({int(p) for p in object_pindex.values()})
    n = max(used_pindexes) if used_pindexes else 0
    filament_colour = [
        pindex_to_color.get(str(i), "#FFFFFF") for i in range(1, n + 1)
    ]
    project_config = {
        "filament_colour":      filament_colour,
        "filament_type":        ["PLA"] * n,
        "filament_ids":         ["GFL99"] * n,
        "filament_settings_id": ["Generic PLA"] * n,
        "filament_self_index":  [str(i) for i in range(1, n + 1)],
    }
    members["Metadata/project_settings.config"] = json.dumps(
        project_config, indent=4
    ).encode("utf-8")
    print(f"  filament_colour: {filament_colour}")

    # Register .config in [Content_Types].xml (otherwise some readers warn).
    ct_xml = members["[Content_Types].xml"].decode("utf-8")
    if 'Extension="config"' not in ct_xml:
        ct_xml = ct_xml.replace(
            "</Types>",
            '\t<Default Extension="config" ContentType="application/xml"/>\n</Types>',
        )
        members["[Content_Types].xml"] = ct_xml.encode("utf-8")

    # Repack. [Content_Types].xml must be the first entry in the archive --
    # it is an OPC requirement, and strict readers reject the package without
    # it (verify_3mf.py checks for exactly this).
    order = ["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"]
    names = [n for n in order if n in members] + [
        n for n in members if n not in order
    ]
    with zipfile.ZipFile(threemf_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, members[name])


def main() -> int:
    scad_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "nameplate-offset.scad"
    out_path  = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT / "exports" / "nameplate.3mf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    render_scad(scad_path, out_path)
    patch_object_pindex(out_path)
    print(f"Done: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
