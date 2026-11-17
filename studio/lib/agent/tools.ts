import { tool } from "ai";
import { z } from "zod";
import {
  generateFigurineStyles,
  nanoEdit,
  gptEdit,
  editPrompt,
  fullEditPrompt,
  MAKE_PRINTABLE_PROMPT,
} from "@/lib/render";
import { specPatchSchema } from "@/lib/spec";
import { cleanUrlFor, flagHandoff, saveOrder } from "@/lib/db";
import { createCheckoutUrl } from "@/lib/shopify";
import { errStr, log } from "@/lib/log";
import {
  agentContextSchema,
  imageBudgetExceeded,
  resolveImage,
} from "./context";

/** Log a tool failure (issue #4 — these used to fail silently) and produce
 * the { error } result the model sees. */
function toolError(tool: string, err: unknown) {
  log("error", "tool_failed", { tool, err: errStr(err) });
  return { error: err instanceof Error ? err.message : "failed" };
}

// Price list (Rs., taxes included) — computed server-side, never by the
// model. Mirrors the live variants on everything3dindia.com (single uses the
// small-base variant prices; podium base isn't offered in the studio yet).
const PRICE_INR: Record<string, Record<string, number>> = {
  single: { "13cm": 4499, "15cm": 5499, "18cm": 6499 },
  couple: { "13cm": 6999, "15cm": 7999, "18cm": 8999 },
  pet: { "13cm": 6499, "15cm": 7499, "18cm": 8499 },
  family: { "13cm": 10499, "15cm": 11499, "18cm": 12499 },
};

// The team's WhatsApp number (digits only, for wa.me links).
const TEAM_WHATSAPP = "917892554719";

/**
 * The studio agent's tools. Image tools take workspace image IDS, never urls —
 * the ids are resolved against the per-request AgentContext, so the model can
 * only ever touch images that actually exist in this session.
 *
 * Model choice per tool (learned from real use):
 * - nano-banana-lite: great at POINTED edits (leaves the rest of the image
 *   alone), bad at whole-image transformations.
 * - gpt-image-2 edit: slower, but the only thing that works for full-image
 *   changes and 3D-printable conversions.
 */
export const tools = {
  askUser: tool({
    description:
      "Ask the customer ONE question and show 2-4 tappable quick-reply buttons. Use whenever your question has a small set of natural answers (keep pose vs standing, size, yes/no, color choices) — most customers tap instead of typing. The question is displayed with the buttons, so do NOT also write it in text. Each option must be a short, self-contained answer.",
    inputSchema: z.object({
      question: z.string().describe("The question to show the customer."),
      options: z
        .array(z.string())
        .min(2)
        .max(4)
        .describe(
          "2-4 short tap options, each a complete answer on its own, e.g. ['Keep the hugging pose from the photo', 'Standard standing pose'].",
        ),
    }),
    // No execute on purpose: the agent loop stops here and waits. The
    // customer's tap (or typed reply) is filled in as the tool output by the
    // client, which then continues the conversation.
  }),

  updateOrderSpecification: tool({
    description:
      "Record or update the customer's confirmed order choices: size (13cm/18cm for figurines) and base text. Pass only the fields that changed.",
    inputSchema: specPatchSchema,
    execute: async (patch) => patch,
  }),

  generatePixarFigurine: tool({
    description:
      "Signature product ONLY: turn an uploaded PHOTO of a real person or couple into TWO style previews — Pixar/DreamWorks first (recommended) and simplified realistic second. Ask the customer to pick a style, then continue on the chosen image. Never use it on an image that is already a design/figurine (e.g. brainstormed in ChatGPT) — use makePrintable for those. Takes 1-2 minutes.",
    inputSchema: z.object({
      fromImageId: z
        .string()
        .describe("Workspace id of the uploaded photo to render from."),
      notes: z
        .string()
        .optional()
        .describe(
          "Optional clothing/detail notes, e.g. 'red saree with gold border'.",
        ),
      preservePose: z
        .string()
        .optional()
        .describe(
          "Only when the customer confirmed they want the photo's own pose kept (default is a simple standing pose): describe the pose SPECIFICALLY from what you see in the photo — who is where, how they're positioned relative to each other, and notable accessories, e.g. 'woman seated with both arms wrapped around her fawn boxer lying across her lap, dog wearing a yellow party hat'.",
        ),
    }),
    contextSchema: agentContextSchema,
    execute: async ({ fromImageId, notes, preservePose }, { context }) => {
      const capped = imageBudgetExceeded(context, "figurine");
      if (capped) return capped;
      const url = resolveImage(context, fromImageId);
      if (!url) return { error: `No image with id ${fromImageId}.` };
      try {
        const r = await generateFigurineStyles(await cleanUrlFor(url), {
          quality: "medium",
          extraDetails: notes,
          preservePose,
        });
        return {
          imageUrls: r.styleUrls,
          optionLabels: ["Pixar style", "Realistic style"],
          optionDescriptions: [
            "Our signature stylized look",
            "Closer to your photo, simplified for printing",
          ],
          recommendedIndex: 0,
          label: "figurine preview",
        };
      } catch (err) {
        return toolError("generatePixarFigurine", err);
      }
    },
  }),

  editImage: tool({
    description:
      "POINTED edit: change one specific thing and leave the rest of the image untouched (remove the handbag, add glasses, change the shirt to blue, fix a mismatched face). Fast (~seconds). Optionally pass reference image ids to guide the edit (e.g. the original photo to fix a face). NOT for changes that affect the whole image — use transformImage for those.",
    inputSchema: z.object({
      targetImageId: z
        .string()
        .describe("Workspace id of the image to edit."),
      referenceImageIds: z
        .array(z.string())
        .optional()
        .describe(
          "Optional workspace ids of reference images to guide the edit, e.g. the customer's original photo.",
        ),
      instruction: z
        .string()
        .describe(
          "The one thing to change, in plain language, e.g. 'remove the handbag' or 'make the face match the reference photo'.",
        ),
    }),
    contextSchema: agentContextSchema,
    execute: async (
      { targetImageId, referenceImageIds, instruction },
      { context },
    ) => {
      const capped = imageBudgetExceeded(context, "edit");
      if (capped) return capped;
      const targetUrl = resolveImage(context, targetImageId);
      if (!targetUrl) return { error: `No image with id ${targetImageId}.` };
      const refUrls = (referenceImageIds ?? [])
        .map((id) => resolveImage(context, id))
        .filter((u): u is string => Boolean(u));
      try {
        // Resolve previews from older chats that predate watermark removal to
        // their clean originals before continuing an edit chain.
        const cleanUrls = await Promise.all(
          [targetUrl, ...refUrls].map(cleanUrlFor),
        );
        const imageUrl = await nanoEdit(cleanUrls, editPrompt(instruction));
        return { imageUrl, label: "edited design" };
      } catch (err) {
        return toolError("editImage", err);
      }
    },
  }),

  transformImage: tool({
    description:
      "FULL-IMAGE edit: when the change affects the whole image — overall style, proportions, color scheme, pose overhaul, big restructuring. Slower (~1 minute). For changing one specific thing, use editImage instead (much faster).",
    inputSchema: z.object({
      targetImageId: z
        .string()
        .describe("Workspace id of the image to transform."),
      instruction: z
        .string()
        .describe(
          "The transformation, in plain language, e.g. 'make the whole figure chibi-proportioned with an oversized head'.",
        ),
    }),
    contextSchema: agentContextSchema,
    execute: async ({ targetImageId, instruction }, { context }) => {
      const capped = imageBudgetExceeded(context, "edit");
      if (capped) return capped;
      const targetUrl = resolveImage(context, targetImageId);
      if (!targetUrl) return { error: `No image with id ${targetImageId}.` };
      try {
        const imageUrl = await gptEdit(
          [await cleanUrlFor(targetUrl)],
          fullEditPrompt(instruction),
        );
        return { imageUrl, label: "reworked design" };
      } catch (err) {
        return toolError("transformImage", err);
      }
    },
  }),

  proposeOrder: tool({
    description:
      "Show the customer an interactive order card for the design they want to buy: a live zero-credit preview of the figurine on its base, size choices with prices, base text, a WhatsApp field, and a Place-order button. Call it the moment they confirm which design to order — do NOT ask size, base text, or WhatsApp in text; the card collects all of those. Their tap comes back as a 'Place my order: …' message.",
    inputSchema: z.object({
      imageId: z
        .string()
        .describe("Workspace id of the approved design image."),
      product: z
        .enum(["single", "couple", "pet", "family", "custom"])
        .describe(
          "single = 1 person figurine, couple = 2 people OR 1 person with their vehicle (bike, car, etc.), pet = person+pet, family = 3-4 people, custom = anything else (team quotes the price).",
        ),
      baseText: z
        .string()
        .optional()
        .describe("Base text, only if already discussed — prefills the card."),
    }),
    contextSchema: agentContextSchema,
    execute: async ({ imageId, product, baseText }, { context }) => {
      const imageUrl = resolveImage(context, imageId);
      if (!imageUrl) return { error: `No image with id ${imageId}.` };
      return {
        imageUrl,
        product,
        baseText,
        // Price per size, computed here — never by the model. null = custom,
        // quoted by the team on WhatsApp.
        prices: PRICE_INR[product] ?? null,
      };
    },
  }),

  finalizeOrder: tool({
    description:
      "File the customer's order request. Call it when their 'Place my order: …' message arrives (after proposeOrder), passing exactly the size, base text, and WhatsApp number it contains. The team then contacts them on WhatsApp to take payment.",
    inputSchema: z.object({
      imageId: z
        .string()
        .describe("Workspace id of the FINAL confirmed design image."),
      product: z
        .enum(["single", "couple", "pet", "family", "custom"])
        .describe(
          "single = 1 person figurine, couple = 2 people OR 1 person with their vehicle (bike, car, etc.), pet = person+pet, family = 3-4 people, custom = anything else (team quotes the price).",
        ),
      size: z.enum(["13cm", "15cm", "18cm"]),
      baseText: z.string().optional().describe("Text engraved on the base."),
      whatsapp: z
        .string()
        .describe("Customer's WhatsApp number, with country code if given."),
    }),
    contextSchema: agentContextSchema,
    execute: async (
      { imageId, product, size, baseText, whatsapp },
      { context },
    ) => {
      const imageUrl = resolveImage(context, imageId);
      if (!imageUrl) return { error: `No image with id ${imageId}.` };

      const digits = whatsapp.replace(/\D/g, "");
      if (digits.length < 10 || digits.length > 14) {
        return {
          error:
            "That WhatsApp number doesn't look valid — ask the customer for a 10-digit number (or with country code).",
        };
      }

      const priceInr = PRICE_INR[product]?.[size] ?? null;

      // Standard products get a prefilled Shopify checkout so the customer
      // can pay right away; custom ones stay on the WhatsApp path (null).
      const checkoutUrl = await createCheckoutUrl({
        product,
        size,
        baseText,
        previewImageUrl: imageUrl,
        sessionId: context.sessionId,
      });

      const order = {
        id: crypto.randomUUID(),
        sessionId: context.sessionId ?? "unknown",
        // Resolve previews from older chats to their clean originals. New
        // previews are returned directly without any display processing.
        imageUrl: await cleanUrlFor(imageUrl),
        product,
        size,
        baseText,
        priceInr,
        whatsapp: digits,
        checkoutUrl,
      };

      try {
        await saveOrder(order);
      } catch (err) {
        log("error", "tool_failed", { tool: "finalizeOrder", err: errStr(err) });
        return {
          error:
            "Could not record the order right now. Apologize and ask the customer to WhatsApp us directly at +91 78925 54719 with their design.",
        };
      }

      return {
        ok: true,
        product,
        size,
        baseText,
        priceInr,
        whatsapp: digits,
        imageUrl,
        checkoutUrl,
      };
    },
  }),

  handoffToHuman: tool({
    description:
      "Transfer the customer to a human team member. Call it immediately when they request extra customization the standard preview cannot reliably handle (such as a logo, readable text on the figure, bespoke branding/materials), when they ask for a human, after repeated failure, or when they're frustrated. The saved session WhatsApp is used automatically; only ask for one if the context says none is captured. The team sees the flag and full chat immediately.",
    inputSchema: z.object({
      reason: z
        .string()
        .describe(
          "One line for the team: what the customer wants and where it got stuck, e.g. 'wants a glass-look trophy — kept refusing, needs custom quote'.",
        ),
      whatsapp: z
        .string()
        .optional()
        .describe("Customer's WhatsApp number, if they gave one."),
    }),
    contextSchema: agentContextSchema,
    execute: async ({ reason, whatsapp }, { context }) => {
      if (!context.sessionId)
        return {
          error:
            "Could not flag this chat. Give the customer our WhatsApp number +91 78925 54719 and ask them to message us directly.",
        };
      try {
        await flagHandoff(
          context.sessionId,
          reason,
          whatsapp ?? context.customerWhatsapp,
        );
        // One-tap WhatsApp deep link, prefilled with the session URL so the
        // team opens the conversation with full context. Rendered by the
        // client as a tappable card alongside the agent's reply.
        const text =
          `Hi! I was designing in the Everything 3D studio and need some help. ` +
          `My chat: https://studio.everything3dindia.com/s/${context.sessionId}`;
        return {
          ok: true,
          whatsappUrl: `https://wa.me/${TEAM_WHATSAPP}?text=${encodeURIComponent(text)}`,
        };
      } catch (err) {
        log("error", "tool_failed", { tool: "handoffToHuman", err: errStr(err) });
        return {
          error:
            "Could not flag this chat. Give the customer our WhatsApp number +91 78925 54719 and ask them to message us directly.",
        };
      }
    },
  }),

  makePrintable: tool({
    description:
      "Turn a design the customer already has (for example, an image brainstormed in ChatGPT) into a 3D-printable version — removes the background and flattens it to solid colors. Do not use this for a raw photo of a person; generatePixarFigurine already produces both Pixar and realistic style choices from photos. Takes ~1 minute.",
    inputSchema: z.object({
      imageId: z
        .string()
        .describe("Workspace id of the image to make printable."),
    }),
    contextSchema: agentContextSchema,
    execute: async ({ imageId }, { context }) => {
      const capped = imageBudgetExceeded(context, "edit");
      if (capped) return capped;
      const url = resolveImage(context, imageId);
      if (!url) return { error: `No image with id ${imageId}.` };
      try {
        const imageUrl = await gptEdit(
          [await cleanUrlFor(url)],
          MAKE_PRINTABLE_PROMPT,
        );
        return { imageUrl, label: "print-ready design" };
      } catch (err) {
        return toolError("makePrintable", err);
      }
    },
  }),
};
