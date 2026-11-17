"""
Compute accurate bounding boxes for every <path> in an SVG, plus the overall
bounds. Uses svgpathtools so Bezier curves are evaluated correctly (a regex
over path-data coordinates would include control points that overshoot the
visible shape).

Usage:
    uv run scripts/svg_bounds.py svgs/consciousengines.svg

Coordinate notes:
- SVG uses y-down (y=0 at top of viewBox).
- The lowest visible point in y (largest y value) is the descender bottom for
  letters like 'g', 'p', 'q', 'y'.
- Most lowercase letters bottom out at the baseline; the descender extends
  below that.
"""

import sys
from svgpathtools import svg2paths, Document


def main(svg_path: str) -> None:
    doc = Document(svg_path)
    vb = doc.tree.getroot().get("viewBox")
    w = doc.tree.getroot().get("width")
    h = doc.tree.getroot().get("height")
    print(f"viewBox: {vb}   width={w} height={h}")

    paths, _attrs = svg2paths(svg_path)
    print(f"num paths: {len(paths)}\n")

    overall = [float("inf"), float("-inf"), float("inf"), float("-inf")]  # xmin, xmax, ymin, ymax

    print(f"{'idx':>3}  {'xmin':>8} {'xmax':>8}   {'ymin':>8} {'ymax':>8}   width   height")
    for i, p in enumerate(paths):
        xmin, xmax, ymin, ymax = p.bbox()
        print(
            f"{i:>3}  {xmin:8.2f} {xmax:8.2f}   {ymin:8.2f} {ymax:8.2f}   "
            f"{xmax-xmin:6.2f}  {ymax-ymin:6.2f}"
        )
        overall[0] = min(overall[0], xmin)
        overall[1] = max(overall[1], xmax)
        overall[2] = min(overall[2], ymin)
        overall[3] = max(overall[3], ymax)

    xmin, xmax, ymin, ymax = overall
    print()
    print(f"OVERALL: x[{xmin:.2f}, {xmax:.2f}]  y[{ymin:.2f}, {ymax:.2f}]")
    print(f"  width  = {xmax-xmin:.2f}")
    print(f"  height = {ymax-ymin:.2f}")

    # Heuristic: baseline is roughly the second-largest path-bottom (descenders extend below).
    bottoms = sorted({round(p.bbox()[3], 2) for p in paths})
    print(f"\nUnique path-bottoms (sorted): {bottoms}")
    print("  -> the largest is descender-bottom; the cluster just below is baseline.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "svgs/consciousengines.svg"
    main(path)
