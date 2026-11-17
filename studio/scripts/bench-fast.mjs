// Focused benchmark of the newest fast nano-banana variants.
import { fal } from "@fal-ai/client";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { basename } from "node:path";

fal.config({ credentials: process.env.FAL_KEY });
const OUT =
  "/private/tmp/claude-501/-Users-apoorv-repos-everything3d/029f1c8c-3663-4605-a25d-4c946dfd0cb1/scratchpad/bench";
await mkdir(OUT, { recursive: true });

async function up(path) {
  const buf = await readFile(path);
  const type = path.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg";
  return fal.storage.upload(new File([buf], basename(path), { type }));
}
async function timed(name, model, input) {
  const t = Date.now();
  try {
    const r = await fal.subscribe(model, { input });
    const secs = ((Date.now() - t) / 1000).toFixed(1);
    const ab = await (await fetch(r.data.images[0].url)).arrayBuffer();
    await writeFile(`${OUT}/${name}.png`, Buffer.from(ab));
    console.log(`  ✓ ${name.padEnd(22)} ${secs.padStart(5)}s`);
  } catch (e) {
    const secs = ((Date.now() - t) / 1000).toFixed(1);
    console.log(`  ✗ ${name.padEnd(22)} ${secs.padStart(5)}s  ERROR: ${e.message}`);
  }
}

const preview = await up(process.argv[2]);
const original = await up(process.argv[3]);
const EDIT =
  "Remove the eyeglasses from the figurine. Do not change anything else — keep the exact same face, hair, expression, pose, clothing, colors, and 3D style.";
const FACE =
  "Make the figurine's face and likeness match the person in the second image, while keeping the figurine's body, pose, clothing, colors and 3D style exactly the same.";

console.log("== Test A: remove glasses ==");
await timed("A_nb_lite", "google/nano-banana-lite/edit", { prompt: EDIT, image_urls: [preview] });
await timed("A_nb2", "fal-ai/nano-banana-2/edit", { prompt: EDIT, image_urls: [preview] });
console.log("== Test B: fix face from photo ==");
await timed("B_nb_lite", "google/nano-banana-lite/edit", { prompt: FACE, image_urls: [preview, original] });
await timed("B_nb2", "fal-ai/nano-banana-2/edit", { prompt: FACE, image_urls: [preview, original] });
console.log("done ->", OUT);
