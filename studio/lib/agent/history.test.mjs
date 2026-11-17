import assert from "node:assert/strict";
import test from "node:test";
import { pruneCompletedTurnReasoning } from "./history.ts";

const signedReasoning = (signature) => ({
  type: "reasoning",
  text: "",
  providerOptions: { anthropic: { signature } },
});

test("prunes signed reasoning after a new user turn begins", () => {
  const messages = [
    { role: "user", content: [{ type: "text", text: "make an image" }] },
    {
      role: "assistant",
      content: [
        signedReasoning("first"),
        {
          type: "tool-call",
          toolCallId: "call-1",
          toolName: "generateImage",
          input: {},
        },
      ],
    },
    {
      role: "tool",
      content: [
        {
          type: "tool-result",
          toolCallId: "call-1",
          toolName: "generateImage",
          output: { type: "text", value: "done" },
        },
      ],
    },
    { role: "assistant", content: [signedReasoning("second")] },
    {
      role: "assistant",
      content: [{ type: "text", text: "Here is the image." }],
    },
    { role: "user", content: [{ type: "text", text: "revise it" }] },
  ];

  const result = pruneCompletedTurnReasoning(messages);

  assert.deepEqual(
    result.map((message) => message.role),
    ["user", "assistant", "tool", "assistant", "user"],
  );
  assert.equal(
    result.some(
      (message) =>
        Array.isArray(message.content) &&
        message.content.some((part) => part.type === "reasoning"),
    ),
    false,
  );
  assert.equal(
    messages[1].content[0].type,
    "reasoning",
    "the persisted input must not be mutated",
  );
});

test("preserves reasoning while a tool turn is still active", () => {
  const messages = [
    { role: "user", content: [{ type: "text", text: "make an image" }] },
    {
      role: "assistant",
      content: [
        signedReasoning("active"),
        {
          type: "tool-call",
          toolCallId: "call-1",
          toolName: "generateImage",
          input: {},
        },
      ],
    },
    {
      role: "tool",
      content: [
        {
          type: "tool-result",
          toolCallId: "call-1",
          toolName: "generateImage",
          output: { type: "text", value: "done" },
        },
      ],
    },
  ];

  assert.equal(pruneCompletedTurnReasoning(messages), messages);
});
