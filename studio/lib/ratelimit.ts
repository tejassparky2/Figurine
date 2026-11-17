import { createClient } from "redis";

/**
 * Fixed-window per-IP rate limiting on the paid entry points (issue #5),
 * backed by the same Redis that resumable-stream uses. Without REDIS_URL it
 * fails open — matching the app's "everything optional in local dev" rule —
 * and any Redis error also fails open: a broken limiter must never take the
 * studio down with it.
 */

async function connectRedis() {
  const url = process.env.REDIS_URL ?? process.env.KV_URL;
  if (!url) return null;
  try {
    const client = createClient({ url });
    client.on("error", (err) => console.error("ratelimit redis error", err));
    return await client.connect();
  } catch (err) {
    console.error("ratelimit redis connect failed", err);
    return null;
  }
}

let clientPromise: ReturnType<typeof connectRedis> | undefined;

function getRedis(): ReturnType<typeof connectRedis> {
  if (clientPromise === undefined) clientPromise = connectRedis();
  return clientPromise;
}

/** True when Redis is configured and answers a ping — for /api/health. */
export async function redisOk(): Promise<boolean> {
  try {
    const redis = await getRedis();
    if (!redis) return false;
    return (await redis.ping()) === "PONG";
  } catch {
    return false;
  }
}

/**
 * Count a hit for `key` in the current window; ok=false once `limit` is
 * exceeded. Windows are aligned (not sliding) — simple and good enough to
 * stop a script from draining the image-generation keys.
 */
export async function rateLimit(
  key: string,
  limit: number,
  windowSeconds: number,
): Promise<{ ok: boolean }> {
  try {
    const redis = await getRedis();
    if (!redis) return { ok: true };
    const window = Math.floor(Date.now() / 1000 / windowSeconds);
    const k = `rl:${key}:${window}`;
    const n = await redis.incr(k);
    if (n === 1) await redis.expire(k, windowSeconds);
    return { ok: n <= limit };
  } catch (err) {
    console.error("ratelimit check failed", err);
    return { ok: true };
  }
}

/**
 * Caller's IP as Vercel reports it. Indian mobile carriers CGNAT aggressively,
 * so many real customers can share one IP — limits keyed on this must stay
 * generous enough for a handful of simultaneous humans.
 */
export function clientIp(req: Request): string {
  return (
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    req.headers.get("x-real-ip") ??
    "unknown"
  );
}
