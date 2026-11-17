import type { UIMessage } from "ai";
import { dbAvailable, loadAllMessages } from "@/lib/db";
import { deriveWorkspace, type WorkspaceImage } from "@/lib/workspace";
import { getSessionList } from "@/lib/session-list";

export type GalleryImage = WorkspaceImage & {
  sessionId: string;
  sessionTitle: string;
};

/**
 * Every image across the owner's sessions (uploads and generated designs
 * alike), newest chat first, each pointing back at its chat. Extraction
 * reuses deriveWorkspace, so the gallery shows exactly what the chats show.
 */
export async function getImageGallery(
  ownerId: string | null,
): Promise<GalleryImage[]> {
  if (!dbAvailable || !ownerId) return [];
  const [rows, sessions] = await Promise.all([
    loadAllMessages(ownerId),
    getSessionList(ownerId),
  ]);

  const bySession = new Map<string, UIMessage[]>();
  for (const r of rows) {
    const list = bySession.get(r.sessionId);
    if (list) list.push(r.message);
    else bySession.set(r.sessionId, [r.message]);
  }

  const gallery: GalleryImage[] = [];
  for (const s of sessions) {
    const msgs = bySession.get(s.id);
    if (!msgs) continue;
    for (const img of deriveWorkspace(msgs)) {
      gallery.push({ ...img, sessionId: s.id, sessionTitle: s.title });
    }
  }
  return gallery;
}
