import {
  createAgentUIStream,
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from "ai";
import { waitUntil } from "@vercel/functions";
import { studioAgent } from "@/lib/agent";
import { deriveSpec } from "@/lib/spec";
import { countImageOps, deriveWorkspace } from "@/lib/workspace";
import { clientIp, rateLimit } from "@/lib/ratelimit";
import {
  saveMessages,
  setActiveStream,
  debugEvent,
  recordUsage,
  loadSessionContact,
} from "@/lib/db";
import { generateAndSaveTitle } from "@/lib/title";
import { getStreamContext } from "@/lib/resume";
import { getOwnerId } from "@/lib/owner";
import { errStr, log } from "@/lib/log";
import { checkBotId } from "botid/server";

// Render passes can take a bit (bg removal + gpt-image); nano edits are ~seconds.
export const maxDuration = 300;

export async function POST(req: Request) {
  if (!process.env.AI_GATEWAY_API_KEY) {
    return Response.json(
      { error: "AI_GATEWAY_API_KEY not configured" },
      { status: 500 },
    );
  }

  // Bots never reach the paid APIs (issue #5). Always false in local dev.
  const { isBot } = await checkBotId();
  if (isBot) {
    log("warn", "bot_blocked", { route: "chat", ip: clientIp(req) });
    return Response.json({ error: "Access denied" }, { status: 403 });
  }

  // Spend protection (issue #5): a chat turn can trigger paid image calls,
  // so cap turns per IP. Generous window — Indian carriers CGNAT hard, so
  // one IP can be several real customers.
  const limited = await rateLimit(`chat:${clientIp(req)}`, 30, 10 * 60);
  if (!limited.ok) {
    log("warn", "rate_limited", { route: "chat", ip: clientIp(req) });
    return Response.json(
      {
        error:
          "You're sending messages quickly — please wait a few minutes and try again.",
      },
      { status: 429, headers: { "Retry-After": "600" } },
    );
  }

  // `id` is the chat/session id minted by the client (the /s/[id] URL).
  const { messages, id }: { messages: UIMessage[]; id?: string } =
    await req.json();

  // Stamps the session with this browser's anonymous owner id (first writer
  // wins — see saveMessages), which is what scopes /chats and /images.
  const ownerId = await getOwnerId();
  const customerWhatsapp = id
    ? await loadSessionContact(id, ownerId)
    : null;

  // Save the incoming turn up front so the user's message can never be lost,
  // even if the stream dies. The assistant message is added in onFinish.
  if (id) {
    try {
      await saveMessages(id, messages, ownerId);
      // A new turn supersedes whatever stream a previous turn left behind —
      // never let a reconnecting client resume an outdated one.
      await setActiveStream(id, null);
    } catch (err) {
      log("error", "save_failed", { phase: "pre-stream", id, err: errStr(err) });
    }
    // First turn of the session: generate its title in the background
    // (needs only the user message, not the reply).
    if (messages.filter((m) => m.role === "user").length === 1) {
      waitUntil(generateAndSaveTitle(id, messages));
    }
  }

  // Send the real error message to the client instead of the SDK's masked
  // "An error occurred" — we're pre-auth/pre-prod and debuggability wins.
  // Logged too (issue #4): the customer seeing an error banner we never see
  // was the worst observability gap.
  const onError = (err: unknown) => {
    log("error", "chat_stream_error", { id, err: errStr(err) });
    return err instanceof Error ? err.message : "Something went wrong";
  };

  // Token usage accumulates per step (tool loops = multiple LLM calls per
  // turn) and is recorded against the session in onFinish — that's what the
  // /admin cost column reads. Aborted streams still record what they spent.
  const usage = {
    inputTokens: 0,
    outputTokens: 0,
    inputTokenDetails: {
      noCacheTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
    },
  };

  // Everything the agent needs beyond the conversation is derived from the
  // conversation: the order spec and the image workspace both come out of
  // message history (same derivation the client uses for display).
  const agentStream = await createAgentUIStream({
    agent: studioAgent,
    uiMessages: messages,
    // Without this the response message has NO id ("" in the DB) — every
    // assistant message across all sessions then upserts into the same
    // primary-key row and clobbers it.
    generateMessageId: () => crypto.randomUUID(),
    options: {
      spec: deriveSpec(messages),
      images: deriveWorkspace(messages),
      imageOps: countImageOps(messages),
      sessionId: id,
      customerWhatsapp: customerWhatsapp ?? undefined,
    },
    onStepEnd: (step) => {
      usage.inputTokens += step.usage.inputTokens ?? 0;
      usage.outputTokens += step.usage.outputTokens ?? 0;
      usage.inputTokenDetails.noCacheTokens +=
        step.usage.inputTokenDetails.noCacheTokens ?? 0;
      usage.inputTokenDetails.cacheReadTokens +=
        step.usage.inputTokenDetails.cacheReadTokens ?? 0;
      usage.inputTokenDetails.cacheWriteTokens +=
        step.usage.inputTokenDetails.cacheWriteTokens ?? 0;
    },
    // Persist the full turn (history + new assistant message). waitUntil keeps
    // the serverless function alive for the write after the stream's last
    // byte — without it Vercel freezes the function and the save is lost.
    onFinish: (event) => {
      if (!id) return;
      const roles = event.messages.map((m) => m.role).join(",");
      waitUntil(
        (async () => {
          await debugEvent("onFinish:start", id, {
            roles,
            isAborted: event.isAborted,
            isContinuation: event.isContinuation,
            count: event.messages.length,
          });
          try {
            const result = await saveMessages(id, event.messages, ownerId);
            await debugEvent("onFinish:saved", id, {
              roles,
              ids: event.messages.map((m) => m.id),
              ...result,
            });
          } catch (err) {
            await debugEvent("onFinish:error", id, { err: String(err) });
            log("error", "save_failed", {
              phase: "onFinish",
              id,
              err: errStr(err),
            });
          }
          // Usage recording is best-effort — a missed turn skews the admin
          // cost column slightly but must never break persistence.
          try {
            await recordUsage(id, "anthropic/claude-sonnet-5", usage);
          } catch (err) {
            log("error", "usage_record_failed", { id, err: errStr(err) });
          }
          // Turn over: nothing left to resume. Clearing AFTER the messages
          // are saved means a reconnecting client always finds either the
          // live stream or the persisted result — never a gap.
          try {
            await setActiveStream(id, null);
          } catch (err) {
            log("error", "stream_state_failed", {
              phase: "clear",
              id,
              err: errStr(err),
            });
          }
        })(),
      );
    },
    onError,
  });

  // The image tools (figurine, edit, transform, print-prep) run for 1–2
  // minutes during which the agent emits nothing, so the SSE connection sits
  // idle. Mobile Safari aborts a fetch whose connection is idle that long —
  // it surfaces as "Chat request failed: Load failed" — while desktop
  // browsers tolerate it, which is why this only ever bit on phones. Pumping
  // the agent stream through a wrapper that interleaves a heartbeat every few
  // seconds keeps bytes flowing so the connection stays open. The heartbeat
  // is a transient data part: the client drops it (see processUIMessageStream)
  // and it never lands in message history.
  const stream = createUIMessageStream({
    onError,
    execute: async ({ writer }) => {
      const heartbeat = setInterval(() => {
        writer.write({ type: "data-heartbeat", data: null, transient: true });
      }, 10_000);
      try {
        for await (const chunk of agentStream) writer.write(chunk);
      } finally {
        clearInterval(heartbeat);
      }
    },
  });

  // Resumable streams (the once-and-for-all fix for mobile "Load failed"):
  // mobile browsers kill the fetch the moment the tab is backgrounded, which
  // no heartbeat can survive. So the SSE stream is teed into Redis
  // (resumable-stream) and the generation keeps running server-side — waitUntil
  // keeps the function alive — while the session row records which stream is
  // in flight. A returning client hits GET /api/chat/[id]/stream and replays
  // the whole thing, mid-generation or finished. Without Redis configured
  // consumeSseStream is omitted and behavior is exactly as before.
  return createUIMessageStreamResponse({
    stream,
    ...(id && getStreamContext()
      ? {
          consumeSseStream: async ({
            stream: sseStream,
          }: {
            stream: ReadableStream<string>;
          }) => {
            const streamContext = getStreamContext();
            if (!streamContext) return;
            const streamId = crypto.randomUUID();
            try {
              await streamContext.createNewResumableStream(
                streamId,
                () => sseStream,
              );
              await setActiveStream(id, streamId);
            } catch (err) {
              log("error", "stream_state_failed", {
                phase: "setup",
                id,
                err: errStr(err),
              });
            }
          },
        }
      : {}),
  });
}
