import { fal } from "@fal-ai/client";
import { clientIp, rateLimit } from "@/lib/ratelimit";
import { errStr, log } from "@/lib/log";
import { checkBotId } from "botid/server";

if (process.env.FAL_KEY) {
  fal.config({ credentials: process.env.FAL_KEY });
}

export const maxDuration = 60;

/**
 * Accepts a single uploaded photo (multipart form, field "file"), stores it in
 * fal storage, and returns its URL. The URL is then passed to the chat so the
 * render pipeline can use it. No DB / Blob yet — that comes with auth in a
 * later phase (see plan §13).
 */
export async function POST(req: Request) {
  if (!process.env.FAL_KEY) {
    return Response.json({ error: "FAL_KEY not configured" }, { status: 500 });
  }

  // Bots never reach the paid APIs (issue #5). Always false in local dev.
  const { isBot } = await checkBotId();
  if (isBot) {
    log("warn", "bot_blocked", { route: "upload", ip: clientIp(req) });
    return Response.json({ error: "Access denied" }, { status: 403 });
  }

  // Spend protection (issue #5): uploads land in fal storage, and each one
  // usually kicks off a paid render right after.
  const limited = await rateLimit(`upload:${clientIp(req)}`, 20, 10 * 60);
  if (!limited.ok) {
    log("warn", "rate_limited", { route: "upload", ip: clientIp(req) });
    return Response.json(
      { error: "Too many uploads — please wait a few minutes and try again." },
      { status: 429, headers: { "Retry-After": "600" } },
    );
  }

  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return Response.json({ error: "No file provided" }, { status: 400 });
  }

  // The chat model's vision API rejects images over 5 MB. The client
  // downscales before uploading; this cap catches anything that slips
  // through (e.g. formats the browser couldn't re-encode).
  if (file.size > 4.5 * 1024 * 1024) {
    return Response.json(
      {
        error:
          "That image is too large. Please use a JPEG or PNG under ~4 MB (a normal photo works fine).",
      },
      { status: 413 },
    );
  }

  try {
    const url = await fal.storage.upload(file);
    return Response.json({ url });
  } catch (err) {
    log("error", "upload_failed", { err: errStr(err) });
    return Response.json(
      { error: err instanceof Error ? err.message : "upload failed" },
      { status: 500 },
    );
  }
}
