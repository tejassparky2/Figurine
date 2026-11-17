import { z } from "zod";
import type { UIMessage } from "ai";

/**
 * An image in the session's workspace. Every image the customer uploads or the
 * agent generates/edits lands here with an id, so tools can reference images by
 * id (the server resolves id -> url). Mirrors how `spec` is managed: derived on
 * the client and sent in the chat request body.
 */
export const workspaceImageSchema = z.object({
  id: z.string(),
  url: z.string(),
  kind: z.enum(["uploaded", "generated"]),
  label: z.string(),
});

export type WorkspaceImage = z.infer<typeof workspaceImageSchema>;

export const workspaceSchema = z.array(workspaceImageSchema);

// Tool parts whose output carries a generated image.
const IMAGE_TOOL_PARTS = new Set([
  "tool-generatePixarFigurine",
  "tool-editImage",
  "tool-transformImage",
  "tool-makePrintable",
]);

/**
 * How many paid image operations this session has already run, straight from
 * message history (so it survives refreshes and can't be reset by the
 * client). Counts attempts, not successes — failed calls spend money too.
 * Feeds the per-session caps in the image tools (issue #5).
 */
export function countImageOps(messages: UIMessage[]): {
  figurine: number;
  total: number;
} {
  let figurine = 0;
  let total = 0;
  for (const m of messages) {
    if (m.role !== "assistant") continue;
    for (const part of m.parts) {
      const p = part as { type: string; state?: string };
      if (!IMAGE_TOOL_PARTS.has(p.type)) continue;
      if (p.state !== "output-available") continue;
      total += 1;
      if (p.type === "tool-generatePixarFigurine") figurine += 1;
    }
  }
  return { figurine, total };
}

/**
 * Derive the image workspace from message history. Used identically on the
 * client (for display) and the server (to resolve tool image ids), so ids are
 * stable across both: `${messageId}:${partIndex}`.
 *
 * Uploaded images come from user `file` parts; generated images from the
 * output of the image tools.
 */
export function deriveWorkspace(messages: UIMessage[]): WorkspaceImage[] {
  const images: WorkspaceImage[] = [];
  let uploaded = 0;
  let generated = 0;

  for (const m of messages) {
    m.parts.forEach((part, i) => {
      const p = part as {
        type: string;
        mediaType?: string;
        url?: string;
        state?: string;
        output?: {
          imageUrl?: string;
          imageUrls?: string[];
          optionLabels?: string[];
          label?: string;
        };
      };

      if (
        m.role === "user" &&
        p.type === "file" &&
        p.mediaType?.startsWith("image/") &&
        p.url
      ) {
        uploaded += 1;
        images.push({
          id: `${m.id}:${i}`,
          url: p.url,
          kind: "uploaded",
          label: uploaded === 1 ? "uploaded photo" : `uploaded photo ${uploaded}`,
        });
      }

      if (
        m.role === "assistant" &&
        IMAGE_TOOL_PARTS.has(p.type) &&
        p.state === "output-available" &&
        p.output
      ) {
        // A tool output carries either one image (imageUrl) or several
        // (imageUrls, e.g. the two figurine options). Multi-image outputs get
        // per-image ids `${messageId}:${partIndex}:${optionIndex}`.
        const urls =
          p.output.imageUrls ??
          (p.output.imageUrl ? [p.output.imageUrl] : []);
        const multi = urls.length > 1;
        urls.forEach((url, k) => {
          generated += 1;
          images.push({
            id: multi ? `${m.id}:${i}:${k}` : `${m.id}:${i}`,
            url,
            kind: "generated",
            label: `${p.output?.label ?? "figurine"} ${generated}${
              multi
                ? ` (${p.output?.optionLabels?.[k] ?? `option ${k + 1}`})`
                : ""
            }`,
          });
        });
      }
    });
  }

  return images;
}
