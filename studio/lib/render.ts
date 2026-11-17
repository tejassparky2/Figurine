import { fal } from "@fal-ai/client";

// fal credentials come from FAL_KEY (same key the figurines/ Python pipeline uses).
if (process.env.FAL_KEY) {
  fal.config({ credentials: process.env.FAL_KEY });
}

// Prompts ported verbatim from figurines/scripts/generate_render.py so the web
// previews match what the existing pipeline produces. The pixar prompt is split
// at its pose clause: by default the render re-stages everyone into the proven
// "simple standing pose", but when the customer wants the photo's own pose kept
// (hugs, pet in lap, ...) that clause is swapped for pose-lock text — the render
// must read as a re-skin of the photo, not a re-staging.
const PIXAR_BASE = `Priority: the figurine must be immediately recognizable as the person in the source images
Transform the subject into a DreamWorks-style 3D figurine that clearly reads as a stylized animated character (not a real person). Use bold, playful proportions with an oversized head (~45–50% of the figure's height) and a compact, sturdy body with a cohesive DreamWorks silhouette. Ensure strong visual resemblance to the character(s) in the source image by faithfully matching key facial features, hairstyle, proportions, and overall likeness, while maintaining DreamWorks-style stylization. Preserve the subject's recognizable facial identity while exaggerating expressiveness: large animated eyes, thick brows, a simplified rounded nose, and a warm smile. Render smooth, clean 3D surfaces with flat colors—no pores, no lifelike skin texture. Keep facial planes soft, rounded, and lively. Model hair and any facial hair as solid stylized volumes with smooth contours and clear shape separation (no individual strands). Keep all geometry solid and 3D-printable. For sarees and dresses, use a single color in the clothing. If relevant, add a golden/silver border but no other pattern. Present the figurine full-length on a pure white background. No base/platform/stand, no text, no logos, no names. use solid colored clothes no pattern or text.`;

export const PROMPTS = {
  pixar: `${PIXAR_BASE} simple standing pose`,
  proportion_fix: `now try changing the proportions - head should be larger about 40% of image, and body smaller. DO NOT CHANGE ANYTHING ELSE`,
} as const;

/**
 * Pixar render prompt, optionally locked to the source photo's pose.
 * `preservePose` is a per-image description written by the agent from looking
 * at the photo (who's where, the embrace, accessories) — specific text keeps
 * the model from dropping or reinventing those details.
 */
export function pixarPrompt(preservePose?: string): string {
  if (!preservePose) return PROMPTS.pixar;
  return `${PIXAR_BASE} Keep the EXACT same pose, positioning and composition as in the source image — this is a restyle, not a re-pose: ${preservePose}. Do not re-stage, separate, or straighten the subjects into a standing pose.`;
}

/**
 * Proportion-fix prompt. The default wording ("head should be larger") is the
 * step most likely to break a multi-subject pose — it can balloon a pet's head
 * or shift the composition — so when a pose is preserved it is scoped to human
 * heads only, with the pose restated.
 */
export function proportionFixPrompt(preservePose?: string): string {
  if (!preservePose) return PROMPTS.proportion_fix;
  return `now try changing the proportions - ONLY enlarge each person's head to about 40% of their figure and make their body smaller. Keep any pets/animals completely natural and unchanged. Keep the exact same pose and composition (${preservePose}). DO NOT CHANGE ANYTHING ELSE`;
}

/**
 * Manufacturing constraints for a 3D-printable model. Appended server-side to
 * every create / edit / make-printable call so the model can never drop them,
 * regardless of what the customer or agent asks for. (The agent also knows
 * these — see the chat system prompt — so it can guide the customer, but
 * enforcement lives here.)
 */
export const PRINTABILITY = `The result must be 3D-printable, which means:
- Solid flat colors only — broad areas of a single color; no fine patterns, gradients, photographic skin texture, or tiny detail.
- A limited palette: at most 5 distinct colors across the whole figure.
- Clothing must be solid colors only (one color per garment; a plain golden or silver border is allowed, but no patterns, prints, or text).
- Plain pure white background.
- No base, platform, or stand.
- No transparent or glass materials — render everything as solid, opaque material.
- No text, logos, names, or writing anywhere on the figure.`;

const REALISTIC_BASE = `Make this a recognizable 3D-printable figurine.
Preserve each person's facial identity, hairstyle, outfit silhouette, pose, relative positioning, and overall likeness.
Use simplified smooth solid forms and solid colors only, with no tiny details, gradients, or photographic skin texture.
Manufacturing priority: never reproduce clothing patterns, prints, stripes, or small decorative details. Replace patterned clothing with its dominant solid color and use one solid color per garment.
Slightly exaggerate facial features, but not too much — only enough to preserve likeness in a physical figurine.
Use at most 5 distinct colors across the whole figurine.
Use a pure white background. No base, platform, stand, text, logos, names, or writing.
The result should look like a semi-realistic physical sculpted figurine, not a photograph and not a Pixar or cartoon character.`;

/** Semi-realistic alternative shown alongside the signature Pixar style. */
export function realisticPrompt(preservePose?: string): string {
  if (!preservePose) return REALISTIC_BASE;
  return `${REALISTIC_BASE}\nKeep this exact pose and composition: ${preservePose}.`;
}

/**
 * Prompt for a POINTED edit (one localized change) on nano-banana-lite.
 * Deliberately minimal: nano is a weak model and extra constraint text makes
 * it change things it shouldn't. No printability rubric here — the source
 * image is already printable and the edit must preserve everything else;
 * enforcement lives on the gpt-image-2 paths.
 */
export function editPrompt(instruction: string): string {
  return `Apply this change: "${instruction}". DO NOT CHANGE ANYTHING ELSE.`;
}

/**
 * Wrap a FULL-IMAGE edit instruction (style/proportions/overall look) with the
 * printability guard. Runs on gpt-image-2 edit — slower but far better when
 * the change affects the whole image.
 */
export function fullEditPrompt(instruction: string): string {
  return `Rework this image as follows: "${instruction}". Keep the subject clearly recognizable. ${PRINTABILITY}`;
}

/**
 * Fixed instruction to turn an arbitrary image (e.g. a design the customer
 * brainstormed in ChatGPT) into a print-ready version. Runs on gpt-image-2
 * edit — the proven prompt for this conversion.
 */
export const MAKE_PRINTABLE_PROMPT = `create a 3d printable version of this. remove the background. also use only solid colors. ${PRINTABILITY}`;

export type Quality = "low" | "medium" | "high";

/**
 * Fast, identity-preserving multi-image edit via fal.ai nano-banana-lite
 * (Gemini Flash Image, sub-2s). Pass the image to edit first, then any
 * reference images (e.g. the original photo for a face fix). Returns a PNG URL.
 */
export async function nanoEdit(
  imageUrls: string[],
  instruction: string,
): Promise<string> {
  const result = await fal.subscribe("google/nano-banana-lite/edit", {
    input: {
      prompt: instruction,
      image_urls: imageUrls,
      output_format: "png",
    },
  });
  return (result.data as { images: { url: string }[] }).images[0].url;
}

/** Remove the background using fal.ai BiRefNet v2 (Portrait). Returns a PNG URL. */
export async function removeBg(imageUrl: string): Promise<string> {
  const result = await fal.subscribe("fal-ai/birefnet/v2", {
    input: {
      image_url: imageUrl,
      model: "Portrait",
      operating_resolution: "1024x1024",
      output_format: "png",
    },
  });
  return (result.data as { image: { url: string } }).image.url;
}

/** Run a single GPT-image-2 edit pass via fal.ai. Returns a PNG URL. */
export async function gptEdit(
  imageUrls: string[],
  prompt: string,
  quality: Quality = "medium",
): Promise<string> {
  const result = await fal.subscribe("openai/gpt-image-2/edit", {
    input: {
      prompt,
      image_urls: imageUrls,
      quality,
      output_format: "png",
    },
  });
  return (result.data as { images: { url: string }[] }).images[0].url;
}

export type FigurineStylesResult = {
  nobgUrl: string;
  styleUrls: [string, string];
};

/**
 * Full figurine style pipeline: remove the background once, then render the
 * signature Pixar style and the simplified realistic style in parallel.
 *
 * Pixar still gets its required low-cost proportion fix. Realistic is a single
 * medium edit, so both choices arrive in roughly the same wall time as the old
 * two-Pixar flow while costing slightly less (~$0.137 instead of ~$0.152).
 */
export async function generateFigurineStyles(
  photoUrl: string,
  opts: { quality?: Quality; extraDetails?: string; preservePose?: string } = {},
): Promise<FigurineStylesResult> {
  const quality = opts.quality ?? "medium";
  const nobgUrl = await removeBg(photoUrl);

  let pixar = pixarPrompt(opts.preservePose);
  let realistic = realisticPrompt(opts.preservePose);
  if (opts.extraDetails) {
    pixar = `${pixar}\n${opts.extraDetails}`;
    realistic = `${realistic}\nRequested details: ${opts.extraDetails}`;
  }
  const fixPrompt = proportionFixPrompt(opts.preservePose);

  // Proportion fix remains mandatory for Pixar (the base render otherwise
  // reads too realistic). The realistic style deliberately skips that pass so
  // it keeps natural human proportions. Both styles share the same clean input.
  const renderPixar = async (): Promise<string> => {
    const renderUrl = await gptEdit([nobgUrl], pixar, quality);
    return gptEdit([renderUrl], fixPrompt, "low");
  };
  const styleUrls = (await Promise.all([
    renderPixar(),
    gptEdit([nobgUrl], realistic, quality),
  ])) as [string, string];

  return { nobgUrl, styleUrls };
}
