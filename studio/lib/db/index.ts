import { neon } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-http";
import { and, asc, desc, eq, isNull, or, sql } from "drizzle-orm";
import type { UIMessage } from "ai";
import { sessions, messages, orders, imageVariants } from "./schema";
import { llmCostUsd, type ImageOpCounts } from "@/lib/cost";

/**
 * Persistence is optional: without DATABASE_URL everything no-ops and the app
 * behaves like before (in-memory sessions, lost on refresh). This lets local
 * dev and the first deploy work before Neon is connected.
 */
const url = process.env.DATABASE_URL;

const db = url ? drizzle(neon(url)) : null;

export const dbAvailable = Boolean(db);

/** Save a visitor's WhatsApp number against their session. */
export async function saveSessionContact(
  sessionId: string,
  ownerId: string,
  whatsapp: string,
): Promise<boolean> {
  if (!db) return false;

  // A shared /s/{id} link may be viewed by anyone, but only the browser that
  // owns the session may attach or replace its private contact details. Keep
  // this check in the upsert itself so two simultaneous claims cannot race.
  const saved = await db
    .insert(sessions)
    .values({
      id: sessionId,
      ownerId,
      customerWhatsapp: whatsapp,
    })
    .onConflictDoUpdate({
      target: sessions.id,
      set: {
        updatedAt: sql`now()`,
        ownerId: sql`coalesce(${sessions.ownerId}, excluded.owner_id)`,
        customerWhatsapp: whatsapp,
      },
      setWhere: or(
        isNull(sessions.ownerId),
        eq(sessions.ownerId, ownerId),
      ),
    })
    .returning({ id: sessions.id });
  if (saved.length === 0) {
    throw new Error("session belongs to another visitor");
  }
  return true;
}

/** Load private contact details only for the session's owning browser. */
export async function loadSessionContact(
  sessionId: string,
  ownerId: string | null,
): Promise<string | null> {
  if (!db || !ownerId) return null;
  const rows = await db
    .select({ whatsapp: sessions.customerWhatsapp })
    .from(sessions)
    .where(and(eq(sessions.id, sessionId), eq(sessions.ownerId, ownerId)))
    .limit(1);
  return rows[0]?.whatsapp ?? null;
}

/** Load a session's messages in order. Empty array if none / no DB. */
export async function loadMessages(sessionId: string): Promise<UIMessage[]> {
  if (!db) return [];
  const rows = await db
    .select({ message: messages.message })
    .from(messages)
    .where(eq(messages.sessionId, sessionId))
    .orderBy(asc(messages.seq));
  return rows.map((r) => r.message as UIMessage);
}

/**
 * Upsert the full message list for a session (idempotent; message ids are
 * stable). Called once per chat turn with user + assistant messages included.
 */
export async function saveMessages(
  sessionId: string,
  msgs: UIMessage[],
  ownerId?: string | null,
): Promise<{ rowCount: number | null; visible: number }> {
  if (!db || msgs.length === 0) return { rowCount: null, visible: -1 };

  await db
    .insert(sessions)
    .values({ id: sessionId, ownerId: ownerId ?? null })
    .onConflictDoUpdate({
      target: sessions.id,
      // First writer claims the session; an existing owner is never
      // reassigned (a shared /s/{id} link must not steal the chat).
      set: {
        updatedAt: sql`now()`,
        ownerId: sql`coalesce(${sessions.ownerId}, excluded.owner_id)`,
      },
    });

  // Belt-and-braces: a message without an id would collide across sessions
  // on the primary key. Give it a deterministic per-session id instead.
  const res = await db
    .insert(messages)
    .values(
      msgs.map((m, seq) => ({
        id: m.id || `${sessionId}:${seq}`,
        sessionId,
        seq,
        message: m,
      })),
    )
    .onConflictDoUpdate({
      target: messages.id,
      set: {
        // Assistant messages grow as tool results stream in; keep latest.
        message: sql`excluded.message`,
        seq: sql`excluded.seq`,
      },
    });

  // TEMP diagnostics for the prod message-loss bug: what did PG report, and
  // what does the same connection see immediately after?
  const check = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(messages)
    .where(eq(messages.sessionId, sessionId));
  return {
    rowCount: (res as unknown as { rowCount?: number }).rowCount ?? null,
    visible: check[0]?.n ?? -1,
  };
}

/**
 * TEMPORARY debugging: record persistence attempts in the DB itself, since
 * Vercel logs aren't accessible in this workflow. Remove once the prod
 * message-loss bug is understood.
 */
export async function debugEvent(
  phase: string,
  sessionId: string,
  detail: unknown,
): Promise<void> {
  if (!url) return;
  try {
    await neon(url)`insert into debug_events (phase, session_id, detail) values (${phase}, ${sessionId}, ${JSON.stringify(detail)})`;
  } catch {
    // never let debugging break the app
  }
}

/**
 * Point the session at the resumable stream currently generating for it
 * (or clear it with null when the turn finishes). Upserts because the very
 * first turn's stream can start before the session row exists.
 */
export async function setActiveStream(
  sessionId: string,
  streamId: string | null,
): Promise<void> {
  if (!db) return;
  await db
    .insert(sessions)
    .values({ id: sessionId, activeStreamId: streamId })
    .onConflictDoUpdate({
      target: sessions.id,
      set: { activeStreamId: streamId },
    });
}

/** The session's in-flight stream id, if a generation is (or was) running. */
export async function getActiveStream(
  sessionId: string,
): Promise<string | null> {
  if (!db) return null;
  const rows = await db
    .select({ activeStreamId: sessions.activeStreamId })
    .from(sessions)
    .where(eq(sessions.id, sessionId))
    .limit(1);
  return rows[0]?.activeStreamId ?? null;
}

export type NewOrder = typeof orders.$inferInsert;

/**
 * Every message across the given owner's sessions (or all sessions when no
 * owner is passed — admin only), in per-session order, for the image gallery.
 * Fine at current volume (a few hundred rows); paginate when the studio
 * outgrows it.
 */
export async function loadAllMessages(
  ownerId?: string,
): Promise<{ sessionId: string; message: UIMessage }[]> {
  if (!db) return [];
  const rows = await db
    .select({ sessionId: messages.sessionId, message: messages.message })
    .from(messages)
    .innerJoin(sessions, eq(messages.sessionId, sessions.id))
    .where(ownerId === undefined ? undefined : eq(sessions.ownerId, ownerId))
    .orderBy(asc(messages.sessionId), asc(messages.seq));
  return rows.map((r) => ({
    sessionId: r.sessionId,
    message: r.message as UIMessage,
  }));
}

/**
 * Record one turn's LLM usage against a session (issue: admin cost display).
 * Increments the cumulative counters; cost is priced at write time from the
 * gateway price table (lib/cost.ts). Unknown model -> tokens still recorded,
 * cost contribution 0. Upserts because a turn can finish before the session
 * row exists (same race as setActiveStream).
 */
export async function recordUsage(
  sessionId: string,
  model: string,
  usage: {
    inputTokens?: number;
    outputTokens?: number;
    inputTokenDetails?: {
      noCacheTokens?: number;
      cacheReadTokens?: number;
      cacheWriteTokens?: number;
    };
  },
): Promise<void> {
  if (!db) return;
  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  if (inputTokens === 0 && outputTokens === 0) return;
  const costUsd =
    llmCostUsd(model, inputTokens, outputTokens, usage.inputTokenDetails) ?? 0;
  await db
    .insert(sessions)
    .values({ id: sessionId, inputTokens, outputTokens, costUsd })
    .onConflictDoUpdate({
      target: sessions.id,
      set: {
        inputTokens: sql`${sessions.inputTokens} + excluded.input_tokens`,
        outputTokens: sql`${sessions.outputTokens} + excluded.output_tokens`,
        costUsd: sql`${sessions.costUsd} + excluded.cost_usd`,
      },
    });
}

/** Set a session's generated title; never overwrites an existing one. */
export async function setSessionTitle(
  sessionId: string,
  title: string,
): Promise<void> {
  if (!db) return;
  await db
    .update(sessions)
    .set({ title })
    .where(and(eq(sessions.id, sessionId), isNull(sessions.title)));
}

/**
 * Flag a session for human follow-up (issue #17). Throws without a DB —
 * the tool falls back to giving the customer the direct WhatsApp number.
 */
export async function flagHandoff(
  sessionId: string,
  reason: string,
  whatsapp?: string,
): Promise<void> {
  if (!db) throw new Error("no database configured");
  await db
    .insert(sessions)
    .values({
      id: sessionId,
      handoffAt: sql`now()`,
      handoffReason: reason,
      customerWhatsapp: whatsapp,
    })
    .onConflictDoUpdate({
      target: sessions.id,
      set: {
        handoffAt: sql`now()`,
        handoffReason: reason,
        customerWhatsapp: whatsapp ?? sql`${sessions.customerWhatsapp}`,
      },
    });
}

/** Sessions flagged for human follow-up, newest first, for /admin. */
export async function listHandoffs(limit = 50) {
  if (!db) return [];
  return db
    .select({
      id: sessions.id,
      title: sessions.title,
      handoffAt: sessions.handoffAt,
      handoffReason: sessions.handoffReason,
      handoffWhatsapp: sessions.customerWhatsapp,
    })
    .from(sessions)
    .where(sql`${sessions.handoffAt} is not null`)
    .orderBy(desc(sessions.handoffAt))
    .limit(limit);
}

/** Mark a contactable lead as followed up, or put it back in the queue. */
export async function setLeadFollowedUp(
  sessionId: string,
  followedUp: boolean,
): Promise<boolean> {
  if (!db) return false;
  const rows = await db
    .update(sessions)
    .set({ followedUpAt: followedUp ? sql`now()` : null })
    .where(
      and(
        eq(sessions.id, sessionId),
        // Same reachability rule as listLeads: a captured contact, or an
        // order that carries one.
        sql`(${sessions.customerWhatsapp} is not null or exists (
          select 1 from ${orders} o where o.session_id = ${sessions}.id
        ))`,
      ),
    )
    .returning({ id: sessions.id });
  return rows.length > 0;
}

/**
 * A filed order, as carried on its lead. createdAt arrives as a string —
 * jsonb has no date type — formatted with an explicit Z so it re-hydrates
 * as UTC like every other timestamp column, whatever the server's zone.
 */
export type LeadOrder = {
  id: string;
  product: string;
  size: string;
  baseText: string | null;
  priceInr: number | null;
  whatsapp: string;
  checkoutUrl: string | null;
  imageUrl: string;
  createdAt: string;
};

/**
 * Every contactable lead for the admin queue, without the heavier cost data.
 * A filed order is not a sale — the team still has to collect payment on
 * WhatsApp — so ordering sessions are leads too, and their latest order
 * rides along instead of living in a separate list. A session that somehow
 * filed an order without a captured contact is still included: the order
 * carries a WhatsApp number of its own.
 */
export async function listLeads() {
  if (!db) return [];
  return db
    .select({
      id: sessions.id,
      title: sessions.title,
      customerWhatsapp: sessions.customerWhatsapp,
      followedUpAt: sessions.followedUpAt,
      handoffAt: sessions.handoffAt,
      handoffReason: sessions.handoffReason,
      updatedAt: sessions.updatedAt,
      messageCount: sql<number>`(
        select count(*)::int from ${messages} m where m.session_id = ${sessions}.id
      )`,
      firstMessage: sql<UIMessage | null>`(
        select m.message from ${messages} m
        where m.session_id = ${sessions}.id
        order by m.seq asc limit 1
      )`,
      orderCount: sql<number>`(
        select count(*)::int from ${orders} o where o.session_id = ${sessions}.id
      )`,
      latestOrder: sql<LeadOrder | null>`(
        select jsonb_build_object(
          'id', o.id,
          'product', o.product,
          'size', o.size,
          'baseText', o.base_text,
          'priceInr', o.price_inr,
          'whatsapp', o.whatsapp,
          'checkoutUrl', o.checkout_url,
          'imageUrl', o.image_url,
          'createdAt', to_char(o.created_at, 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
        )
        from ${orders} o
        where o.session_id = ${sessions}.id
        order by o.created_at desc limit 1
      )`,
    })
    .from(sessions)
    .where(
      sql`${sessions.customerWhatsapp} is not null or exists (
        select 1 from ${orders} o where o.session_id = ${sessions}.id
      )`,
    )
    .orderBy(desc(sessions.updatedAt));
}

/**
 * Resolve a historical watermarked preview to its clean original. New
 * previews are unwatermarked and pass through unchanged. Keep this legacy
 * lookup so old chats can still be edited and ordered from their originals.
 */
export async function cleanUrlFor(url: string): Promise<string> {
  if (!db) return url;
  try {
    const rows = await db
      .select({ cleanUrl: imageVariants.cleanUrl })
      .from(imageVariants)
      .where(eq(imageVariants.watermarkedUrl, url))
      .limit(1);
    return rows[0]?.cleanUrl ?? url;
  } catch (err) {
    console.error("cleanUrlFor failed", err);
    return url;
  }
}

/** Store a captured order. Throws if there is no DB — callers must handle. */
export async function saveOrder(order: NewOrder): Promise<void> {
  if (!db) throw new Error("no database configured");
  await db.insert(orders).values(order);
}

/**
 * Recent sessions with message counts, newest first, for the admin list and
 * the /chats history. The first message rides along so the UI can derive a
 * human-readable title. Pass an ownerId to scope to one visitor's sessions;
 * omitting it returns everything and is for admin use only.
 */
export async function listSessions(limit = 100, ownerId?: string) {
  if (!db) return [];
  return db
    .select({
      id: sessions.id,
      title: sessions.title,
      customerWhatsapp: sessions.customerWhatsapp,
      followedUpAt: sessions.followedUpAt,
      handoffAt: sessions.handoffAt,
      handoffReason: sessions.handoffReason,
      createdAt: sessions.createdAt,
      updatedAt: sessions.updatedAt,
      // NB: ${sessions}.id, not ${sessions.id} — drizzle renders the latter
      // unqualified ("id") inside a subquery, which resolves to the inner
      // messages table and matches nothing.
      messageCount: sql<number>`(
        select count(*)::int from ${messages} m where m.session_id = ${sessions}.id
      )`,
      firstMessage: sql<UIMessage | null>`(
        select m.message from ${messages} m
        where m.session_id = ${sessions}.id
        order by m.seq asc limit 1
      )`,
      // LLM usage recorded by recordUsage (0 for sessions that predate it).
      inputTokens: sessions.inputTokens,
      outputTokens: sessions.outputTokens,
      costUsd: sessions.costUsd,
      // Completed image tool calls per cost group, counted from message
      // history (same derivation as lib/workspace.ts countImageOps). fal
      // spend per call is estimated in lib/cost.ts. An aggregate over zero
      // rows still returns one row, so this is never null.
      imageOps: sql<ImageOpCounts>`(
        select jsonb_build_object(
          'figurine', count(*) filter (where p ->> 'type' = 'tool-generatePixarFigurine'),
          'gptEdit', count(*) filter (where p ->> 'type' in ('tool-transformImage', 'tool-makePrintable')),
          'nanoEdit', count(*) filter (where p ->> 'type' = 'tool-editImage')
        )
        from ${messages} m,
        lateral jsonb_array_elements(m.message -> 'parts') p
        where m.session_id = ${sessions}.id
          and m.message ->> 'role' = 'assistant'
          and p ->> 'state' = 'output-available'
          and p ->> 'type' in (
            'tool-generatePixarFigurine', 'tool-editImage',
            'tool-transformImage', 'tool-makePrintable'
          )
      )`,
    })
    .from(sessions)
    .where(ownerId === undefined ? undefined : eq(sessions.ownerId, ownerId))
    .orderBy(desc(sessions.updatedAt))
    .limit(limit);
}
