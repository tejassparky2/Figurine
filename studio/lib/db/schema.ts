import {
  pgTable,
  text,
  integer,
  jsonb,
  doublePrecision,
  timestamp,
} from "drizzle-orm/pg-core";

/**
 * A design session = one chat. The id is the client-generated chat id (also
 * the /s/[id] URL). Rows are created lazily on the first message.
 */
export const sessions = pgTable("sessions", {
  id: text("id").primaryKey(),
  // Anonymous owner cookie id (see lib/owner.ts). Stamped on first write and
  // never reassigned; null on rows from before owner scoping existed — those
  // are only visible to admin, not in any /chats list.
  ownerId: text("owner_id"),
  // Short model-generated title from the first turn (see lib/title.ts);
  // null until generated — the UI falls back to the first message text.
  title: text("title"),
  // Id of the resumable UI-message stream currently being generated for this
  // session (lives in Redis via resumable-stream); null when idle. Lets a
  // client that lost its connection mid-generation reattach via
  // GET /api/chat/[id]/stream.
  activeStreamId: text("active_stream_id"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
  // Human follow-up state, surfaced in /admin. The WhatsApp column originally
  // belonged only to handoffs; it now stores the session's contact as soon as
  // the first image is submitted, so abandoned designs are contactable too.
  handoffAt: timestamp("handoff_at"),
  handoffReason: text("handoff_reason"),
  customerWhatsapp: text("handoff_whatsapp"),
  // The latest time an admin confirmed that they contacted this lead. A
  // later customer message/handoff makes the lead actionable again without
  // losing the history of the earlier follow-up.
  followedUpAt: timestamp("followed_up_at"),
  // Cumulative LLM usage across all turns (chat agent + title generation),
  // recorded per turn via recordUsage. costUsd is computed at write time from
  // the gateway price table in lib/cost.ts — tokens alone can't be priced
  // later because the two models bill differently. Image (fal) spend is NOT
  // here; it's derived from tool calls in message history (see lib/cost.ts).
  inputTokens: integer("input_tokens").default(0).notNull(),
  outputTokens: integer("output_tokens").default(0).notNull(),
  costUsd: doublePrecision("cost_usd").default(0).notNull(),
});

/**
 * Full UIMessage JSON per message, keyed by the UIMessage id. The message
 * parts are the single source of truth — the workspace and order spec are
 * re-derived from them exactly as the live app does.
 */
export const messages = pgTable("messages", {
  id: text("id").primaryKey(),
  sessionId: text("session_id").notNull(),
  seq: integer("seq").notNull(),
  message: jsonb("message").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

/** Legacy preview -> clean-original mappings retained for old chat history. */
export const imageVariants = pgTable("image_variants", {
  watermarkedUrl: text("watermarked_url").primaryKey(),
  cleanUrl: text("clean_url").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

/**
 * Captured order requests (issue #2). Written by the finalizeOrder tool once
 * a design + contact are confirmed.
 */
export const orders = pgTable("orders", {
  id: text("id").primaryKey(),
  sessionId: text("session_id").notNull(),
  imageUrl: text("image_url").notNull(),
  product: text("product").notNull(),
  size: text("size").notNull(),
  baseText: text("base_text"),
  priceInr: integer("price_inr"),
  whatsapp: text("whatsapp").notNull(),
  // Shopify checkout URL handed to the customer (issue #11); null for custom
  // products, which the team quotes and closes on WhatsApp.
  checkoutUrl: text("checkout_url"),
  status: text("status").default("new").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});
