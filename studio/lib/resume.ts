import {
  createResumableStreamContext,
  type ResumableStreamContext,
} from "resumable-stream";
import { waitUntil } from "@vercel/functions";

/**
 * Shared context for resumable chat streams, backed by Redis (the
 * `resumable-stream` package reads REDIS_URL / KV_URL). While a generation
 * runs, its SSE stream is teed into Redis so a client that lost its
 * connection — mobile Safari kills the socket the moment the tab is
 * backgrounded — can reattach and replay via GET /api/chat/[id]/stream.
 *
 * Without Redis configured this returns null and the app behaves exactly as
 * before (plain one-shot streams), so local dev needs no extra setup.
 */
let ctx: ResumableStreamContext | null | undefined;

export function getStreamContext(): ResumableStreamContext | null {
  if (ctx === undefined) {
    ctx =
      process.env.REDIS_URL || process.env.KV_URL
        ? createResumableStreamContext({ waitUntil })
        : null;
  }
  return ctx;
}
