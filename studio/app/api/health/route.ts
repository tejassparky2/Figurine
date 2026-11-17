import { dbAvailable } from "@/lib/db";
import { redisOk } from "@/lib/ratelimit";

/**
 * Readiness probe + deployment diagnostics (issue #4). Returns 503 when
 * anything a customer session depends on is missing or failing, so a plain
 * uptime monitor (UptimeRobot & co. hitting /api/health) doubles as the
 * alerting channel — including the "keys ran dry mid-session" case, as far
 * as key PRESENCE can catch it.
 */
export async function GET() {
  let dbOkFlag = false;
  let dbError: string | undefined;
  let sessions: number | undefined;
  if (dbAvailable) {
    try {
      const { neon } = await import("@neondatabase/serverless");
      const rows =
        await neon(process.env.DATABASE_URL!)`select count(*)::int as c from sessions`;
      dbOkFlag = true;
      sessions = rows[0].c;
    } catch (err) {
      dbError = err instanceof Error ? err.message : String(err);
    }
  }

  const checks = {
    db: dbOkFlag,
    redis: await redisOk(),
    aiGatewayKey: Boolean(process.env.AI_GATEWAY_API_KEY),
    falKey: Boolean(process.env.FAL_KEY),
    adminToken: Boolean(process.env.ADMIN_TOKEN),
    shopifyToken: Boolean(process.env.SHOPIFY_STOREFRONT_TOKEN),
  };
  const ok = Object.values(checks).every(Boolean);

  return Response.json(
    {
      ok,
      sha: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "local",
      ...checks,
      ...(sessions !== undefined ? { sessions } : {}),
      ...(dbError ? { dbError } : {}),
    },
    { status: ok ? 200 : 503 },
  );
}
