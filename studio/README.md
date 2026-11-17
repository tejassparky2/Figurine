# Everything 3D — Studio (v1)

A guided chat app where a customer designs **any 3D-printable model** and works
toward an order. The **signature product** is a photo → Pixar/DreamWorks-style
figurine, but customers can bring an image made elsewhere or just describe an
idea (a pet, a trophy, a dragon…). This is the thin **MVP** of the larger plan
in [`../everything3d_ai_figurine_studio_plan.md`](../everything3d_ai_figurine_studio_plan.md).

It lives as a subfolder of the `everything3d` monorepo and reuses the proven
render pipeline from [`../figurines/`](../figurines/) (background removal →
GPT-image-2 pixar render → proportion fix), ported to TypeScript so it runs in
the web app.

## What's in v1

- **Standard agent harness** — the agent is an AI SDK **`ToolLoopAgent`**
  (`lib/agent/index.ts`), served with `createAgentUIStreamResponse`. Product
  iteration happens in `lib/agent/prompt.ts` (instructions) and
  `lib/agent/tools.ts` (tools); the loop/streaming/plumbing is the framework's.
  Model `anthropic/claude-sonnet-5` via Vercel AI Gateway (see note below).
- **shadcn/ui + AI Elements UI** — `Conversation` (autoscroll), `Message` /
  `MessageResponse` (markdown), `PromptInput` (composer with attach-photo button,
  Enter-to-send, streaming/stop states).
- **Advisor agent** — the instructions give it a goal + the 3D-printability
  rubric and tell it to guide the customer (flag un-printable requests / photo
  issues, suggest good alternatives). It's multimodal — uploaded photos are
  attached as file parts so it can *see* and assess them.
- **Image workspace** (`lib/workspace.ts`) — every uploaded/generated image gets
  a stable id (derived from message history on client + server). Tools reference
  images by id; ids resolve against a per-request tool context.
- **Five tools**: `updateOrderSpecification`, `generatePixarFigurine`
  (signature photo-of-a-person → figurine pipeline, gpt-image-2; returns Pixar
  and simplified-realistic styles side by side, with Pixar recommended),
  `editImage`
  (pointed single-change edit, nano-banana-lite), `transformImage` (full-image
  change, gpt-image-2 edit), `makePrintable` (bring-your-own design →
  print-ready, gpt-image-2 edit with the proven conversion prompt).
- **Right model per edit scope** — nano-banana-lite (~7s, ~$0.05, multi-image)
  is great at pointed edits that must leave the rest of the image untouched,
  but bad at whole-image transformations; those (and 3D-printable conversion)
  run on gpt-image-2 edit (~1 min, ~$0.06). Pointed revisions still go from a
  ~90s full regen to a ~7s edit, and multi-image lets it e.g. fix a face using
  the original photo.
- **Generative UI** — `components/image-card.tsx` renders every image tool output
  (loading → image → **Keep / Revise**).
- **Structured `OrderSpec`** in a live order-summary sidebar, derived from
  message history on both client and server (nothing extra in the request body).
- Printability is also **enforced server-side** (`lib/render.ts` guard) on the
  gpt-image-2 paths (generate / transform / makePrintable), not just requested
  by the agent. Pointed nano edits deliberately get a **minimal prompt** — no
  rubric text — because nano-banana-lite changes things it shouldn't when the
  prompt carries extra constraints; those edits start from an already-printable
  image and must only preserve it.

## What's deliberately NOT in v1 yet

(All in the plan, added in later phases.) Auth (Clerk), Neon/Drizzle DB,
Vercel Blob, Shopify cart/checkout, BotID, rate limits & quotas,
clickable pose/outfit/style picker cards, design deposit.

## Run it

```bash
cd studio
cp .env.local.example .env.local   # then fill in the two keys
npm run dev
# open http://localhost:3000
```

Environment (`studio/.env.local`):

- `FAL_KEY` — fal.ai key (shared with the figurines pipeline, `figurines/.env`).
  Used for photo upload + the BiRefNet/GPT-image-2 render calls.
- `AI_GATEWAY_API_KEY` — Vercel AI Gateway key for the chat agent. Create one at
  https://vercel.com/<team>/~/ai-gateway/api-keys.
- `DATABASE_URL` (optional) — Neon Postgres for session persistence (Vercel
  Marketplace Neon integration). Without it the app works but sessions are
  lost on refresh. After setting it, run `npm run db:push` once.
- `ADMIN_TOKEN` (optional) — enables the internal `/admin?token=…` follow-up
  queue. The page tracks contacted leads and can show browser notifications
  while it is open.

### Note on the chat model

The chat agent uses Vercel AI Gateway. If the gateway account does not have
access to paid Anthropic models, `anthropic/claude-sonnet-5` may fail at runtime;
switch `model` in `lib/agent/index.ts` back to a lower-cost model for local or
free-tier testing.

## Architecture

```
app/page.tsx                  redirects to a fresh /s/[uuid] session
app/s/[id]/page.tsx           loads persisted messages, renders the chat
app/admin/page.tsx            internal lead follow-up queue (/admin?token=ADMIN_TOKEN)
components/chat.tsx           Chat UI (AI Elements) + photo upload + order-summary sidebar
app/api/chat/route.ts         thin HTTP wrapper: derive spec+workspace -> agent -> stream;
                              persists each turn via lib/db (no-op without DATABASE_URL)
app/api/upload/route.ts       multipart upload -> fal storage -> URL
lib/db/                       Neon + Drizzle: sessions, messages, orders schema
lib/agent/index.ts            the ToolLoopAgent definition (rarely changes)
lib/agent/prompt.ts           agent instructions — iterate here
lib/agent/tools.ts            the 5 tools — iterate here
lib/agent/context.ts          per-request context (spec + images) + id resolution
lib/render.ts                 fal calls: removeBg, gptEdit, nanoEdit + printability
                              guard (PRINTABILITY, edit/full-edit/printable prompts)
lib/workspace.ts              WorkspaceImage type + deriveWorkspace(messages)
lib/spec.ts                   OrderSpec zod schema + deriveSpec(messages)
components/image-card.tsx     generative-UI card for image tool outputs
components/ai-elements/*      shadcn AI Elements (conversation, message, prompt-input, ...)
components/ui/*               shadcn primitives
scripts/bench-*.mjs           fal edit-model benchmark scripts
```

Tools take image **ids**, not URLs — ids resolve against the per-request tool
context (`contextSchema`/`toolsContext`), which the route derives from message
history. The final image prompts are wrapped server-side: the agent authors
descriptions/instructions, `lib/render.ts` appends the printability guard so it
can never be dropped.

A figurine preview = 1 BiRefNet call + 2 parallel styles: Pixar uses a medium
render plus low-cost proportion fix, while realistic uses one medium render.
Wall time is ~1–2 min and estimated cost is ~$0.14. Routes set
`maxDuration` for Vercel; the render route needs Fluid Compute / a paid plan for
the long duration in production.

## Dev notes / gotchas

- **shadcn must use the Radix base.** The default `npx shadcn init -d` now picks
  the Base UI style (`base-nova`), which throws type errors with AI Elements.
  This project was initialized with `--base radix`. If you re-init, use
  `--base radix` and re-add components with `-o`.
- After any shadcn init, fix the circular `--font-sans: var(--font-sans)` it
  writes into `app/globals.css` — use the literal `"Geist"` font name instead.

## Next steps (toward the plan)

1. Clickable style/type/pose **picker cards** (generative UI for structured
   choices, not just typed answers).
2. Persist sessions + previews (Neon + Drizzle, Vercel Blob).
3. Add Clerk auth; gate upload + generate behind login.
4. Add quotas / rate limits / BotID.
5. Shopify cart creation with a `design_session_id` custom attribute.
