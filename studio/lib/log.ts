/**
 * Structured logging (issue #4): one JSON object per line so Vercel's log
 * search (and any future drain) can filter by event/level instead of grepping
 * prose. Use for anything we'd want to notice in production — tool failures,
 * stream errors, rate-limit trips — not for chatty debug output.
 */

type Level = "info" | "warn" | "error";

export function log(
  level: Level,
  event: string,
  fields: Record<string, unknown> = {},
): void {
  const line = JSON.stringify({
    level,
    event,
    ...fields,
    at: new Date().toISOString(),
  });
  if (level === "error") console.error(line);
  else console.log(line);
}

/** Error -> loggable string, keeping the message but not a stack novel. */
export function errStr(err: unknown): string {
  return err instanceof Error ? `${err.name}: ${err.message}` : String(err);
}
