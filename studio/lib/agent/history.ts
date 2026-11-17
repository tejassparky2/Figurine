import { pruneMessages, type ModelMessage } from "ai";

/**
 * Anthropic requires signed reasoning blocks to be replayed byte-for-byte while
 * an assistant tool turn is still in progress. Once a new user turn starts,
 * those blocks may be omitted from the completed history.
 *
 * UI message persistence reconstructs each agent step as a separate model
 * message. With interleaved/omitted thinking (Claude Sonnet 5), that
 * reconstruction can change the grouping of signed reasoning blocks and make
 * Anthropic reject the next request as modified. Prune completed-turn
 * reasoning before the model call, while leaving active tool continuations
 * untouched.
 */
export function pruneCompletedTurnReasoning(
  prompt: string | ModelMessage[] | undefined,
): string | ModelMessage[] | undefined {
  if (!Array.isArray(prompt) || prompt.at(-1)?.role !== "user") return prompt;

  return pruneMessages({
    messages: prompt,
    reasoning: "all",
  });
}
