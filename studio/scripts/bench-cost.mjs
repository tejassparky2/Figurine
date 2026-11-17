// Run two nano-banana-lite edits and dump the full response to inspect
// usage/cost fields, so we can report real per-edit cost.
import { fal } from "@fal-ai/client";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { basename } from "node:path";

fal.config({ credentials: process.env.FAL_KEY });
const OUT =
  "/private/tmp/claude-501/-Users-apoorv-repos-everything3d/029f1c8c-3663-4605-a25d-4c946dfd0cb1/scratchpad/bench";
await mkdir(OUT, { recursive: true });

async function up(p) {
  const buf = await readFile(p);
  const type = p.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg";
  return fal.storage.upload(new File([buf], basename(p), { type }));
}

const preview = await up(process.argv[2]);
const original = await up(process.argv[3]);

async function run(name, image_urls, prompt) {
  const t = Date.now();
  const r = await fal.subscribe("google/nano-banana-lite/edit", {
    input: { prompt, image_urls, output_format: "png" },
    logs: true,
  });
  const secs = ((Date.now() - t) / 1000).toFixed(1);
  const ab = await (await fetch(r.data.images[0].url)).arrayBuffer();
  await writeFile(`${OUT}/cost_${name}.png`, Buffer.from(ab));
  console.log(`\n===== ${name}  (${secs}s, ${image_urls.length} input image(s)) =====`);
  // Print everything except the raw image bytes/urls list length
  const clone = JSON.parse(JSON.stringify(r));
  console.log(JSON.stringify(clone, null, 2).slice(0, 4000));
}

await run(
  "remove_glasses",
  [preview],
  "Remove the eyeglasses from the figurine. Keep everything else exactly the same.",
);
await run(
  "fix_face",
  [preview, original],
  "Make the figurine's face and likeness match the person in the second image; keep the body, pose, clothing, colors and style the same.",
);
console.log("\nimages saved to", OUT);
