import { UI_MESSAGE_STREAM_HEADERS } from "ai";
import { getActiveStream, setActiveStream } from "@/lib/db";
import { getStreamContext } from "@/lib/resume";

// A resumed connection can live for the remainder of a 1–2 minute image
// generation, same as the POST that started it.
export const maxDuration = 300;

/**
 * Reattach to a generation in flight (or just finished) for this session.
 * Called by useChat — automatically on mount via `resume`, and via
 * resumeStream() when the client notices its connection died (mobile Safari
 * kills the socket when the tab is backgrounded). Replays the buffered
 * UI-message stream from Redis and stays attached while it's still live.
 * 204 means nothing to resume — the client keeps whatever state it has.
 */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const streamContext = getStreamContext();
  if (!streamContext) return new Response(null, { status: 204 });

  const streamId = await getActiveStream(id);
  if (!streamId) return new Response(null, { status: 204 });

  const stream = await streamContext.resumeExistingStream(streamId);
  if (!stream) {
    // Stream fully done and past its replay window (or unknown): the result,
    // if any, is already persisted in Postgres. Clear the stale pointer so
    // future mounts don't keep probing Redis.
    if (stream === null) await setActiveStream(id, null);
    return new Response(null, { status: 204 });
  }

  return new Response(stream, { headers: UI_MESSAGE_STREAM_HEADERS });
}
