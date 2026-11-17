// Debug: render imported SVG with axis-aligned reference markers to see where
// `import(center=true)` actually places the geometry.
//
// Render with:
//   /Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD -o /tmp/debug.png \
//     --imgsize=1400,800 --camera=0,0,0,0,0,0,1500 --projection=ortho \
//     scripts/debug_svg_center.scad

linear_extrude(1) import("../svgs/consciousengines.svg", center = true);

// Origin marker (5x5 square at OpenSCAD 0,0)
translate([0, 0, 2]) color("red") cube([5, 5, 5], center = true);

// Markers at expected viewBox extents (svg_w=708, svg_h=192, so half = 354, 96)
for (p = [[-354, 0], [354, 0], [0, 96], [0, -96]])
    translate([p[0], p[1], 2]) color("blue") cube([10, 10, 10], center = true);
