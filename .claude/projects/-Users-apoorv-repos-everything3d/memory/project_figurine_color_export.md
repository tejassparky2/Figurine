---
name: Figurine color export options
description: Tripo API convert_model parameters for colored 3MF export — not yet implemented, needs iteration
type: project
---

Tripo convert_model endpoint supports colored 3MF output. Not yet integrated into the pipeline — needs a few iterations to get right.

Key parameters:
- `export_vertex_colors: true` — preserves colors in 3MF
- `texture_format` — PNG/JPEG/WEBP
- `face_limit` — polygon count cap (default 10000)
- `flatten_bottom: true` — flattens base for printing
- `quad: true` — cleaner quad mesh
- No built-in color quantization (e.g., 4 colors) — would need post-processing

**Why:** User wants colored figurines for multi-color printing on Bambu Studio.
**How to apply:** When revisiting the figurine pipeline, add these params to the convert_model step. Color quantization to N colors will need a separate post-processing step.
