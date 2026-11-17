import { saveSessionContact } from "@/lib/db";
import { getOwnerId } from "@/lib/owner";
import { clientIp, rateLimit } from "@/lib/ratelimit";
import { errStr, log } from "@/lib/log";

const UUID = /^[0-9a-f]{8}-[0-9a-f-]{27}$/i;

/** Capture a lead before their first paid image upload. */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!UUID.test(id)) {
    return Response.json({ error: "Invalid session" }, { status: 400 });
  }

  const limited = await rateLimit(`contact:${clientIp(req)}`, 20, 10 * 60);
  if (!limited.ok) {
    return Response.json(
      { error: "Too many attempts — please wait a few minutes." },
      { status: 429 },
    );
  }

  const body = (await req.json()) as { whatsapp?: unknown };
  const digits =
    typeof body.whatsapp === "string"
      ? body.whatsapp.replace(/\D/g, "")
      : "";
  if (digits.length < 10 || digits.length > 14) {
    return Response.json(
      { error: "Enter a valid 10-digit WhatsApp number." },
      { status: 400 },
    );
  }

  try {
    const ownerId = await getOwnerId();
    if (!ownerId) {
      return Response.json({ error: "Session identity missing" }, { status: 403 });
    }
    const persisted = await saveSessionContact(id, ownerId, digits);
    if (!persisted && process.env.NODE_ENV === "production") {
      return Response.json(
        { error: "Could not save your number right now. Please try again." },
        { status: 503 },
      );
    }
    return Response.json({ whatsapp: digits });
  } catch (err) {
    log("warn", "contact_save_failed", { id, err: errStr(err) });
    return Response.json(
      { error: "Could not save your number right now. Please try again." },
      { status: 403 },
    );
  }
}
