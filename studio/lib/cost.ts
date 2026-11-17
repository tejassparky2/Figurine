import type { UIMessage } from "ai";

/**
 * Cost accounting for the /admin session list. All prices in one place:
 *
 * LLM prices are the Vercel AI Gateway list prices (USD per token, base
 * region — gateway billing is pass-through). Check with:
 *   curl https://ai-gateway.vercel.sh/v1/models/<model> | jq .pricing
 *
 * fal.ai doesn't return per-call cost, so image tools carry hardcoded
 * estimates derived from the call graphs in lib/render.ts / lib/agent/tools.ts:
 *   generatePixarFigurine = 1 birefnet bg-removal + 1 gpt-image-2 medium
 *   Pixar render + 1 low proportion fix + 1 medium realistic render
 *   (~$0.137 total)
 *   transformImage / makePrintable = 1 gpt-image-2 medium edit
 *   editImage = 1 nano-banana-lite edit
 */
type ModelPrice = {
  input: number;
  output: number;
  cacheRead?: number;
  cacheWrite?: number;
};

const MODEL_PRICE_PER_TOKEN: Record<string, ModelPrice> = {
  // Sonnet 5 launch pricing through 2026-08-31. Automatic caching uses the
  // default five-minute Anthropic cache (0.1x reads, 1.25x writes).
  "anthropic/claude-sonnet-5": {
    input: 2e-6,
    output: 10e-6,
    cacheRead: 0.2e-6,
    cacheWrite: 2.5e-6,
  },
  "anthropic/claude-haiku-4.5": { input: 1e-6, output: 5e-6 },
};

export type InputTokenDetails = {
  noCacheTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
};

export function llmCostUsd(
  model: string,
  inputTokens: number,
  outputTokens: number,
  inputTokenDetails?: InputTokenDetails,
): number | null {
  const price = MODEL_PRICE_PER_TOKEN[model];
  if (!price) return null;

  const noCache = inputTokenDetails?.noCacheTokens ?? 0;
  const cacheRead = inputTokenDetails?.cacheReadTokens ?? 0;
  const cacheWrite = inputTokenDetails?.cacheWriteTokens ?? 0;
  const classifiedInput = noCache + cacheRead + cacheWrite;

  // Providers that do not report a cache breakdown retain the old behavior.
  // If a provider reports only part of the breakdown, price the remainder as
  // ordinary input rather than accidentally making it free.
  const inputCost =
    classifiedInput === 0
      ? inputTokens * price.input
      : noCache * price.input +
        cacheRead * (price.cacheRead ?? price.input) +
        cacheWrite * (price.cacheWrite ?? price.input) +
        Math.max(0, inputTokens - classifiedInput) * price.input;

  return inputCost + outputTokens * price.output;
}

/** Estimated fal spend per completed image tool call, keyed by tool name. */
export const IMAGE_TOOL_COST_USD: Record<string, number> = {
  generatePixarFigurine: 0.137,
  transformImage: 0.06,
  makePrintable: 0.06,
  editImage: 0.004,
};

export type ImageOpCounts = { figurine: number; gptEdit: number; nanoEdit: number };

export const EMPTY_IMAGE_OPS: ImageOpCounts = {
  figurine: 0,
  gptEdit: 0,
  nanoEdit: 0,
};

/** Estimated fal spend for a session given its image tool call counts. */
export function imageCostUsd(ops: ImageOpCounts): number {
  return (
    ops.figurine * IMAGE_TOOL_COST_USD.generatePixarFigurine +
    ops.gptEdit * IMAGE_TOOL_COST_USD.transformImage +
    ops.nanoEdit * IMAGE_TOOL_COST_USD.editImage
  );
}

/**
 * Count completed image tool calls straight from message history — the same
 * derivation countImageOps (lib/workspace.ts) uses, split per cost group.
 */
export function countImageOpsByCost(messages: UIMessage[]): ImageOpCounts {
  const ops = { ...EMPTY_IMAGE_OPS };
  for (const m of messages) {
    if (m.role !== "assistant") continue;
    for (const part of m.parts) {
      const p = part as { type: string; state?: string };
      if (p.state !== "output-available") continue;
      if (p.type === "tool-generatePixarFigurine") ops.figurine += 1;
      else if (p.type === "tool-transformImage" || p.type === "tool-makePrintable")
        ops.gptEdit += 1;
      else if (p.type === "tool-editImage") ops.nanoEdit += 1;
    }
  }
  return ops;
}

/** "$0.0423" -> "$0.04"; sub-cent amounts show as "<$0.01". */
export function formatUsd(usd: number): string {
  if (usd > 0 && usd < 0.01) return "<$0.01";
  return `$${usd.toFixed(2)}`;
}
