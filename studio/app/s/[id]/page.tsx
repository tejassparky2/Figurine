import { Chat } from "@/components/chat";
import { loadMessages, loadSessionContact } from "@/lib/db";
import { getSessionList } from "@/lib/session-list";
import { getOwnerId } from "@/lib/owner";

export const dynamic = "force-dynamic";

/**
 * A design session. Messages (if any) are loaded from the DB and replayed —
 * the workspace and order spec re-derive from them on both client and server.
 */
export default async function SessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  // Session ids are client-minted UUIDs; reject anything else early.
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Invalid session link.
      </div>
    );
  }

  // The session itself loads by direct link (unlisted-URL model — shared
  // designs and admin need this); only the history sidebar is owner-scoped.
  const ownerId = await getOwnerId();
  const [initialMessages, sessions, initialWhatsapp] = await Promise.all([
    loadMessages(id),
    getSessionList(ownerId),
    loadSessionContact(id, ownerId),
  ]);
  return (
    <Chat
      id={id}
      initialMessages={initialMessages}
      sessions={sessions}
      initialWhatsapp={initialWhatsapp ?? undefined}
    />
  );
}
