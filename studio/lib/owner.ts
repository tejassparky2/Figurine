import { cookies } from "next/headers";

// Keep in sync with proxy.ts, which mints the cookie.
export const OWNER_COOKIE = "e3d_owner";

/**
 * The caller's anonymous owner id (random UUID set by proxy.ts on first
 * visit). Null only when the proxy didn't run — e.g. a non-browser client
 * hitting an API directly — in which case owner-scoped queries return nothing.
 */
export async function getOwnerId(): Promise<string | null> {
  return (await cookies()).get(OWNER_COOKIE)?.value ?? null;
}
