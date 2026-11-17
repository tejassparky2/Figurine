"use client";

import { useChat } from "@ai-sdk/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ChatStatus, FileUIPart, UIMessage } from "ai";
import Image from "next/image";
import Link from "next/link";
import {
  ExternalLink,
  ImageIcon,
  Images,
  PanelLeft,
  Plus,
  X,
} from "lucide-react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputButton,
  PromptInputSubmit,
  usePromptInputAttachments,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import {
  Attachments,
  Attachment,
  AttachmentPreview,
  AttachmentRemove,
} from "@/components/ai-elements/attachments";
import {
  ImageCard,
  ImageOptionCards,
  OrderCard,
  OrderConfirmedCard,
  HandoffCard,
  UploadedThumb,
} from "@/components/image-card";
import { WelcomeScreen } from "@/components/welcome";
import { ContactCaptureDialog } from "@/components/contact-capture-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { deriveWorkspace } from "@/lib/workspace";
import { deriveSpec, type OrderSpec } from "@/lib/spec";
import { downscaleImage } from "@/lib/downscale";
import type { SessionListItem } from "@/lib/session-list";

// tool part type -> loading caption
const LOADING_LABEL: Record<string, string> = {
  "tool-generatePixarFigurine": "Generating two styles… ~1–2 minutes",
  "tool-editImage": "Applying your edit…",
  "tool-transformImage": "Reworking the image… ~1 minute",
  "tool-makePrintable": "Making it print-ready… ~1 minute",
};
const IMAGE_TOOLS = Object.keys(LOADING_LABEL);

// ---------------------------------------------------------------------------
// Connection recovery — the mobile "Load failed" fix.
//
// Mobile browsers kill the in-flight fetch the moment the tab is backgrounded,
// and a 1–2 minute generation practically guarantees the customer switches
// apps while waiting. The server keeps generating regardless and tees the
// stream into Redis (see /api/chat), so the client's job is to notice the
// dead connection and quietly reattach:
//
//   1. network-type error surfaces        -> resumeStream() replays the live
//      stream via GET /api/chat/[id]/stream
//   2. socket silently dead (no heartbeat
//      for 30s while "streaming")         -> resumeStream()
//   3. generation finished while away
//      (live stream no longer replayable) -> pull the persisted turn from
//      GET /api/chat/[id]/messages and swap it in
//
// A page reload mid-generation is covered separately by useChat's `resume`.
// ---------------------------------------------------------------------------

/** Errors that mean "the connection died", not "the server said no". */
const isNetworkError = (err?: Error) =>
  Boolean(
    err &&
      /load failed|failed to fetch|network|connection|socket/i.test(
        err.message,
      ),
  );

/**
 * True when the last turn never completed: a server tool is still waiting for
 * its output, or a user message got no reply. askUser doesn't count — it
 * legitimately waits for the customer.
 */
const hasDanglingWork = (msgs: UIMessage[]) => {
  const last = msgs[msgs.length - 1];
  if (!last) return false;
  if (last.role === "user") return true;
  if (last.role !== "assistant") return false;
  return last.parts.some((part) => {
    if (!part.type.startsWith("tool-") || part.type === "tool-askUser")
      return false;
    const state = (part as { state?: string }).state;
    return state === "input-streaming" || state === "input-available";
  });
};

/** No chunk for this long while "streaming" = the socket is dead (the server
 *  heartbeats every 10s precisely so silence is meaningful). */
const STALE_CONNECTION_MS = 30_000;

function useStreamRecovery({
  chatId,
  status,
  error,
  messages,
  lastChunkAt,
  resumeStream,
  setMessages,
  clearError,
  onRecovered,
}: {
  chatId: string;
  status: ChatStatus;
  error: Error | undefined;
  messages: UIMessage[];
  lastChunkAt: React.RefObject<number>;
  resumeStream: () => void;
  setMessages: (messages: UIMessage[]) => void;
  clearError: () => void;
  onRecovered: () => void;
}) {
  const busy = status === "submitted" || status === "streaming";

  // The watchdog is installed once and reads current state through refs.
  const stateRef = useRef({ status, error, messages, busy });
  stateRef.current = { status, error, messages, busy };
  const fnRef = useRef({ resumeStream, setMessages, clearError, onRecovered });
  fnRef.current = { resumeStream, setMessages, clearError, onRecovered };

  // Streamed message updates mark the connection live (heartbeats between
  // them are caught by onData in the useChat options).
  useEffect(() => {
    if (busy) lastChunkAt.current = Date.now();
  }, [busy, messages, lastChunkAt]);

  const lastResumeAtRef = useRef(0);
  const tryResume = useCallback(() => {
    if (Date.now() - lastResumeAtRef.current < 5_000) return;
    lastResumeAtRef.current = Date.now();
    // Fresh grace period so the zombie check doesn't instantly re-fire.
    lastChunkAt.current = Date.now();
    fnRef.current.resumeStream();
  }, [lastChunkAt]);

  // Generation finished while we were away: the live stream is gone but the
  // completed turn is in Postgres. Swap it in — but never drop local-only
  // content, and never fight an active stream.
  const reconcilingRef = useRef(false);
  const reconcileFromDb = useCallback(async () => {
    if (reconcilingRef.current) return;
    reconcilingRef.current = true;
    try {
      const res = await fetch(`/api/chat/${chatId}/messages`);
      if (!res.ok) return;
      const { messages: db } = (await res.json()) as { messages: UIMessage[] };
      const { messages: local, busy: busyNow } = stateRef.current;
      if (busyNow) return; // a resumed stream took over meanwhile
      if (!db?.length || db.length < local.length) return;
      if (hasDanglingWork(db)) return; // server turn not finished yet
      fnRef.current.setMessages(db);
      fnRef.current.clearError();
      fnRef.current.onRecovered();
    } catch {
      // offline etc. — the next tick retries
    } finally {
      reconcilingRef.current = false;
    }
  }, [chatId]);

  // React quickly when a network error surfaces while the tab is visible
  // (desktop blips); the watchdog below covers everything else.
  useEffect(() => {
    if (status !== "error" || !isNetworkError(error)) return;
    if (document.visibilityState !== "visible") return;
    const t = setTimeout(tryResume, 400);
    return () => clearTimeout(t);
  }, [status, error, tryResume]);

  // Watchdog: on returning to the tab (the moment that matters on mobile)
  // and every 5s while visible.
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      const { status, error, messages, busy } = stateRef.current;
      if (busy) {
        if (Date.now() - lastChunkAt.current > STALE_CONNECTION_MS)
          tryResume();
        return;
      }
      if (status === "error" && isNetworkError(error)) tryResume();
      if (hasDanglingWork(messages)) void reconcileFromDb();
    };
    const iv = setInterval(tick, 5_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(iv);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [tryResume, reconcileFromDb, lastChunkAt]);
}

export function Chat({
  id,
  initialMessages,
  sessions = [],
  initialWhatsapp,
}: {
  id: string;
  initialMessages: UIMessage[];
  sessions?: SessionListItem[];
  initialWhatsapp?: string;
}) {
  const [text, setText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [customerWhatsapp, setCustomerWhatsapp] = useState(
    initialWhatsapp ?? "",
  );
  const [contactDialogOpen, setContactDialogOpen] = useState(false);
  const router = useRouter();
  const pendingContactPromise = useRef<Promise<string> | null>(null);
  const resolveContact = useRef<((whatsapp: string) => void) | null>(null);

  const persistCustomerWhatsapp = useCallback(
    async (whatsapp: string) => {
      const res = await fetch(`/api/chat/${id}/contact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ whatsapp }),
      });
      const data = (await res.json()) as {
        whatsapp?: string;
        error?: string;
      };
      if (!res.ok || !data.whatsapp) {
        throw new Error(data.error ?? "Could not save number");
      }
      setCustomerWhatsapp(data.whatsapp);
      router.refresh();
      return data.whatsapp;
    },
    [id, router],
  );

  const ensureCustomerWhatsapp = useCallback(() => {
    if (customerWhatsapp) return Promise.resolve(customerWhatsapp);
    if (pendingContactPromise.current) return pendingContactPromise.current;
    setContactDialogOpen(true);
    const promise = new Promise<string>((resolve) => {
      resolveContact.current = resolve;
    });
    pendingContactPromise.current = promise;
    return promise;
  }, [customerWhatsapp]);

  const completeContactCapture = useCallback(
    async (whatsapp: string) => {
      const saved = await persistCustomerWhatsapp(whatsapp);
      setContactDialogOpen(false);
      resolveContact.current?.(saved);
      resolveContact.current = null;
      pendingContactPromise.current = null;
    },
    [persistCustomerWhatsapp],
  );

  // Timestamp of the last streamed byte — heartbeats included — used by the
  // recovery watchdog to tell a live connection from a dead one.
  const lastChunkAt = useRef(Date.now());

  // The chat id doubles as the session id: the transport posts it to
  // /api/chat, which persists the turn's messages under it (see lib/db).
  const {
    messages,
    sendMessage,
    addToolOutput,
    status,
    error,
    resumeStream,
    setMessages,
    clearError,
  } = useChat({
    id,
    messages: initialMessages,
    // Reattach to an in-flight generation on page load (mobile browsers
    // reload backgrounded tabs); GET /api/chat/[id]/stream 204s when idle.
    resume: initialMessages.length > 0,
    // Heartbeat data parts are transient (never enter message history) but
    // they do reach onData — exactly what liveness tracking needs.
    onData: () => {
      lastChunkAt.current = Date.now();
    },
    // Refresh server data after each turn so the sidebar picks up this
    // session (and its generated title) without a manual reload.
    onFinish: () => router.refresh(),
  });

  useStreamRecovery({
    chatId: id,
    status,
    error,
    messages,
    lastChunkAt,
    resumeStream,
    setMessages,
    clearError,
    onRecovered: () => router.refresh(),
  });

  // Order-summary spec, derived from the agent's tool outputs (the server
  // derives the same thing from message history — nothing extra in the body).
  const spec = useMemo(() => deriveSpec(messages), [messages]);

  const workspace = useMemo(() => deriveWorkspace(messages), [messages]);

  const busy = status === "submitted" || status === "streaming";

  // A synchronous lock around every send path. Taps (especially on mobile)
  // can fire faster than React updates `status`, so `busy` alone lets a button
  // be pressed several times before it flips — each press sending a duplicate
  // message and corrupting the tool-call/tool-result pairing ("tool result is
  // missing" errors). This ref rejects re-entrant sends immediately.
  const sendingRef = useRef(false);

  const runSend = async (fn: () => Promise<void> | void) => {
    if (sendingRef.current || busy) return;
    sendingRef.current = true;
    try {
      await fn();
    } finally {
      sendingRef.current = false;
    }
  };

  // askUser is a client-side tool (no server execute): the agent stops and
  // waits for its output. A tap fills the output with the chosen option; a
  // typed reply fills a placeholder so the tool call is never left dangling
  // (the model would reject the history otherwise).
  const answerQuestion = (toolCallId: string, option: string) =>
    runSend(async () => {
      await addToolOutput({ tool: "askUser", toolCallId, output: option });
      await sendMessage(undefined);
    });

  const resolvePendingQuestion = async () => {
    const last = messages[messages.length - 1];
    if (last?.role !== "assistant") return;
    for (const part of last.parts) {
      if (part.type === "tool-askUser") {
        const p = part as { toolCallId: string; state: string };
        if (p.state === "input-available") {
          await addToolOutput({
            tool: "askUser",
            toolCallId: p.toolCallId,
            output: "(the customer typed a reply instead — see their message)",
          });
        }
      }
    }
  };

  // Downscale one image and push it to fal storage, so message history
  // carries small, stable URLs (which also become the agent's image
  // workspace) instead of megabytes of base64. Downscaling matters: the chat
  // model rejects images > 5 MB, and nothing downstream needs more than ~2K px.
  const uploadImage = async (
    raw: Blob,
    filename: string,
  ): Promise<FileUIPart> => {
    const { blob, mediaType } = await downscaleImage(raw);
    const fd = new FormData();
    fd.append("file", new File([blob], filename, { type: mediaType }));
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!data.url) throw new Error(data.error ?? "Upload failed");
    return { type: "file", mediaType, url: data.url as string };
  };

  // Text + staged attachments are sent together as ONE message. Attachments
  // arrive from the composer as data URLs.
  const handleSubmit = async (message: PromptInputMessage) => {
    const value = message.text?.trim() ?? "";
    const attached = message.files.filter((f) =>
      f.mediaType?.startsWith("image/"),
    );
    // Throwing keeps the composer's text/attachments intact for a retry.
    if ((!value && attached.length === 0) || busy || sendingRef.current)
      throw new Error("not ready");

    sendingRef.current = true;
    setUploadError(null);
    try {
      if (attached.length > 0) {
        await ensureCustomerWhatsapp();
        setUploading(true);
      }
      const files: FileUIPart[] = await Promise.all(
        attached.map(async (f) => {
          const raw = await (await fetch(f.url)).blob();
          return uploadImage(raw, f.filename ?? "image.jpg");
        }),
      );
      await resolvePendingQuestion();
      if (value) {
        sendMessage({ text: value, ...(files.length ? { files } : {}) });
      } else {
        sendMessage({ files });
      }
      setText("");
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
      throw err; // keep composer contents for a retry
    } finally {
      setUploading(false);
      sendingRef.current = false;
    }
  };

  const quickSend = (value: string) =>
    runSend(async () => {
      await resolvePendingQuestion();
      sendMessage({ text: value });
    });

  // The welcome screen's "Upload a photo" CTA: upload and send in one step —
  // no composer round-trip, the agent takes it from there.
  const sendPhotos = (list: File[]) =>
    runSend(async () => {
      setUploadError(null);
      try {
        await ensureCustomerWhatsapp();
        setUploading(true);
        const files = await Promise.all(
          list.map((f) => uploadImage(f, f.name || "photo.jpg")),
        );
        sendMessage({ files });
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    });

  return (
    <div className="flex h-[100dvh] min-h-0 overflow-hidden">
      <ContactCaptureDialog
        open={contactDialogOpen}
        onSave={completeContactCapture}
      />
      {/* Chat history sidebar — static on desktop, slide-over on mobile. */}
      <aside className="hidden shrink-0 border-r bg-secondary/20 lg:block">
        <ChatSidebar sessions={sessions} activeId={id} />
      </aside>
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-72 border-r bg-background shadow-lg">
            <ChatSidebar
              sessions={sessions}
              activeId={id}
              onNavigate={() => setSidebarOpen(false)}
              onClose={() => setSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Chat column */}
      <div className="flex min-h-0 flex-1 flex-col min-w-0">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <button
              type="button"
              aria-label="Chat history"
              onClick={() => setSidebarOpen(true)}
              className="-ml-1 shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground lg:hidden"
            >
              <PanelLeft className="size-5" />
            </button>
            <Image
              src="/e3d-mark.png"
              alt=""
              width={28}
              height={28}
              priority
              className="size-7 shrink-0 rounded-md border bg-white object-contain p-0.5"
            />
            <h1 className="truncate text-sm font-semibold sm:text-base">
              Everything 3D India — Figurine Studio
            </h1>
          </div>
          <a
            href="https://everything3dindia.com"
            className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            Store
            <ExternalLink className="size-3.5" />
          </a>
        </header>

        {/* No initial scroll-to-bottom on an empty chat — the welcome screen
            should be seen from the top (hero first, CTA below). */}
        <Conversation
          className="min-h-0 flex-1"
          initial={messages.length === 0 ? false : "smooth"}
        >
          <ConversationContent className="mx-auto w-full max-w-2xl px-3 py-4 sm:p-4">
            {messages.length === 0 && (
              <WelcomeScreen
                onPhotos={sendPhotos}
                onStarter={quickSend}
                uploading={uploading}
                disabled={busy}
              />
            )}

            {messages.map((message, mi) => {
              // Action buttons (choose option, keep/revise) only apply to the
              // current step. Once the customer has moved on, the buttons in
              // older messages must be inert — otherwise tapping a stale card
              // sends a contradictory message into a finished part of the chat.
              const isLastMessage = mi === messages.length - 1;
              return (
              <Message from={message.role} key={message.id}>
                <MessageContent>
                  {message.parts.map((part, i) => {
                    const key = `${message.id}-${i}`;

                    if (part.type === "text") {
                      return (
                        <MessageResponse key={key}>{part.text}</MessageResponse>
                      );
                    }

                    // Uploaded photo shown back to the customer.
                    if (
                      part.type === "file" &&
                      part.mediaType?.startsWith("image/")
                    ) {
                      return <UploadedThumb key={key} url={part.url} />;
                    }

                    // Question with tappable quick-reply options.
                    if (part.type === "tool-askUser") {
                      const p = part as {
                        toolCallId: string;
                        state: string;
                        input?: { question?: string; options?: string[] };
                        output?: unknown;
                      };
                      if (
                        (p.state !== "input-available" &&
                          p.state !== "output-available") ||
                        !p.input?.question
                      ) {
                        return null;
                      }
                      return (
                        <QuickReplies
                          key={key}
                          question={p.input.question}
                          options={p.input.options ?? []}
                          chosen={
                            typeof p.output === "string" ? p.output : undefined
                          }
                          answered={p.state === "output-available"}
                          disabled={busy}
                          onChoose={(opt) => answerQuestion(p.toolCallId, opt)}
                        />
                      );
                    }

                    // Interactive order card: the customer picks a size and
                    // enters their WhatsApp number right in the card; the
                    // Place-order tap comes back as a structured message.
                    if (part.type === "tool-proposeOrder") {
                      const p = part as {
                        state: string;
                        output?: {
                          error?: string;
                          imageUrl?: string;
                          product?: string;
                          baseText?: string;
                          prices?: Record<string, number> | null;
                        };
                      };
                      if (p.state !== "output-available" || p.output?.error) {
                        return null; // errors are relayed by the agent in text
                      }
                      const product = p.output?.product ?? "custom";
                      return (
                        <OrderCard
                          key={key}
                          imageUrl={p.output?.imageUrl}
                          product={product}
                          initialBaseText={p.output?.baseText}
                          initialWhatsapp={customerWhatsapp}
                          prices={p.output?.prices}
                          disabled={busy || !isLastMessage}
                          onPlaceOrder={({ size, baseText, whatsapp }) =>
                            runSend(async () => {
                              await persistCustomerWhatsapp(whatsapp);
                              await resolvePendingQuestion();
                              sendMessage({
                                text: `Place my order: ${product} figurine, ${size}${
                                  baseText
                                    ? `, base text "${baseText}"`
                                    : ", no base text"
                                }, WhatsApp ${whatsapp}.`,
                              });
                            })
                          }
                        />
                      );
                    }

                    // Order confirmation card.
                    if (part.type === "tool-finalizeOrder") {
                      const p = part as {
                        state: string;
                        output?: {
                          ok?: boolean;
                          error?: string;
                          imageUrl?: string;
                          product?: string;
                          size?: string;
                          baseText?: string;
                          priceInr?: number | null;
                          whatsapp?: string;
                        };
                      };
                      if (p.state === "output-available" && p.output?.ok) {
                        return <OrderConfirmedCard key={key} {...p.output} />;
                      }
                      return null; // errors are relayed by the agent in text
                    }

                    // Human handoff: one-tap WhatsApp button.
                    if (part.type === "tool-handoffToHuman") {
                      const p = part as {
                        state: string;
                        output?: { ok?: boolean; whatsappUrl?: string };
                      };
                      if (
                        p.state === "output-available" &&
                        p.output?.ok &&
                        p.output.whatsappUrl
                      ) {
                        return (
                          <HandoffCard
                            key={key}
                            whatsappUrl={p.output.whatsappUrl}
                          />
                        );
                      }
                      return null; // errors are relayed by the agent in text
                    }

                    // Any of the image tools -> ImageCard / option cards.
                    if (IMAGE_TOOLS.includes(part.type)) {
                      const p = part as {
                        state: string;
                        output?: {
                          imageUrl?: string;
                          imageUrls?: string[];
                          optionLabels?: string[];
                          optionDescriptions?: string[];
                          recommendedIndex?: number;
                          error?: string;
                        };
                        errorText?: string;
                      };
                      if (
                        p.state === "input-streaming" ||
                        p.state === "input-available"
                      ) {
                        return (
                          <ImageCard
                            key={key}
                            loading
                            loadingLabel={LOADING_LABEL[part.type]}
                          />
                        );
                      }
                      if (p.state === "output-available") {
                        // Multi-image output (figurine options): pick one.
                        if (p.output?.imageUrls?.length) {
                          return (
                            <ImageOptionCards
                              key={key}
                              urls={p.output.imageUrls}
                              labels={p.output.optionLabels}
                              descriptions={p.output.optionDescriptions}
                              recommendedIndex={p.output.recommendedIndex}
                              disabled={busy || !isLastMessage}
                              onChoose={(idx) =>
                                quickSend(
                                  `I'll go with the ${p.output?.optionLabels?.[idx] ?? `option ${idx + 1}`} — let's continue with that one.`,
                                )
                              }
                            />
                          );
                        }
                        return (
                          <ImageCard
                            key={key}
                            url={p.output?.imageUrl}
                            error={p.output?.error}
                            disabled={busy || !isLastMessage}
                            onKeep={() =>
                              quickSend("I love this one — let's keep it!")
                            }
                            onRevise={() => quickSend("Can we tweak this?")}
                          />
                        );
                      }
                      if (p.state === "output-error") {
                        return <ImageCard key={key} error={p.errorText} />;
                      }
                    }

                    return null;
                  })}
                </MessageContent>
              </Message>
              );
            })}
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>

        {(error || uploadError) && (
          <div
            className={cn(
              "mx-auto mb-2 w-full max-w-2xl px-3 text-sm sm:px-6",
              !uploadError && isNetworkError(error)
                ? "text-muted-foreground"
                : "text-destructive",
            )}
          >
            {uploadError ??
              (isNetworkError(error)
                ? "Connection interrupted — reconnecting…"
                : `Chat request failed: ${error?.message}`)}
          </div>
        )}

        {/* Composer — attach via button, paste, or drag-drop; images are
            staged as previews and sent together with the text. */}
        <div className="mx-auto w-full max-w-2xl px-3 md:hidden">
          <MobileOrderSummary spec={spec} imageCount={workspace.length} />
        </div>
        <div className="mx-auto w-full max-w-2xl shrink-0 px-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] sm:px-6 sm:pb-6">
          <PromptInput
            onSubmit={handleSubmit}
            accept="image/*"
            multiple
            globalDrop
          >
            <PromptInputBody>
              <ComposerAttachments />
              <PromptInputTextarea
                value={text}
                onChange={(e) => setText(e.currentTarget.value)}
                className="max-h-32 min-h-14 sm:max-h-48 sm:min-h-16"
                placeholder="Type a message, paste or drop images…"
              />
            </PromptInputBody>
            <PromptInputFooter className="gap-2">
              <PromptInputTools className="flex-1">
                <AttachButton uploading={uploading} />
              </PromptInputTools>
              <ComposerSubmit text={text} status={status} uploading={uploading} />
            </PromptInputFooter>
          </PromptInput>
        </div>
      </div>

      {/* Order summary sidebar */}
      <aside className="hidden w-80 shrink-0 border-l p-6 md:block">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Order Summary
        </h2>
        <div className="space-y-3 text-sm">
          <SpecRow label="Size" value={spec.size} />
          <SpecRow label="Base text" value={spec.baseText} />
          <Separator />
          <SpecRow
            label="Images"
            value={workspace.length ? String(workspace.length) : undefined}
          />
        </div>
      </aside>
    </div>
  );
}

/**
 * ChatGPT-style history sidebar: new-design button + past sessions by title.
 * Rendered statically on desktop and inside the mobile slide-over.
 */
function ChatSidebar({
  sessions,
  activeId,
  onNavigate,
  onClose,
}: {
  sessions: SessionListItem[];
  activeId: string;
  onNavigate?: () => void;
  onClose?: () => void;
}) {
  return (
    <div className="flex h-full w-64 flex-col">
      <div className="flex items-center gap-2 p-3">
        <Link
          href="/"
          onClick={onNavigate}
          className="flex flex-1 items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm font-medium transition-colors hover:bg-secondary"
        >
          <Plus className="size-4" />
          New figurine
        </Link>
        {onClose && (
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        )}
      </div>
      <div className="px-2 pb-1">
        <Link
          href="/images"
          onClick={onNavigate}
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
        >
          <Images className="size-4" />
          Images
        </Link>
      </div>
      <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-4">
        {sessions.map((s) => (
          <Link
            key={s.id}
            href={`/s/${s.id}`}
            onClick={onNavigate}
            title={s.title}
            className={cn(
              "block truncate rounded-md px-3 py-2 text-sm transition-colors",
              s.id === activeId
                ? "bg-secondary font-medium"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
            )}
          >
            {s.title}
          </Link>
        ))}
        {sessions.length === 0 && (
          <p className="px-3 py-2 text-sm text-muted-foreground">
            No chats yet
          </p>
        )}
      </nav>
    </div>
  );
}

/**
 * A question from the agent with tappable quick-reply options (the askUser
 * tool). After answering, the chosen option stays highlighted and the rest
 * fade; the customer can also just type instead of tapping.
 */
function QuickReplies({
  question,
  options,
  chosen,
  answered,
  disabled,
  onChoose,
}: {
  question: string;
  options: string[];
  chosen?: string;
  answered: boolean;
  disabled: boolean;
  onChoose: (option: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <MessageResponse>{question}</MessageResponse>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <Button
            key={opt}
            type="button"
            size="sm"
            variant={answered && chosen === opt ? "default" : "outline"}
            disabled={disabled || answered}
            onClick={() => onChoose(opt)}
            className={cn(
              "h-auto whitespace-normal rounded-full px-4 py-1.5 text-left",
              answered && chosen === opt && "disabled:opacity-100",
              answered && chosen !== opt && "opacity-40",
            )}
          >
            {opt}
          </Button>
        ))}
      </div>
    </div>
  );
}

/** Previews of images staged in the composer (added via button/paste/drop). */
function ComposerAttachments() {
  const attachments = usePromptInputAttachments();
  if (attachments.files.length === 0) return null;
  return (
    <Attachments variant="grid" className="mr-auto max-w-full px-2 pt-2 sm:px-3 sm:pt-3">
      {attachments.files.map((f) => (
        <Attachment
          key={f.id}
          className="size-20 sm:size-24"
          data={f}
          onRemove={() => attachments.remove(f.id)}
        >
          <AttachmentPreview />
          <AttachmentRemove />
        </Attachment>
      ))}
    </Attachments>
  );
}

function AttachButton({ uploading }: { uploading: boolean }) {
  const attachments = usePromptInputAttachments();
  return (
    <PromptInputButton
      onClick={attachments.openFileDialog}
      disabled={uploading}
      className="max-w-full"
    >
      <ImageIcon className="size-4" />
      <span className="truncate">{uploading ? "Uploading…" : "Add photos"}</span>
    </PromptInputButton>
  );
}

/** Submit enabled when there's text OR staged images. */
function ComposerSubmit({
  text,
  status,
  uploading,
}: {
  text: string;
  status: ChatStatus;
  uploading: boolean;
}) {
  const attachments = usePromptInputAttachments();
  const hasContent = Boolean(text.trim()) || attachments.files.length > 0;
  return (
    <PromptInputSubmit
      disabled={!hasContent || uploading}
      status={uploading ? "submitted" : status}
    />
  );
}

function SpecRow({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      {value ? (
        <Badge variant="secondary" className="font-normal">
          {value}
        </Badge>
      ) : (
        <span className="text-muted-foreground/50">—</span>
      )}
    </div>
  );
}

function MobileOrderSummary({
  spec,
  imageCount,
}: {
  spec: OrderSpec;
  imageCount: number;
}) {
  const rows = [
    spec.size ? { label: "Size", value: spec.size } : null,
    spec.baseText ? { label: "Base", value: spec.baseText } : null,
    imageCount > 0 ? { label: "Images", value: String(imageCount) } : null,
  ].filter((row): row is { label: string; value: string } => Boolean(row));

  if (rows.length === 0) return null;

  return (
    <div
      aria-label="Order summary"
      className="mb-2 flex items-center gap-2 overflow-x-auto rounded-lg border bg-background px-3 py-2 text-xs"
    >
      <span className="shrink-0 font-medium text-muted-foreground">Order</span>
      {rows.map((row) => (
        <span
          key={row.label}
          className="inline-flex shrink-0 items-center gap-1 rounded-md bg-secondary px-2 py-1"
        >
          <span className="text-muted-foreground">{row.label}</span>
          <span className="max-w-36 truncate font-medium">{row.value}</span>
        </span>
      ))}
    </div>
  );
}
