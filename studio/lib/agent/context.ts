import { z } from "zod";
import { orderSpecSchema } from "@/lib/spec";
import { workspaceImageSchema } from "@/lib/workspace";

/**
 * Per-request context for the studio agent, derived server-side from message
 * history. Passed as the agent's call options (feeds the dynamic instructions)
 * and as the tool context (image id -> url resolution inside tools).
 */
export const agentContextSchema = z.object({
  spec: orderSpecSchema,
  images: z.array(workspaceImageSchema),
  // Paid image ops already run this session (from countImageOps, i.e. message
  // history — the client can't reset it). Enforces the per-session spend caps.
  imageOps: z.object({ figurine: z.number(), total: z.number() }).optional(),
  // Chat/session id (the /s/[id] URL); used by finalizeOrder to file the
  // order against the session. Absent for bare API calls.
  sessionId: z.string().optional(),
  // Captured before the first paid image upload. Lets checkout prefill the
  // number and lets the agent hand off without asking for it a second time.
  customerWhatsapp: z.string().optional(),
});

export type AgentContext = z.infer<typeof agentContextSchema>;

/** Resolve a workspace image id to its URL. */
export function resolveImage(
  ctx: AgentContext,
  id: string,
): string | undefined {
  return ctx.images.find((img) => img.id === id)?.url;
}

// Per-session spend caps (issue #5). A figurine render is ~$0.15, an edit
// ~$0.05; a normal customer converges in well under these.
const FIGURINE_CAP = 4;
const TOTAL_OPS_CAP = 15;

/**
 * Null if the session may run another paid image op, otherwise an { error }
 * result for the tool to return — the message tells the model how to steer
 * the customer instead of silently failing.
 */
export function imageBudgetExceeded(
  ctx: AgentContext,
  kind: "figurine" | "edit",
): { error: string } | null {
  const ops = ctx.imageOps;
  if (!ops) return null;
  if (kind === "figurine" && ops.figurine >= FIGURINE_CAP) {
    return {
      error:
        "This session has reached its limit of fresh figurine renders. Do NOT retry. Tell the customer warmly that we've explored several looks and it's time to pick a favorite — offer small edits to their preferred design instead, or suggest our team continue with them on WhatsApp (+91 78925 54719).",
    };
  }
  if (ops.total >= TOTAL_OPS_CAP) {
    return {
      error:
        "This session has reached its image-generation limit. Do NOT retry. Tell the customer warmly that we've done a lot of exploring — help them pick the best design so far and place the order, or hand them to our team on WhatsApp (+91 78925 54719) to continue.",
    };
  }
  return null;
}
