import { generateText, type ModelMessage, type UIMessage } from "ai";
import { recordUsage, setSessionTitle } from "@/lib/db";

/**
 * Generate and store a short title for a session from its first user message
 * (text and/or uploaded photo), ChatGPT-style. Fire-and-forget: any failure
 * just leaves the title null and the UI falls back to the raw message text.
 */
export async function generateAndSaveTitle(
  sessionId: string,
  messages: UIMessage[],
): Promise<void> {
  const first = messages.find((m) => m.role === "user");
  if (!first) return;

  const content: Exclude<
    Extract<ModelMessage, { role: "user" }>["content"],
    string
  > = [];
  for (const part of first.parts) {
    if (part.type === "text" && part.text.trim()) {
      content.push({ type: "text", text: part.text.trim() });
    }
    // One image is plenty for a title.
    if (
      part.type === "file" &&
      part.mediaType?.startsWith("image/") &&
      !content.some((c) => c.type === "file")
    ) {
      content.push({
        type: "file",
        mediaType: part.mediaType,
        data: new URL(part.url),
      });
    }
  }
  if (content.length === 0) return;

  try {
    const { text, usage } = await generateText({
      model: "anthropic/claude-haiku-4.5",
      system:
        "You title chats for a custom 3D-printed figurine design studio. " +
        "Given the customer's first message (and photo, if any), reply with ONLY a title: " +
        "3-6 words, no quotes, no trailing punctuation. Describe the subject when a photo " +
        "is attached, e.g. 'Couple on scooter figurine', 'Golden retriever figurine', " +
        "'ChatGPT design made printable'.",
      messages: [{ role: "user", content }],
    });
    const title = text.trim().replace(/^["'“]|["'”]$/g, "").slice(0, 80);
    if (title) await setSessionTitle(sessionId, title);
    // Counted in the same per-session bucket as chat turns (admin cost
    // column); a failure here must not surface, same as title generation.
    try {
      await recordUsage(sessionId, "anthropic/claude-haiku-4.5", usage);
    } catch (err) {
      console.error("usage recording failed", { sessionId, err });
    }
  } catch (err) {
    console.error("title generation failed", { sessionId, err });
  }
}
