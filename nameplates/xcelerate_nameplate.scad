// ============================================================
// Xcelerate Batch 2024 — Award Nameplate
// ============================================================

// ---- Plate ----
length = 109;
width  = 49;
height = 1;
radius = 2.5;
$fn    = 64;

// ---- Text heights ----
text_height = 0.5;       // how far text/logo is raised above plate

// ---- Logo ----
logo_file = "sagility-logo-solid.svg";
logo_hole_file = "sagility-logo-g-hole.svg";
logo_svg_width  = 149.81;   // from viewBox
logo_svg_height = 41.2;
logo_scale = 1.2;          // scale factor to fit on plate
logo_x = 60;                 // horizontal offset from center (positive = right)
logo_y = 28;                // vertical offset from center (positive = up)

// ---- Name ----
name_text = "Harish Mitra";
name_font = "Cookie";
name_size = 10;
name_bold = 0.15;           // offset thickening (mm)
name_y = -5;                // vertical position

// ---- Award line ----
award_text = "Xcelerate Batch 2024";
award_font = "Lexend Deca";
award_size = 5;
award_bold = 0.08;
award_y = -17;

// ---- Margins ----
name_margin = 4;            // mm clear space at each end

// ============================================================
// Computed sizes (auto-shrink if text is too wide)
// ============================================================

function text_width(txt, size, font) =
    txt == "" ? 0
    : textmetrics(text=txt, size=size, font=font).size[0] + 2*name_bold;

function shrink_to_fit(txt, base_size, font, max_width, bold) =
    let(natural = textmetrics(text=txt, size=base_size, font=font).size[0] + 2*bold)
    natural > max_width ? base_size * max_width / natural : base_size;

name_fit_size  = shrink_to_fit(name_text, name_size, name_font,
                               length - 2*name_margin, name_bold);
award_fit_size = shrink_to_fit(award_text, award_size, award_font,
                               length - 2*name_margin, award_bold);

// ============================================================
// Modules
// ============================================================

module plate() {
    linear_extrude(height = height)
        offset(r = radius)
            offset(delta = -radius)
                square([length, width], center = true);
}

module bold_text(txt, size, font, bold, y_pos) {
    translate([0, y_pos, height])
        linear_extrude(height = text_height)
            offset(r = bold)
                text(txt, size = size, font = font,
                     halign = "center", valign = "center");
}

module logo() {
    logo_w = logo_svg_width * logo_scale;
    logo_h = logo_svg_height * logo_scale;
    translate([logo_x - logo_w/2, logo_y - logo_h/2, height])
        linear_extrude(height = text_height)
            difference() {
                scale([logo_scale, logo_scale, 1])
                    import(logo_file, center = false);
                scale([logo_scale, logo_scale, 1])
                    import(logo_hole_file, center = false);
            }
}

// ============================================================
// Assembly
// ============================================================

color("WhiteSmoke") plate();
color("DarkGreen")  logo();
color("Black") {
    bold_text(name_text, name_fit_size, name_font, name_bold, name_y);
    bold_text(award_text, award_fit_size, award_font, award_bold, award_y);
}
