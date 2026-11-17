// Benchmark fast image-edit models for figurine revisions.
// Usage: set -a; source .env.local; set +a; node scripts/bench-edit-models.mjs <previewPath> [originalPath]
// Compares Nano-Banana vs FLUX Kontext vs gpt-image-2(low) on:
//   Test A - single-image local edit ("remove the glasses, keep everything else")
//   Test B - multi-image identity ("match the face to the reference photo")
import { fal } from "@fal-ai/client";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { basename } from "node:path";

const KEY = process.env.FAL_KEY;
if (!KEY) {
  console.error("FAL_KEY not set (run: set -a; source .env.local; set +a)");
  process.exit(1);
}
fal.config({ credentials: KEY });

const OUT =
  "/private/tmp/claude-501/-Users-apoorv-repos-everything3d/029f1c8c-3663-4605-a25d-4c946dfd0cb1/scratchpad/bench";
await mkdir(OUT, { recursive: true });

async function up(path) {
  const buf = await readFile(path);
  const type = path.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg";
  const file = new File([buf], basename(path), { type });
  return await fal.storage.upload(file);
}

async function timed(name, fn) {
  const t = Date.now();
  try {
    const url = await fn();
    const secs = ((Date.now() - t) / 1000).toFixed(1);
    const resp = await fetch(url);
    const ab = await resp.arrayBuffer();
    const out = `${OUT}/${name}.png`;
    await writeFile(out, Buffer.from(ab));
    console.log(`  ✓ ${name.padEnd(20)} ${secs.padStart(5)}s  -> ${out}`);
  } catch (e) {
    const secs = ((Date.now() - t) / 1000).toFixed(1);
    console.log(`  ✗ ${name.padEnd(20)} ${secs.padStart(5)}s  ERROR: ${e.message}`);
  }
}

const previewPath = process.argv[2];
const originalPath = process.argv[3];
if (!previewPath) {
  console.error("Provide a preview image path as the first argument.");
  process.exit(1);
}

console.log("Uploading test images to fal...");
const preview = await up(previewPath);
const original = originalPath ? await up(originalPath) : null;
console.log("preview :", preview);
if (original) console.log("original:", original);

const EDIT =
  "Remove the eyeglasses from the figurine. Do not change anything else — keep the exact same face, hair, expression, pose, clothing, colors, and 3D style.";
const FACE =
  "Make the figurine's face and likeness match the person in the second image, while keeping the figurine's body, pose, clothing, colors and 3D style exactly the same.";

console.log("\n== Test A: single-image local edit (remove glasses) ==");
await timed("A_nano_banana", async () => {
  const r = await fal.subscribe("fal-ai/nano-banana/edit", {
    input: { prompt: EDIT, image_urls: [preview] },
  });
  return r.data.images[0].url;
});
await timed("A_flux_kontext", async () => {
  const r = await fal.subscribe("fal-ai/flux-pro/kontext", {
    input: { prompt: EDIT, image_url: preview },
  });
  return r.data.images[0].url;
});
await timed("A_gpt_image2_low", async () => {
  const r = await fal.subscribe("openai/gpt-image-2/edit", {
    input: { prompt: EDIT, image_urls: [preview], quality: "low", output_format: "png" },
  });
  return r.data.images[0].url;
});

if (original) {
  console.log("\n== Test B: multi-image identity (fix face using original photo) ==");
  await timed("B_nano_banana", async () => {
    const r = await fal.subscribe("fal-ai/nano-banana/edit", {
      input: { prompt: FACE, image_urls: [preview, original] },
    });
    return r.data.images[0].url;
  });
  await timed("B_gpt_image2_low", async () => {
    const r = await fal.subscribe("openai/gpt-image-2/edit", {
      input: { prompt: FACE, image_urls: [preview, original], quality: "low", output_format: "png" },
    });
    return r.data.images[0].url;
  });
}

console.log("\nDone. Outputs in", OUT);
