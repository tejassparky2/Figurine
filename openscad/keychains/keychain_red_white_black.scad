// Parametric 3D-printable name keychain badge
// Uses textmetrics() for proper name sizing

// ---------- USER SETTINGS ----------
name_text = "Abeer";

font_size = 10;
font_name = "Racing Sans One:style=Condensed Bold";
text_spacing = 0.95;

// Padding around actual measured text
side_padding = 7.5;

// Main badge sizing
badge_h = 23;
min_badge_w = 55;
corner_r = 8;

// Borders
black_border = 2.8;
red_border = 2.0;

// Keychain hole sizing
hole_d = 3.2;
tab_outer_d = 7.5;
tab_overlap = 3.5;   // how much the tab overlaps into the badge body

// Heights
black_base_h   = 2.0;
white_panel_z   = 1.0;                              // where white starts
white_panel_top = 2.6;                              // where white ends
white_panel_h   = white_panel_top - white_panel_z;

// Raised red features
red_border_h = 1.8;
red_text_h = 2.0;

$fn = 64;


// ---------- MEASURE TEXT PROPERLY ----------
text_m = textmetrics(
    text = name_text,
    size = font_size,
    font = font_name,
    halign = "center",
    valign = "center",
    spacing = text_spacing
);

text_w = text_m.size[0];
text_h = text_m.size[1];


// ---------- DERIVED DIMENSIONS ----------
badge_w = max(min_badge_w, text_w + 2 * side_padding);

hole_r = hole_d / 2;
tab_r = tab_outer_d / 2;

// Tab center: attached to left edge, but hole stays mostly outside the badge body
tab_x = -badge_w/2 - tab_r + tab_overlap;


// ---------- SAFETY CHECKS ----------
assert(hole_d < tab_outer_d - 2.0, "Hole too large for tab.");
assert(corner_r > black_border + red_border, "Corner radius too small for borders.");
assert(text_h < badge_h - 2 * (black_border + red_border), "Text too tall for badge height. Reduce font_size or increase badge_h.");


// ---------- 2D SHAPES ----------
module rounded_rect(w, h, r) {
    hull() {
        translate([-w/2 + r, -h/2 + r]) circle(r = r);
        translate([ w/2 - r, -h/2 + r]) circle(r = r);
        translate([-w/2 + r,  h/2 - r]) circle(r = r);
        translate([ w/2 - r,  h/2 - r]) circle(r = r);
    }
}

module outer_black_2d() {
    difference() {
        union() {
            rounded_rect(badge_w, badge_h, corner_r);

            translate([tab_x, 0])
                circle(r = tab_r);
        }

        translate([tab_x, 0])
            circle(r = hole_r);
    }
}

module red_border_2d() {
    difference() {
        rounded_rect(
            badge_w - 2 * black_border,
            badge_h - 2 * black_border,
            corner_r - black_border
        );

        rounded_rect(
            badge_w - 2 * (black_border + red_border),
            badge_h - 2 * (black_border + red_border),
            corner_r - black_border - red_border
        );
    }
}

module white_panel_2d() {
    rounded_rect(
        badge_w - 2 * (black_border + red_border),
        badge_h - 2 * (black_border + red_border),
        corner_r - black_border - red_border
    );
}

module name_2d() {
    text(
        text = name_text,
        size = font_size,
        font = font_name,
        halign = "center",
        valign = "center",
        spacing = text_spacing
    );
}


// ---------- 3D LAYERS ----------
module black_base() {
    color("black")
    difference() {
        linear_extrude(height = black_base_h)
            outer_black_2d();

        // Carve out the white panel footprint from white_panel_z upward
        translate([0, 0, white_panel_z])
            linear_extrude(height = black_base_h - white_panel_z + 0.01)
                white_panel_2d();
    }
}

module white_insert() {
    color("white")
    translate([0, 0, white_panel_z])
        linear_extrude(height = white_panel_h)
            white_panel_2d();
}

module raised_red() {
    color("red") {
        // Raised red border
        translate([0, 0, black_base_h])
            linear_extrude(height = red_border_h)
                red_border_2d();

        // Significantly raised red name
        translate([0, 0, white_panel_top])
            linear_extrude(height = red_text_h)
                name_2d();
    }
}


// ---------- FINAL MODEL ----------
black_base();
white_insert();
raised_red();