"""
Create a before/after composite from a client photo and a 3D render.

Usage:
    python scripts/before_after.py <client_photo> <render_image> [output_image]

Detects faces in the client photo, crops a circular region covering all faces,
extracts the figurine subject from the render, and composes them side by side
on a clean canvas with a curved arrow.

If no output path is given, the output is saved with a '_before_after' suffix
on the render image filename.
"""

import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

# ── Layout ──────────────────────────────────────────────────────────────────

# Canvas height matches the render image height; width is computed from layout
CANVAS_PADDING = 0.04          # padding around elements as fraction of canvas height
CIRCLE_SIZE_FRACTION = 0.35    # circle diameter as fraction of canvas height
SUBJECT_MAX_HEIGHT = 0.90      # max subject height as fraction of canvas height
CANVAS_BG_COLOR = (245, 245, 245)  # light gray background

# Circle border
BORDER_FRACTION = 0.04         # white border as fraction of circle diameter

# ── Face detection ──────────────────────────────────────────────────────────

CROP_PADDING = 0.6             # extra padding around faces (fraction of region size)
HAAR_MIN_NEIGHBORS = 5

# ── Subject extraction ──────────────────────────────────────────────────────

BG_SAMPLE_SIZE = 20            # pixels sampled from each corner
BG_THRESHOLD = 30              # color distance to count as foreground

# ── Arrow styling ───────────────────────────────────────────────────────────

ARROW_COLOR = (180, 180, 180, 255)       # medium gray
ARROW_WIDTH_FRACTION = 0.003             # line width as fraction of canvas width
ARROWHEAD_LENGTH_FRACTION = 0.018        # arrowhead size as fraction of canvas width
CURVE_BULGE_FRACTION = 0.06              # how much the curve bows (fraction of arrow length)


def detect_faces(image_path: Path) -> list[tuple[int, int, int, int]]:
    """Detect faces in image, return list of (x, y, w, h) bounding boxes."""
    image = cv2.imread(str(image_path))
    if image is None:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=HAAR_MIN_NEIGHBORS, minSize=(30, 30),
    )

    if len(faces) == 0:
        return []

    boxes = sorted(faces.tolist(), key=lambda f: f[2] * f[3], reverse=True)[:2]
    return [(x, y, w, h) for x, y, w, h in boxes]


def combined_face_region(
    boxes: list[tuple[int, int, int, int]], img_w: int, img_h: int
) -> tuple[int, int, int]:
    """Combine all face boxes into one padded square region. Returns (cx, cy, side)."""
    min_x = min(x for x, y, w, h in boxes)
    min_y = min(y for x, y, w, h in boxes)
    max_x = max(x + w for x, y, w, h in boxes)
    max_y = max(y + h for x, y, w, h in boxes)

    cx = (min_x + max_x) // 2
    cy = (min_y + max_y) // 2
    region_size = max(max_x - min_x, max_y - min_y)
    side = int(region_size * (1 + CROP_PADDING))

    half = side // 2
    cx = max(half, min(img_w - half, cx))
    cy = max(half, min(img_h - half, cy))
    return cx, cy, side


def crop_circle(
    image: Image.Image, cx: int, cy: int, side: int, diameter: int, border: int,
) -> Image.Image:
    """Crop a square region into a circle with white border. Returns RGBA image."""
    half = side // 2
    box = (cx - half, cy - half, cx + half, cy + half)
    crop = image.crop(box).resize((diameter, diameter), Image.LANCZOS)

    # Circular mask
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    crop_rgba = crop.convert("RGBA")
    crop_rgba.putalpha(mask)

    # White border ring
    total = diameter + border * 2
    output = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    ImageDraw.Draw(output).ellipse((0, 0, total - 1, total - 1), fill=(255, 255, 255, 255))
    output.paste(crop_rgba, (border, border), crop_rgba)
    return output


def extract_subject(render_path: Path) -> Image.Image:
    """Extract the figurine subject from the render, removing the background.

    Returns an RGBA image with transparent background, cropped to the subject bounds.
    """
    image = cv2.imread(str(render_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        print(f"Error: Could not read {render_path}")
        sys.exit(1)

    # If image has alpha channel, use it directly
    if image.shape[2] == 4:
        bgr = image[:, :, :3]
        alpha = image[:, :, 3]
    else:
        bgr = image
        alpha = None

    h, w = bgr.shape[:2]
    s = BG_SAMPLE_SIZE

    # Sample background from corners
    corners = [
        bgr[0:s, 0:s], bgr[0:s, w - s:w],
        bgr[h - s:h, 0:s], bgr[h - s:h, w - s:w],
    ]
    bg_color = np.mean(
        np.concatenate([c.reshape(-1, 3) for c in corners], axis=0), axis=0
    )

    # Create foreground mask
    diff = np.linalg.norm(bgr.astype(float) - bg_color, axis=2)
    fg_mask = (diff > BG_THRESHOLD).astype(np.uint8) * 255

    if alpha is not None:
        # Combine with existing alpha
        fg_mask = cv2.bitwise_and(fg_mask, alpha)

    # Clean up mask with morphological operations
    kernel = np.ones((5, 5), np.uint8)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # Find bounding box of subject
    coords = cv2.findNonZero(fg_mask)
    if coords is None:
        # Fallback: return whole image
        pil_img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
        return pil_img

    bx, by, bw, bh = cv2.boundingRect(coords)

    # Crop to subject bounds
    subject_bgr = bgr[by:by + bh, bx:bx + bw]
    subject_mask = fg_mask[by:by + bh, bx:bx + bw]

    # Convert to RGBA with mask as alpha
    subject_rgb = cv2.cvtColor(subject_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(subject_rgb).convert("RGBA")
    pil_mask = Image.fromarray(subject_mask)
    pil_img.putalpha(pil_mask)

    return pil_img


def draw_curved_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    canvas_w: int,
    color: tuple,
) -> None:
    """Draw a curved arrow (quadratic bezier) from start to end."""
    sx, sy = start
    ex, ey = end
    arrow_len = math.hypot(ex - sx, ey - sy)
    width = max(3, int(canvas_w * ARROW_WIDTH_FRACTION))
    head_length = max(10, int(canvas_w * ARROWHEAD_LENGTH_FRACTION))

    # Control point: midpoint offset upward for a nice arc
    mx = (sx + ex) / 2
    my = (sy + ey) / 2 - arrow_len * CURVE_BULGE_FRACTION

    # Sample points along the quadratic bezier
    num_points = 40
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        # B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * mx + t ** 2 * ex
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * my + t ** 2 * ey
        points.append((x, y))

    # Draw the curve as line segments
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color, width=width)

    # Arrowhead at the end, using direction of last segment
    px, py = points[-2]
    angle = math.atan2(ey - py, ex - px)
    head_half = head_length * 0.35

    tip_x, tip_y = ex, ey
    left_x = ex - head_length * math.cos(angle) + head_half * math.sin(angle)
    left_y = ey - head_length * math.sin(angle) - head_half * math.cos(angle)
    right_x = ex - head_length * math.cos(angle) - head_half * math.sin(angle)
    right_y = ey - head_length * math.sin(angle) + head_half * math.cos(angle)

    draw.polygon([(tip_x, tip_y), (left_x, left_y), (right_x, right_y)], fill=color)


def create_before_after(
    client_path: Path, render_path: Path, output_path: Path
) -> None:
    """Create the before/after composite image."""
    # 1. Detect faces and make circle crop
    boxes = detect_faces(client_path)
    if not boxes:
        print("Error: No faces detected in client photo")
        sys.exit(1)

    client_image = Image.open(client_path).convert("RGB")
    img_w, img_h = client_image.size
    cx, cy, side = combined_face_region(boxes, img_w, img_h)

    # 2. Extract subject from render
    subject = extract_subject(render_path)
    sub_w, sub_h = subject.size

    # 3. Compute canvas dimensions
    render_image = Image.open(render_path)
    render_w, render_h = render_image.size
    canvas_h = render_h
    padding = int(canvas_h * CANVAS_PADDING)

    circle_diameter = int(canvas_h * CIRCLE_SIZE_FRACTION)
    circle_border = max(2, int(circle_diameter * BORDER_FRACTION))
    circle_total = circle_diameter + circle_border * 2

    # Scale subject to fit canvas height
    max_sub_h = int(canvas_h * SUBJECT_MAX_HEIGHT)
    scale = min(max_sub_h / sub_h, 1.0)
    new_sub_w = int(sub_w * scale)
    new_sub_h = int(sub_h * scale)
    subject_resized = subject.resize((new_sub_w, new_sub_h), Image.LANCZOS)

    # Arrow gap between circle and subject
    arrow_gap = padding * 3

    # Canvas width: padding + circle + arrow_gap + subject + padding
    canvas_w = padding + circle_total + arrow_gap + new_sub_w + padding

    # 4. Make the circle crop
    circle = crop_circle(client_image, cx, cy, side, circle_diameter, circle_border)

    # 5. Compose everything on canvas
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (*CANVAS_BG_COLOR, 255))

    # Place circle (vertically centered)
    circle_x = padding
    circle_y = (canvas_h - circle_total) // 2
    canvas.paste(circle, (circle_x, circle_y), circle)

    # Place subject (vertically centered)
    subject_x = padding + circle_total + arrow_gap
    subject_y = (canvas_h - new_sub_h) // 2
    canvas.paste(subject_resized, (subject_x, subject_y), subject_resized)

    # 6. Draw curved arrow
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    arrow_start = (circle_x + circle_total + padding // 2, canvas_h // 2)
    arrow_end = (subject_x - padding // 2, canvas_h // 2)

    draw_curved_arrow(overlay_draw, arrow_start, arrow_end, canvas_w, ARROW_COLOR)

    canvas = Image.alpha_composite(canvas, overlay)

    # 7. Save
    canvas = canvas.convert("RGB")
    canvas.save(output_path, quality=95)
    print(f"  {render_path.name} -> {output_path.name}")


def main() -> None:
    args = sys.argv[1:]

    if len(args) < 2:
        print(__doc__.strip())
        sys.exit(1)

    client_path = Path(args[0])
    render_path = Path(args[1])
    output_path = Path(args[2]) if len(args) > 2 else render_path.with_stem(
        render_path.stem + "_before_after"
    )

    if not client_path.exists():
        print(f"Error: {client_path} does not exist")
        sys.exit(1)

    if not render_path.exists():
        print(f"Error: {render_path} does not exist")
        sys.exit(1)

    create_before_after(client_path, render_path, output_path)


if __name__ == "__main__":
    main()
