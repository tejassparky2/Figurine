"use client";

import { Bell, BellRing } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const REFRESH_MS = 30_000;

export function AdminLive({
  pendingLeadKeys,
}: {
  pendingLeadKeys: string[];
}) {
  const router = useRouter();
  const previousIds = useRef<Set<string> | null>(null);
  const [permission, setPermission] = useState<
    NotificationPermission | "loading" | "unsupported"
  >("loading");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPermission(
        "Notification" in window ? Notification.permission : "unsupported",
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => router.refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [router]);

  useEffect(() => {
    const nextIds = new Set(pendingLeadKeys);
    const previous = previousIds.current;

    if (previous && permission === "granted") {
      const newCount = pendingLeadKeys.filter(
        (id) => !previous.has(id),
      ).length;
      if (newCount > 0) {
        new Notification(
          newCount === 1
            ? "Studio follow-up needed"
            : `${newCount} studio follow-ups need attention`,
          {
            body: "Open the follow-up queue to see who needs a message.",
            icon: "/icon.png",
          },
        );
      }
    }

    previousIds.current = nextIds;
  }, [pendingLeadKeys, permission]);

  async function enableAlerts() {
    if (!("Notification" in window)) return;
    setPermission(await Notification.requestPermission());
  }

  if (
    permission === "loading" ||
    permission === "unsupported" ||
    permission === "denied"
  ) {
    return (
      <span className="text-xs text-slate-500">Updates every 30 seconds</span>
    );
  }

  if (permission === "granted") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700">
        <BellRing className="size-3.5" />
        Browser alerts on
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={enableAlerts}
      className="inline-flex h-8 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2"
    >
      <Bell className="size-3.5" />
      Enable browser alerts
    </button>
  );
}
