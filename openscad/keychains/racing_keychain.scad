// ============================================
// RACING KEYCHAIN GENERATOR v2
// Layered 3D racing badge with speed streaks
// Colors: Black (base), Red (border/accents), White (panel)
// ============================================

/* ======= PARAMETERS ======= */

// Name to display (change per kid)
name = "Abeer";

// Font — bold condensed fonts give the best racing feel
// Options: "Impact", "Arial Black", "Helvetica Neue:style=Bold"
font_name = "Impact";

// --- Overall dimensions ---
body_length = 65;              // Main body length (mm)
body_width  = 25;              // Main body width (mm)

// --- Speed streaks ---
num_streaks     = 4;           // Number of speed prongs
streak_max_len  = 22;          // Longest streak (mm)
streak_step     = 4.5;         // Each streak shorter by this
streak_gap      = 2.0;         // Gap between streaks (mm)

// --- Layer heights (mm) ---
h_base    = 2.0;               // Black base plate
h_accent  = 0.8;               // Red border + streak layer
h_panel   = 0.8;               // White inner panel
h_outline = 0.5;               // Black text outline
h_text    = 0.5;               // Red text

// --- Border widths (mm) ---
border_outer = 1.5;            // Black → Red inset
border_inner = 1.3;            // Red → White inset
text_outline_w = 0.5;          // Text outline thickness

// --- Keyring hole ---
hole_d    = 5.0;               // Hole diameter
hole_wall = 2.0;               // Min wall around hole

// --- Text ---
text_size   = 13;              // Font size (mm)
text_italic = 12;              // Forward slant (degrees)

/* ======= COMPUTED ======= */
right_r = body_width / 2;
streak_width = (body_width - (num_streaks - 1) * streak_gap) / num_streaks;
total_inset = border_outer + border_inner;
hole_x = -(streak_max_len - hole_d/2 - hole_wall);
hole_y = streak_width / 2;

/* ======= 2D PROFILES ======= */

// Main body: flat left edge, fully rounded right end
module body_2d() {
    r = body_width / 2;
    union() {
        square([body_length - r, body_width]);
        translate([body_length - r, r])
            circle(r=r, $fn=64);
    }
}

// Single speed streak — sharp pointed prong
module streak_2d(len) {
    tip_w = 0.3;  // Tiny tip width for printability
    polygon([
        [0, 0],
        [0, streak_width],
        [-len, streak_width/2 + tip_w/2],
        [-len, streak_width/2 - tip_w/2]
    ]);
}

// All streaks
module streaks_2d() {
    for (i = [0 : num_streaks - 1]) {
        s_len = streak_max_len - i * streak_step;
        s_y   = i * (streak_width + streak_gap);
        translate([0, s_y])
            streak_2d(s_len);
    }
}

// Complete outline shape
module full_shape_2d() {
    body_2d();
    streaks_2d();
}

// Keyring hole (2D)
module hole_2d() {
    translate([hole_x, hole_y])
        circle(d=hole_d, $fn=32);
}

// Name text (2D) with italic shear
module name_2d(extra=0) {
    translate([10, body_width/2])
        multmatrix([
            [1, tan(text_italic), 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0]
        ])
        offset(r=extra)
            text(name, size=text_size, font=font_name,
                 halign="left", valign="center", spacing=1.0);
}

/* ======= 3D COLOR LAYERS ======= */

// BLACK: base plate + text outline
module color_black() {
    // --- Base plate (full shape) ---
    difference() {
        linear_extrude(h_base)
            full_shape_2d();
        linear_extrude(h_base)
            hole_2d();
    }

    // --- Text outline (raised, on white panel) ---
    z = h_base + h_accent + h_panel;
    translate([0, 0, z])
        difference() {
            linear_extrude(h_outline)
                intersection() {
                    offset(r=-total_inset) body_2d();
                    name_2d(text_outline_w);
                }
            linear_extrude(h_outline)
                hole_2d();
        }
}

// RED: border frame + streak accents + text
module color_red() {
    z_accent = h_base;

    // --- Red border (body) + red streak surfaces ---
    translate([0, 0, z_accent])
        difference() {
            // Full shape inset
            linear_extrude(h_accent)
                offset(r=-border_outer)
                    full_shape_2d();
            // Subtract white panel area
            linear_extrude(h_accent)
                offset(r=-total_inset)
                    body_2d();
            // Hole
            linear_extrude(h_accent)
                hole_2d();
        }

    // --- Red text (on top of outline) ---
    z_text = h_base + h_accent + h_panel + h_outline;
    translate([0, 0, z_text])
        difference() {
            linear_extrude(h_text)
                intersection() {
                    offset(r=-total_inset) body_2d();
                    name_2d();
                }
            linear_extrude(h_text)
                hole_2d();
        }
}

// WHITE: inner panel (body only, no streaks)
module color_white() {
    z_panel = h_base + h_accent;

    translate([0, 0, z_panel])
        difference() {
            linear_extrude(h_panel)
                offset(r=-total_inset)
                    body_2d();
            linear_extrude(h_panel)
                hole_2d();
        }
}

/* ======= RENDER ======= */

// --- PREVIEW: all 3 colors together ---
color("#1a1a1a") color_black();
color("#dc2626") color_red();
color("#f0f0f0") color_white();

// --- EXPORT: uncomment ONE at a time for STL ---
// color_black();    // → Abeer_black.stl
// color_red();      // → Abeer_red.stl
// color_white();    // → Abeer_white.stl
