import type { UIMessage } from "ai";
import { dbAvailable, listSessions } from "@/lib/db";

export type SessionListItem = {
  id: string;
  title: string;
  updatedAt: Date;
  messageCount: number;
};

/** Fallback title from a session's first message, when none was generated. */
export function sessionTitle(first: UIMessage | null): string {
  if (!first) return "New design";
  for (const part of first.parts) {
    if (part.type === "text" && part.text.trim()) {
      const t = part.text.trim();
      return t.length > 64 ? `${t.slice(0, 64)}…` : t;
    }
  }
  if (first.parts.some((p) => p.type === "file")) return "Photo upload";
  return "New design";
}

export function relativeTime(date: Date): string {
  const mins = Math.round((Date.now() - date.getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/**
 * The owner's sessions for the sidebar / history list, newest first:
 * generated title (fallback: first message), skipping empty sessions (stray
 * rows with no messages, e.g. from abandoned tabs). A null owner (no cookie,
 * e.g. non-browser client) sees no history at all — never everyone's.
 */
export async function getSessionList(
  ownerId: string | null,
): Promise<SessionListItem[]> {
  if (!dbAvailable || !ownerId) return [];
  const rows = await listSessions(100, ownerId);
  return rows
    .filter((r) => r.messageCount > 0)
    .map((r) => ({
      id: r.id,
      title: r.title ?? sessionTitle(r.firstMessage),
      updatedAt: r.updatedAt,
      messageCount: r.messageCount,
    }));
}
