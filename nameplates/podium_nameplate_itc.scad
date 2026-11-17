// ---- Plate ----
length = 109;
width  = 49;
height = 1;
radius = 5;
$fn    = 64;

// ---- Text ----
text_height = 0.5;
bold_amount = 0.1;   // how much to thicken strokes (mm). 0.1–0.25 works well.

name_text = "Harish Mitra";
name_font = "American Typewriter";
name_size = 7.2;        // was 9
name_margin = 4;        // mm of clear space at each end of the plate

sub1_text = "Always on Go...Abhi main yahan";
sub2_text = "iske baad main wahan hounga";
sub_font  = "Akaya Kanadaka";
sub_size  = 4.5;        // base. Tag lines grow to fill plate width, capped.
sub_max_size = 6.0;     // upper bound when scaling short taglines up

// Width text() actually occupies once we apply the bold offset.
function text_width(txt, size, font) =
    txt == "" ? 0
    : textmetrics(text=txt, size=size, font=font).size[0] + 2*bold_amount;

// Shrink size only when text overruns max_width; never grows past base.
function shrink_to_fit(txt, base_size, font, max_width) =
    let(natural = text_width(txt, base_size, font))
    natural > max_width ? base_size * max_width / natural : base_size;

// Scale size up so the widest of two strings hits target_width, capped at max_size.
function scale_to_fill(s1, s2, base_size, font, target_width, max_size) =
    let(widest = max(text_width(s1, base_size, font), text_width(s2, base_size, font)))
    widest == 0 ? base_size : min(max_size, base_size * target_width / widest);

name_fit_size = shrink_to_fit(name_text, name_size, name_font, length - 2*name_margin);
sub_fit_size  = scale_to_fill(sub1_text, sub2_text, sub_size, sub_font,
                              length - 2*name_margin, sub_max_size);

// Vertical layout: re-center the text group based on how many tag lines exist.
n_tags = (sub1_text == "" ? 0 : 1) + (sub2_text == "" ? 0 : 1);
name_y = n_tags == 2 ? 11 : (n_tags == 1 ? 7 : 0);
sub1_y = n_tags == 2 ? -3 : -7;
sub2_y = -12;

module plate() {
    linear_extrude(height = height)
        offset(r = radius)
            offset(delta = -radius)
                square([length, width], center = true);
}

// Bold trick: render text as 2D, grow it with offset(), then extrude.
module bold_text(txt, size, font, y) {
    translate([0, y, height])
        linear_extrude(height = text_height)
            offset(r = bold_amount)
                text(txt, size = size, font = font,
                     halign = "center", valign = "center");
}

color("WhiteSmoke") plate();
color("black")      bold_text(name_text, name_fit_size, name_font, name_y);
color("DodgerBlue") {
    bold_text(sub1_text, sub_fit_size, sub_font, sub1_y);
    bold_text(sub2_text, sub_fit_size, sub_font, sub2_y);
}