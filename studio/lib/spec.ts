import { z } from "zod";
import type { UIMessage } from "ai";

/**
 * Structured order specification kept in sync between the chat agent and the
 * order-summary sidebar. The agent records choices here as they're made; it is
 * derived from message history (tool outputs) on both client and server, so
 * nothing extra travels in the request body.
 *
 * Only what actually matters for the order: everything visual lives in the
 * chosen image itself.
 */
export const orderSpecSchema = z.object({
  size: z
    .string()
    .optional()
    .describe(
      'Physical print size. Figurine sizes are "13cm", "15cm" and "18cm".',
    ),
  baseText: z
    .string()
    .optional()
    .describe("Text engraved on the physical base (added at print time)."),
});

export type OrderSpec = z.infer<typeof orderSpecSchema>;

/** Partial-update schema the agent uses to patch the spec. */
export const specPatchSchema = orderSpecSchema;

/**
 * Derive the current order spec from message history by merging the outputs of
 * every updateOrderSpecification tool call. Used identically on the client
 * (sidebar) and the server (system prompt).
 */
export function deriveSpec(messages: UIMessage[]): OrderSpec {
  const merged: OrderSpec = {};
  for (const m of messages) {
    for (const part of m.parts) {
      if (
        part.type === "tool-updateOrderSpecification" &&
        part.state === "output-available" &&
        part.output
      ) {
        Object.assign(merged, part.output as OrderSpec);
      }
    }
  }
  return merged;
}
