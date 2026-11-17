// ===========================================
// Desk Nameplate Generator
// ===========================================
// 1. Place SVG in svgs/, set svg_file
// 2. Update SVG metrics below — run: uv run scripts/svg_bounds.py <svg>
// 3. Tweak target_total_width / leg as needed
// 4. Preview with F6. Export multi-color 3MF with:
//      uv run scripts/build_3mf.py
//    (the GUI "Export 3MF" merges colors into one object — Bambu prints it
//     as a single filament. The script splits via --enable=lazy-union.)
// ===========================================

// -- FILE --
svg_file = "svgs/consciousengines.svg";

// -- SVG METRICS (re-run scripts/svg_bounds.py whenever the SVG changes) --
// All in SVG user units (top-left origin, y grows downward).
svg_native_width       = 708;     // viewBox / content width
svg_native_height      = 192;     // viewBox / content height
svg_baseline_y         = 89;      // y of upper-row baseline (where letters w/o descender bottom out)
svg_descender_bottom_y = 191;     // y of lowest visible point (g/p/q/y descender)

// -- TARGET SIZE (mm) --
target_total_width = 440;         // total finished width incl. border. Must fit build plate.

// -- DIMENSIONS (mm) --
base_height   = 20;               // slab thickness — becomes depth when sign stands
text_height   = 5;                // letter rise above the slab
border        = 5;                // border around the closed text
offset_amount = 12;              // hole-fill amount for close-op (~15 SVG units at this scale)

// -- LEG (left-side support) --
// A vertical bar whose bottom drops to the same level as the 'g' descender,
// so the leg + the 'g' both touch the desk and the sign sits flat. The horizontal
// position is given in SVG units; for consciousengines, the stylized "on" of
// "conscious" sits at svg_x ≈ 64–160 (center 112).
leg_x_center_svg = 112;           // SVG units — horizontal center of leg
leg_width        = 0;             // mm — extra width *before* the border offset.
                                  //      Final printed leg width = leg_width + 2*border.
                                  //      0 → leg is just the border halo (= 2*border wide).

// -- RESOLUTION --
smoothness = 150;                 // 60 quick / 120+ for export

// ===========================================

// SVG width/height in mm after resize (preserves aspect ratio).
svg_w_mm = target_total_width - 2 * border;
svg_h_mm = svg_w_mm * svg_native_height / svg_native_width;

// Import + force-resize: makes 1 SVG-unit a known fraction of mm regardless of
// OpenSCAD's dpi interpretation. center=true puts content bbox at origin.
module svg_shape() {
    resize([svg_w_mm, 0], auto = [false, true])
        import(svg_file, center = true);
}

module closed_svg() {
    offset(delta = -offset_amount, $fn = smoothness)
        offset(delta = +offset_amount, $fn = smoothness)
            svg_shape();
}

// SVG (x, y) (top-left origin, y-down) → OpenSCAD (x, y) in mm (centered, y-up).
function svg_x_mm(x_svg) = svg_w_mm * (x_svg / svg_native_width - 0.5);
function svg_y_mm(y_svg) = svg_h_mm * (0.5 - y_svg / svg_native_height);

module leg_2d() {
    x_center = svg_x_mm(leg_x_center_svg);
    y_top    = svg_y_mm(svg_baseline_y);
    y_bot    = svg_y_mm(svg_descender_bottom_y);
    // Clamp width to a tiny epsilon so leg_width = 0 still produces a valid
    // polygon (square([0, H]) is degenerate and offset() gives empty geometry).
    w = max(leg_width, 0.001);
    translate([x_center - w / 2, y_bot])
        square([w, y_top - y_bot]);
}

module base_2d() {
    offset(r = border, $fn = smoothness)
        union() {
            closed_svg();
            leg_2d();
        }
}

module base_slab() { linear_extrude(base_height) base_2d(); }

module raised_text() {
    translate([0, 0, base_height])
        linear_extrude(text_height)
            svg_shape();
}

// 3MF multi-material export: each color() block becomes a separate part.
// Slicer (Bambu Studio / OrcaSlicer) maps these to filaments.
color("white") base_slab();
color("black") raised_text();
