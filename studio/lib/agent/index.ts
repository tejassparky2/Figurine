import { ToolLoopAgent, isStepCount } from "ai";
import { agentContextSchema, type AgentContext } from "./context";
import { pruneCompletedTurnReasoning } from "./history";
import { instructions } from "./prompt";
import { tools } from "./tools";

const EMPTY_CONTEXT: AgentContext = { spec: {}, images: [] };

/**
 * The studio agent, defined once with the AI SDK's ToolLoopAgent. Per-request
 * state (order spec + image workspace, derived from message history) comes in
 * as call options; prepareCall turns it into the dynamic instructions and the
 * tool context. Iterate on prompt.ts / tools.ts — this file rarely changes.
 */
export const studioAgent = new ToolLoopAgent({
  model: "anthropic/claude-sonnet-5",
  // Studio decisions are narrow and tool-driven; low effort avoids paying for
  // long hidden reasoning traces without disabling reasoning altogether.
  reasoning: "low",
  // AI Gateway applies Anthropic cache breakpoints automatically. The large,
  // stable instructions + tool schemas are then written once and read cheaply
  // on later turns and tool-loop steps.
  providerOptions: {
    gateway: {
      caching: "auto",
    },
  },
  tools,
  stopWhen: isStepCount(5),
  callOptionsSchema: agentContextSchema,
  // Base tool context (required by the types); prepareCall swaps in the real
  // per-request context below.
  toolsContext: {
    generatePixarFigurine: EMPTY_CONTEXT,
    editImage: EMPTY_CONTEXT,
    transformImage: EMPTY_CONTEXT,
    makePrintable: EMPTY_CONTEXT,
    proposeOrder: EMPTY_CONTEXT,
    finalizeOrder: EMPTY_CONTEXT,
    handoffToHuman: EMPTY_CONTEXT,
  },
  prepareCall: ({ options, ...call }) => ({
    ...call,
    prompt: pruneCompletedTurnReasoning(call.prompt),
    instructions: instructions(options),
    // toolsContext is keyed per tool; every image tool gets the same context.
    toolsContext: {
      generatePixarFigurine: options,
      editImage: options,
      transformImage: options,
      makePrintable: options,
      proposeOrder: options,
      finalizeOrder: options,
      handoffToHuman: options,
    },
  }),
});
