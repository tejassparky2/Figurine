import {
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleDot,
  Clock3,
  MessageCircle,
  RotateCcw,
  ShoppingBag,
  Sparkles,
  UserRoundCheck,
} from "lucide-react";
import Link from "next/link";
import { revalidatePath } from "next/cache";
import { notFound } from "next/navigation";
import {
  dbAvailable,
  listLeads,
  listSessions,
  setLeadFollowedUp,
  type LeadOrder,
} from "@/lib/db";
import { EMPTY_IMAGE_OPS, formatUsd, imageCostUsd } from "@/lib/cost";
import { relativeTime, sessionTitle } from "@/lib/session-list";
import { AdminLive } from "./admin-live";

export const dynamic = "force-dynamic";

const IST = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  year: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const fmtIst = (date: Date) => IST.format(date);

type LeadRow = Awaited<ReturnType<typeof listLeads>>[number];

type Order = Omit<LeadOrder, "createdAt"> & { createdAt: Date };

/**
 * A queue row. Filing an order is a stage, not a sale — nobody has paid at
 * that point — so an ordering session is just a lead whose latest order is
 * attached, and the queue is the only place leads live.
 */
type Lead = Omit<LeadRow, "latestOrder"> & {
  order: Order | null;
  /** Session contact, falling back to the number the order was filed with. */
  whatsapp: string;
  /** Newest of message activity, handoff, and order — drives the queue. */
  activityAt: Date;
};

function toLead(row: LeadRow): Lead {
  const { latestOrder, ...rest } = row;
  const order = latestOrder
    ? { ...latestOrder, createdAt: new Date(latestOrder.createdAt) }
    : null;
  let activityAt = row.updatedAt;
  if (row.handoffAt && row.handoffAt > activityAt) activityAt = row.handoffAt;
  if (order && order.createdAt > activityAt) activityAt = order.createdAt;
  return {
    ...rest,
    order,
    whatsapp: row.customerWhatsapp ?? order?.whatsapp ?? "",
    activityAt,
  };
}

function handoffNeedsFollowUp(lead: {
  handoffAt: Date | null;
  followedUpAt: Date | null;
}) {
  return Boolean(
    lead.handoffAt &&
      (!lead.followedUpAt || lead.handoffAt > lead.followedUpAt),
  );
}

function whatsappHref(number: string, sessionId: string, hasOrder: boolean) {
  const digits = number.replace(/\D/g, "");
  const destination = digits.length === 10 ? `91${digits}` : digits;
  const message = hasOrder
    ? `Hi! You picked out your figurine with Everything 3D India — I can help you finish the order and payment: https://studio.everything3dindia.com/s/${sessionId}`
    : `Hi! You started a design with Everything 3D India. I can help you finish it: https://studio.everything3dindia.com/s/${sessionId}`;
  return `https://wa.me/${destination}?text=${encodeURIComponent(message)}`;
}

/** Everything after the product name, which is capitalised on its own. */
function orderSummary(order: Order) {
  const parts = [
    order.size,
    order.priceInr
      ? `₹${order.priceInr.toLocaleString("en-IN")}`
      : "price on quote",
  ];
  if (order.baseText) parts.push(`base “${order.baseText}”`);
  return parts.join(" · ");
}

function LeadCard({
  lead,
  action,
}: {
  lead: Lead;
  action: () => Promise<void>;
}) {
  const { activityAt, order } = lead;
  const hasOrder = Boolean(order);
  const isExplicitHandoff = handoffNeedsFollowUp(lead);
  const isReturning = Boolean(
    lead.followedUpAt && activityAt > lead.followedUpAt,
  );
  const title = lead.title ?? sessionTitle(lead.firstMessage);

  return (
    <article className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_8px_30px_rgba(15,23,42,0.04)]">
      <div
        className={`absolute inset-y-0 left-0 w-1 ${
          hasOrder
            ? "bg-violet-500"
            : isExplicitHandoff
              ? "bg-amber-500"
              : "bg-emerald-500"
        }`}
      />
      <div className="p-4 pl-5 sm:p-5 sm:pl-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {hasOrder && (
                <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700">
                  <ShoppingBag className="size-3" /> Reached order stage ·
                  unpaid
                </span>
              )}
              {isExplicitHandoff && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">
                  <Sparkles className="size-3" /> Needs a human
                </span>
              )}
              {!hasOrder && !isExplicitHandoff && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                  <CircleDot className="size-3" />
                  {isReturning ? "Active again" : "New lead"}
                </span>
              )}
              <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                <Clock3 className="size-3" /> {relativeTime(activityAt)}
              </span>
            </div>
            <Link
              href={`/s/${lead.id}`}
              className="group inline-flex max-w-full items-center gap-1.5 text-base font-semibold text-slate-950 hover:text-emerald-700"
            >
              <span className="truncate">{title}</span>
              <ArrowUpRight className="size-4 shrink-0 opacity-50 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </Link>
            {isExplicitHandoff && lead.handoffReason ? (
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                {lead.handoffReason}
              </p>
            ) : (
              <p className="mt-1 text-sm text-slate-500">
                {lead.messageCount}{" "}
                {lead.messageCount === 1 ? "message" : "messages"} in this
                design
              </p>
            )}
            {order && (
              <div className="mt-3 rounded-xl bg-violet-50/70 px-3 py-2.5 text-sm text-violet-950">
                <p className="font-medium">
                  <span className="capitalize">{order.product}</span> ·{" "}
                  {orderSummary(order)}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-violet-800/80">
                  <span>
                    Filed {relativeTime(order.createdAt)} ·{" "}
                    {fmtIst(order.createdAt)} IST
                  </span>
                  <a
                    className="font-medium underline underline-offset-2 hover:text-violet-950"
                    href={order.imageUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Design
                  </a>
                  {order.checkoutUrl && (
                    <a
                      className="font-medium underline underline-offset-2 hover:text-violet-950"
                      href={order.checkoutUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Checkout link
                    </a>
                  )}
                  {lead.orderCount > 1 && (
                    <span>
                      +{lead.orderCount - 1} earlier{" "}
                      {lead.orderCount === 2 ? "attempt" : "attempts"}
                    </span>
                  )}
                </p>
              </div>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <a
              href={whatsappHref(lead.whatsapp, lead.id, hasOrder)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-[#128C7E] px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#0f7c70] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#128C7E] focus-visible:ring-offset-2"
            >
              <MessageCircle className="size-4" />
              Open WhatsApp
            </a>
            <form action={action}>
              <button
                type="submit"
                className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition-colors hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2"
              >
                <Check className="size-4" />
                Mark followed up
              </button>
            </form>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 pt-3 font-mono text-xs text-slate-500">
          <a
            href={whatsappHref(lead.whatsapp, lead.id, hasOrder)}
            target="_blank"
            rel="noopener noreferrer"
            className="font-sans font-medium text-slate-700 hover:text-emerald-700"
          >
            +{lead.whatsapp.replace(/\D/g, "")}
          </a>
          <span>Last active {fmtIst(activityAt)} IST</span>
        </div>
      </div>
    </article>
  );
}

function SectionDisclosure({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <details className="group rounded-2xl border border-slate-200 bg-white">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-sm font-semibold text-slate-800 marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2 [&::-webkit-details-marker]:hidden">
        <span>
          {title}{" "}
          <span className="ml-1 font-normal text-slate-400">{count}</span>
        </span>
        <ChevronDown className="size-4 text-slate-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-slate-100 p-3 sm:p-5">{children}</div>
    </details>
  );
}

export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  const expected = process.env.ADMIN_TOKEN;
  if (!expected || token !== expected) notFound();

  async function updateFollowUp(sessionId: string, followedUp: boolean) {
    "use server";
    if (!expected || token !== expected) throw new Error("Unauthorized");
    await setLeadFollowedUp(sessionId, followedUp);
    revalidatePath("/admin");
  }

  const [sessions, leadRows] = dbAvailable
    ? await Promise.all([listSessions(200), listLeads()])
    : [[], []];
  const leads = leadRows.map(toLead);
  const priority = (lead: Lead) =>
    lead.order ? 2 : handoffNeedsFollowUp(lead) ? 1 : 0;
  const pendingLeads = leads
    .filter(
      (lead) => !lead.followedUpAt || lead.activityAt > lead.followedUpAt,
    )
    .sort(
      (a, b) =>
        priority(b) - priority(a) ||
        b.activityAt.getTime() - a.activityAt.getTime(),
    );
  const pendingLeadIds = new Set(pendingLeads.map((lead) => lead.id));
  const completedLeads = leads
    .filter((lead) => !pendingLeadIds.has(lead.id))
    .sort((a, b) => b.followedUpAt!.getTime() - a.followedUpAt!.getTime());
  const orderStageCount = pendingLeads.filter((lead) => lead.order).length;

  return (
    <main className="min-h-screen bg-[#F6F8FA] text-slate-950">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10 lg:px-8">
        <header className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
              Everything 3D · Studio desk
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.035em] text-slate-950 sm:text-4xl">
              Follow-up queue
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">
              Everyone we can contact, in one queue — including the people who
              reached the order screen, since nobody has paid until we close
              them on WhatsApp. Check them off; if someone returns later, they
              automatically come back here.
            </p>
          </div>
          <AdminLive
            pendingLeadKeys={pendingLeads.map((lead) => {
              const handoffKey = handoffNeedsFollowUp(lead)
                ? `:handoff:${lead.handoffAt!.getTime()}`
                : "";
              return lead.order
                ? `${lead.id}:order:${lead.order.id}${handoffKey}`
                : `${lead.id}:lead${handoffKey}`;
            })}
          />
        </header>

        <section
          className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          aria-label="Queue summary"
        >
          <div className="rounded-2xl bg-slate-950 p-5 text-white shadow-sm">
            <p className="text-sm text-slate-300">To follow up</p>
            <p className="mt-3 text-4xl font-semibold tracking-tight">
              {pendingLeads.length}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="text-sm text-slate-500">Reached order stage</p>
            <p className="mt-3 text-2xl font-semibold text-violet-700">
              {orderStageCount}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="text-sm text-slate-500">Needs a human</p>
            <p className="mt-3 text-2xl font-semibold text-amber-700">
              {
                pendingLeads.filter((lead) => handoffNeedsFollowUp(lead)).length
              }
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="text-sm text-slate-500">Followed up</p>
            <p className="mt-3 text-2xl font-semibold text-slate-800">
              {completedLeads.length}
            </p>
          </div>
        </section>

        <section aria-labelledby="queue-heading">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2
              id="queue-heading"
              className="text-base font-semibold text-slate-900"
            >
              Next to contact
            </h2>
            <span className="text-right text-xs text-slate-500">
              Order stage and human requests first
            </span>
          </div>

          {pendingLeads.length > 0 ? (
            <div className="space-y-3">
              {pendingLeads.map((lead) => (
                <LeadCard
                  key={lead.id}
                  lead={lead}
                  action={updateFollowUp.bind(null, lead.id, true)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/60 px-6 py-12 text-center">
              <UserRoundCheck className="mx-auto size-7 text-emerald-700" />
              <h3 className="mt-3 font-semibold text-emerald-950">
                Everyone has been followed up with
              </h3>
              <p className="mt-1 text-sm text-emerald-800/70">
                New and returning leads will appear here automatically.
              </p>
            </div>
          )}
        </section>

        <div className="mt-8 space-y-3">
          <SectionDisclosure
            title="Followed-up leads"
            count={completedLeads.length}
          >
            {completedLeads.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {completedLeads.map((lead) => (
                  <div
                    key={lead.id}
                    className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <Link
                        href={`/s/${lead.id}`}
                        className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-emerald-700"
                      >
                        <span className="truncate">
                          {lead.title ?? sessionTitle(lead.firstMessage)}
                        </span>
                        {lead.order && (
                          <ShoppingBag
                            className="size-3.5 shrink-0 text-violet-500"
                            aria-label="Reached order stage"
                          />
                        )}
                      </Link>
                      <p className="mt-1 text-xs text-slate-500">
                        {lead.followedUpAt
                          ? `Followed up ${relativeTime(lead.followedUpAt)}`
                          : "Followed up"}{" "}
                        · +{lead.whatsapp.replace(/\D/g, "")}
                      </p>
                    </div>
                    <form
                      action={updateFollowUp.bind(null, lead.id, false)}
                    >
                      <button
                        type="submit"
                        className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
                      >
                        <RotateCcw className="size-3.5" /> Move back to queue
                      </button>
                    </form>
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-3 text-sm text-slate-500">
                Checked-off leads will collect here.
              </p>
            )}
          </SectionDisclosure>

          <SectionDisclosure title="Recent sessions" count={sessions.length}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr className="border-b border-slate-100">
                    <th className="pb-3 font-medium">Session</th>
                    <th className="pb-3 font-medium">Messages</th>
                    <th className="pb-3 font-medium">Contact</th>
                    <th className="pb-3 font-medium">Cost</th>
                    <th className="pb-3 font-medium">Last activity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sessions.map((session) => {
                    const ops = session.imageOps ?? EMPTY_IMAGE_OPS;
                    const fal = imageCostUsd(ops);
                    const total = session.costUsd + fal;
                    const breakdown = `LLM ${formatUsd(session.costUsd)} (${session.inputTokens} in / ${session.outputTokens} out) · images ~${formatUsd(fal)} (${ops.figurine} figurine, ${ops.gptEdit} transform/print, ${ops.nanoEdit} edit)`;
                    return (
                      <tr key={session.id}>
                        <td className="py-3 pr-5">
                          <Link
                            className="font-medium text-slate-800 hover:text-emerald-700 hover:underline"
                            href={`/s/${session.id}`}
                          >
                            {session.title ?? sessionTitle(session.firstMessage)}
                          </Link>
                        </td>
                        <td className="py-3 pr-5 text-slate-500">
                          {session.messageCount}
                        </td>
                        <td className="py-3 pr-5 text-slate-500">
                          {session.customerWhatsapp
                            ? `+${session.customerWhatsapp.replace(/\D/g, "")}`
                            : "—"}
                        </td>
                        <td
                          className="py-3 pr-5 text-slate-500"
                          title={breakdown}
                        >
                          {total > 0 ? `~${formatUsd(total)}` : "—"}
                        </td>
                        <td className="py-3 text-slate-500">
                          {fmtIst(session.updatedAt)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {sessions.length === 0 && (
                <p className="py-3 text-sm text-slate-500">
                  {dbAvailable
                    ? "No sessions yet."
                    : "No DATABASE_URL configured."}
                </p>
              )}
              <p className="mt-4 text-xs leading-5 text-slate-400">
                Cost combines recorded LLM spend with estimated image spend.
                Hover a cost for the breakdown.
              </p>
            </div>
          </SectionDisclosure>
        </div>

        <footer className="mt-6 flex items-center gap-2 text-xs text-slate-400">
          <span className="size-1.5 rounded-full bg-emerald-500" />
          Auto-refreshes while this page is open
        </footer>
      </div>
    </main>
  );
}
