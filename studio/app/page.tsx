import { redirect } from "next/navigation";

// Every visit starts a fresh design session at a stable URL, so the
// conversation survives refreshes and can be shared/resumed.
export const dynamic = "force-dynamic";

export default function Home() {
  redirect(`/s/${crypto.randomUUID()}`);
}
