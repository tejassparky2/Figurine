import { loadMessages } from "@/lib/db";

/**
 * The session's persisted messages, for client-side recovery. A resumable
 * stream is only replayable while its producer is alive; once the turn
 * finished (or the stream expired) the DB is the source of truth, and a
 * client that was away too long reconciles its state from here.
 */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const messages = await loadMessages(id);
  return Response.json({ messages });
}
