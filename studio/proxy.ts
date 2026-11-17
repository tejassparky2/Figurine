import { NextResponse, type NextRequest } from "next/server";

// Keep in sync with lib/owner.ts (not imported: proxy runs on the edge and
// shouldn't pull in server-only modules).
const OWNER_COOKIE = "e3d_owner";

/**
 * Anonymous device identity (issue #18). Every browser gets a random owner id
 * on first visit; sessions are stamped with it on write and /chats + /images
 * only show that owner's data. No login involved — the id is the identity.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has(OWNER_COOKIE)) return NextResponse.next();

  const id = crypto.randomUUID();
  // Mutate the request too, so this very first render already sees the id
  // via cookies() instead of only after the next navigation.
  request.cookies.set(OWNER_COOKIE, id);
  const response = NextResponse.next({ request });
  response.cookies.set(OWNER_COOKIE, id, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
  return response;
}

export const config = {
  // Everything except static assets — API routes included, so a cookie exists
  // even if the first hit is a direct fetch.
  matcher: ["/((?!_next/static|_next/image|.*\\.(?:ico|png|svg|jpg|webp)).*)"],
};
