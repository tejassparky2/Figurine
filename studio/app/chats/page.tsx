import Link from "next/link";
import { MessageSquare, Plus } from "lucide-react";
import { getSessionList, relativeTime } from "@/lib/session-list";
import { getOwnerId } from "@/lib/owner";

export const dynamic = "force-dynamic";

/**
 * This visitor's design sessions, newest first — same data as the chat
 * sidebar. Scoped by the anonymous owner cookie; nobody sees anyone else's
 * chats here.
 */
export default async function ChatsPage() {
  const sessions = await getSessionList(await getOwnerId());

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6 sm:py-10">
      <header className="mb-6 flex items-center justify-between gap-3">
        <h1 className="text-base font-semibold sm:text-lg">Chats</h1>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-secondary"
        >
          <Plus className="size-4" />
          New design
        </Link>
      </header>

      {sessions.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border py-16 text-center">
          <MessageSquare className="size-8 text-muted-foreground" />
          <p className="max-w-sm text-sm text-muted-foreground">
            No chats yet — start a design and it will show up here.
          </p>
        </div>
      ) : (
        <ul className="divide-y rounded-lg border">
          {sessions.map((s) => (
            <li key={s.id}>
              <Link
                href={`/s/${s.id}`}
                className="flex items-center justify-between gap-3 px-4 py-3.5 transition-colors hover:bg-secondary/50"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{s.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {s.messageCount} message{s.messageCount === 1 ? "" : "s"}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {relativeTime(s.updatedAt)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
