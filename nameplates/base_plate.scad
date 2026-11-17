length = 109;
width  = 49;
height = 1;
radius = 2.5;
$fn    = 64;

linear_extrude(height = height)
    offset(r = radius)
        offset(delta = -radius)
            square([length, width], center = true);
