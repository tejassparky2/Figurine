"use client";

import { useId, useState } from "react";
import Image from "next/image";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { BasePreview } from "@/components/base-preview";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { ArrowRight, Box, ImageIcon, Star, XIcon } from "lucide-react";

/**
 * Chat image that opens a full-size lightbox on click. `className` styles the
 * inline <img>; `triggerClassName` sizes the clickable wrapper.
 */
function ZoomableImage({
  src,
  alt,
  className,
  triggerClassName,
}: {
  src: string;
  alt: string;
  className?: string;
  triggerClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className={cn("block cursor-zoom-in", triggerClassName)}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className={className} />
      </DialogTrigger>
      {/* Full-width content so the image isn't shrink-wrapped against
          left:50% (w-auto caps it at half the viewport on mobile). Radix
          forces pointer-events:auto on modal content, so clicks in the empty
          band beside the image are closed by hand instead of the overlay. */}
      <DialogContent
        aria-describedby={undefined}
        showCloseButton={false}
        onClick={(e) => e.target === e.currentTarget && setOpen(false)}
        className="flex w-full max-w-none justify-center border-none bg-transparent p-0 shadow-none ring-0 sm:max-w-none"
      >
        <DialogTitle className="sr-only">{alt}</DialogTitle>
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt}
            className="max-h-[85vh] max-w-[calc(100vw-2rem)] rounded-xl bg-white object-contain"
          />
          {/* High-contrast close button — the ui/dialog default (ghost) is
              invisible over dark photos. */}
          <DialogClose className="absolute top-2 right-2 rounded-full bg-black/50 p-1.5 text-white transition-colors hover:bg-black/70">
            <XIcon className="size-4" />
            <span className="sr-only">Close</span>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Customer-controlled render/base switch. This is deliberately local UI:
 * toggling it never sends a chat turn or spends an image-generation credit. */
function PreviewWithBaseToggle({
  url,
  alt,
  defaultBase = false,
  imageClassName,
}: {
  url: string;
  alt: string;
  defaultBase?: boolean;
  imageClassName: string;
}) {
  const [onBase, setOnBase] = useState(defaultBase);
  return (
    <div className="relative">
      {onBase ? (
        <BasePreview imageUrl={url} className={imageClassName} />
      ) : (
        <ZoomableImage
          src={url}
          alt={alt}
          triggerClassName="w-full"
          className={imageClassName}
        />
      )}
      <button
        type="button"
        aria-pressed={onBase}
        onClick={() => setOnBase((value) => !value)}
        className="absolute top-2 right-2 inline-flex items-center gap-1.5 rounded-full border bg-background/90 px-2.5 py-1.5 text-xs font-medium shadow-sm backdrop-blur transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {onBase ? <ImageIcon className="size-3.5" /> : <Box className="size-3.5" />}
        {onBase ? "Render only" : "On the base"}
      </button>
    </div>
  );
}

/**
 * Generative-UI card rendered from the image tools (generatePixarFigurine,
 * editImage, transformImage, makePrintable). Handles loading, error, and the
 * resulting image with Keep / Revise actions.
 */
export function ImageCard({
  url,
  loading,
  loadingLabel = "Working…",
  error,
  disabled,
  onKeep,
  onRevise,
}: {
  url?: string;
  loading?: boolean;
  loadingLabel?: string;
  error?: string;
  disabled?: boolean;
  onKeep?: () => void;
  onRevise?: () => void;
}) {
  if (loading) {
    return (
      <Card className="w-[min(18rem,calc(100vw-2rem))]">
        <CardContent className="flex aspect-square flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground">
          <Spinner className="size-6" />
          <span>{loadingLabel}</span>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="w-[min(18rem,calc(100vw-2rem))] border-destructive/50">
        <CardContent className="p-4 text-sm text-destructive">
          {error}
        </CardContent>
      </Card>
    );
  }

  if (!url) return null;

  return (
    <Card className="w-[min(18rem,calc(100vw-2rem))] gap-0 overflow-hidden py-0">
      <CardContent className="p-0">
        <PreviewWithBaseToggle
          url={url}
          alt="Figurine"
          defaultBase
          imageClassName="aspect-square w-full bg-white object-contain"
        />
      </CardContent>
      <CardFooter className="grid grid-cols-2 gap-2 p-3">
        <Button
          size="sm"
          className="flex-1"
          onClick={onKeep}
          disabled={disabled}
        >
          Keep this
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="flex-1"
          onClick={onRevise}
          disabled={disabled}
        >
          Revise
        </Button>
      </CardFooter>
    </Card>
  );
}

/**
 * Side-by-side option cards for tools that return multiple images (the two
 * figurine options). The customer picks one to continue with.
 */
export function ImageOptionCards({
  urls,
  labels,
  descriptions,
  recommendedIndex,
  disabled,
  onChoose,
}: {
  urls: string[];
  labels?: string[];
  descriptions?: string[];
  recommendedIndex?: number;
  disabled?: boolean;
  onChoose: (index: number) => void;
}) {
  return (
    <div className="grid w-[min(30rem,calc(100vw-2rem))] grid-cols-1 gap-3 sm:grid-cols-2">
      {urls.map((url, i) => {
        const label = labels?.[i] ?? `Option ${i + 1}`;
        return (
          <Card key={i} className="min-w-0 gap-0 overflow-hidden py-0">
            <CardContent className="relative p-0">
              <PreviewWithBaseToggle
                url={url}
                alt={label}
                imageClassName="aspect-square w-full bg-white object-contain"
              />
              {recommendedIndex === i && (
                <Badge className="absolute top-2 left-2 gap-1 bg-amber-400 text-amber-950 hover:bg-amber-400">
                  <Star className="size-3 fill-current" />
                  Recommended
                </Badge>
              )}
            </CardContent>
            <CardFooter className="flex flex-col items-stretch gap-2 p-3">
              <div>
                <div className="text-sm font-medium">{label}</div>
                {descriptions?.[i] && (
                  <div className="text-xs text-muted-foreground">
                    {descriptions[i]}
                  </div>
                )}
              </div>
              <Button
                size="sm"
                className="w-full"
                onClick={() => onChoose(i)}
                disabled={disabled}
              >
                Choose {label}
              </Button>
            </CardFooter>
          </Card>
        );
      })}
    </div>
  );
}

const PRODUCT_LABEL: Record<string, string> = {
  single: "Single figurine",
  couple: "Couple figurine",
  pet: "Figurine with pet",
  family: "Family figurine",
  custom: "Custom figurine",
};

// Matches the live store variants: Standard / Large / Extra Large.
const SIZE_LABEL: Record<string, string> = {
  "13cm": "Standard",
  "15cm": "Large",
  "18cm": "XL",
};

// The same real render→print examples shown on everything3dindia.com, served
// from the store CDN so Studio presents the comparisons customers already see.
const RENDER_TO_PRINT_EXAMPLES = [
  {
    renderUrl:
      "https://everything3dindia.com/cdn/shop/t/5/assets/render-vs-print-feature-render-clean.png?v=161294285981400920111777264683",
    renderAlt: "AI render preview of a couple figurine",
    printUrl:
      "https://everything3dindia.com/cdn/shop/t/5/assets/render-vs-print-feature-print-clean.png?v=176782347533963688611777264701",
    printAlt: "Final 3D-printed couple figurine",
    note: "Overall look stays similar, but fine details are simplified for printing.",
  },
  {
    renderUrl:
      "https://everything3dindia.com/cdn/shop/t/5/assets/render-vs-print-casual-render-real.png?v=170232617760361094371777268236",
    renderAlt: "AI render preview of a casual couple figurine",
    printUrl:
      "https://everything3dindia.com/cdn/shop/t/5/assets/render-vs-print-casual-print-real.png?v=37229423226640786361777267333",
    printAlt: "Final 3D-printed casual couple figurine",
    note: "Pose may be adjusted slightly for stability.",
  },
  {
    renderUrl:
      "https://everything3dindia.com/cdn/shop/t/5/assets/render-vs-print-wedding-render-clean.png?v=99147465659503695471777264689",
    renderAlt: "AI render preview of a couple in traditional outfits",
    printUrl:
      "https://everything3dindia.com/cdn/shop/t/5/assets/render-vs-print-wedding-print-real.png?v=106160254028180264911777267333",
    printAlt: "Final 3D-printed couple in traditional outfits",
    note: "Complex clothing patterns may be simplified.",
  },
] as const;

/** Compact pre-order expectation setting, using the store's real examples. */
function RenderToPrintNotice() {
  const titleId = useId();

  return (
    <section
      aria-labelledby={titleId}
      className="w-full rounded-xl border bg-secondary/30 p-3 text-left"
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 id={titleId} className="text-sm font-semibold">
          Render → final 3D print
        </h3>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          Swipe · 3 examples
        </span>
      </div>
      <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
        Your render is a concept preview. We adapt it for real-world 3D
        printing.
      </p>

      <div
        aria-label="Render and final print comparisons"
        className="mt-2.5 flex snap-x snap-mandatory overflow-x-auto pb-1 outline-none [scrollbar-width:none] focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-scrollbar]:hidden"
        role="region"
        tabIndex={0}
      >
        {RENDER_TO_PRINT_EXAMPLES.map((example) => (
          <figure
            key={example.renderUrl}
            className="w-[calc(100%-1.25rem)] shrink-0 snap-start pr-2"
          >
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-1.5">
              <div className="space-y-1">
                <span className="block text-[11px] font-medium text-muted-foreground">
                  AI render
                </span>
                <div className="relative aspect-[4/3] overflow-hidden rounded-lg border bg-white">
                  <Image
                    src={example.renderUrl}
                    alt={example.renderAlt}
                    fill
                    sizes="(max-width: 768px) 38vw, 130px"
                    className="object-contain"
                  />
                </div>
              </div>
              <ArrowRight
                aria-hidden="true"
                className="mt-5 size-4 shrink-0 text-muted-foreground"
              />
              <div className="space-y-1">
                <span className="block text-[11px] font-medium text-muted-foreground">
                  Final 3D print
                </span>
                <div className="relative aspect-[4/3] overflow-hidden rounded-lg border bg-white">
                  <Image
                    src={example.printUrl}
                    alt={example.printAlt}
                    fill
                    sizes="(max-width: 768px) 38vw, 130px"
                    className="object-contain"
                  />
                </div>
              </div>
            </div>
            <figcaption className="mt-2 min-h-8 text-xs leading-snug text-muted-foreground">
              {example.note}
            </figcaption>
          </figure>
        ))}
      </div>

      <p className="mt-2 border-t pt-2 text-xs leading-snug">
        We always try to keep the likeness, outfit feel, and overall vibe as
        close as possible.
      </p>
    </section>
  );
}

/**
 * Interactive order card rendered from the proposeOrder tool: size pills with
 * server-computed prices, optional base text, and the customer's WhatsApp
 * number — the only thing they have to type in the whole flow. Placing the
 * order sends one structured message back into the chat.
 */
export function OrderCard({
  imageUrl,
  product,
  initialBaseText,
  initialWhatsapp,
  prices,
  disabled,
  onPlaceOrder,
}: {
  imageUrl?: string;
  product: string;
  initialBaseText?: string;
  initialWhatsapp?: string;
  /** Price per size (Rs.), or null/undefined when the team quotes (custom). */
  prices?: Record<string, number> | null;
  disabled?: boolean;
  onPlaceOrder: (choice: {
    size: string;
    baseText: string;
    whatsapp: string;
  }) => void;
}) {
  const [size, setSize] = useState("13cm");
  const [baseText, setBaseText] = useState(initialBaseText ?? "");
  const [whatsapp, setWhatsapp] = useState(initialWhatsapp ?? "");

  const digits = whatsapp.replace(/\D/g, "");
  const validPhone = digits.length >= 10 && digits.length <= 14;
  const total = prices?.[size];

  return (
    <Card className="w-[min(22rem,calc(100vw-2rem))] gap-0 overflow-hidden py-0">
      {imageUrl && (
        <CardContent className="border-b p-0">
          <BasePreview imageUrl={imageUrl} baseText={baseText} />
        </CardContent>
      )}
      <CardContent className="flex items-center gap-3 border-b bg-secondary/30 p-4">
        <div className="min-w-0">
          <p className="text-sm font-semibold">Your figurine</p>
          <p className="truncate text-xs text-muted-foreground">
            {PRODUCT_LABEL[product] ?? product} · base preview updates as you type
          </p>
        </div>
      </CardContent>

      <CardContent className="space-y-4 p-4">
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Size</p>
          <div className="grid grid-cols-3 gap-2">
            {Object.keys(SIZE_LABEL).map((s) => (
              <button
                key={s}
                type="button"
                disabled={disabled}
                onClick={() => setSize(s)}
                className={cn(
                  "rounded-xl border px-3 py-2 text-center transition-colors disabled:opacity-60",
                  size === s
                    ? "border-primary ring-1 ring-primary"
                    : "hover:bg-secondary/50",
                )}
              >
                <span className="block text-sm font-medium">
                  {SIZE_LABEL[s]}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {s}
                </span>
                {prices?.[s] != null && (
                  <span className="block text-sm font-semibold">
                    ₹{prices[s].toLocaleString("en-IN")}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">
            Text on the base (optional)
          </p>
          <Input
            value={baseText}
            onChange={(e) => setBaseText(e.currentTarget.value)}
            disabled={disabled}
            maxLength={40}
            placeholder="e.g. Asha ♥ Rohan"
          />
        </div>

        <RenderToPrintNotice />

        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">
            WhatsApp number — we confirm your order there
          </p>
          <Input
            type="tel"
            inputMode="tel"
            value={whatsapp}
            onChange={(e) => setWhatsapp(e.currentTarget.value)}
            disabled={disabled}
            placeholder="10-digit number"
          />
        </div>

        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted-foreground">Total</span>
          <span className="text-lg font-bold">
            {total != null
              ? `₹${total.toLocaleString("en-IN")}`
              : "Quoted on WhatsApp"}
          </span>
        </div>
      </CardContent>

      <CardFooter className="flex-col gap-2 p-4 pt-0">
        <Button
          className="w-full rounded-full"
          disabled={disabled || !validPhone}
          onClick={() => onPlaceOrder({ size, baseText: baseText.trim(), whatsapp: digits })}
        >
          Place order
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          ↻ Free design changes · 🚚 Ships in 48h after approval
        </p>
      </CardFooter>
    </Card>
  );
}

/** Confirmation card rendered from a successful finalizeOrder call. */
export function OrderConfirmedCard({
  imageUrl,
  product,
  size,
  baseText,
  priceInr,
  whatsapp,
  checkoutUrl,
}: {
  imageUrl?: string;
  product?: string;
  size?: string;
  baseText?: string;
  priceInr?: number | null;
  whatsapp?: string;
  /** Prefilled Shopify checkout; absent for custom (team-quoted) products. */
  checkoutUrl?: string | null;
}) {
  return (
    <Card className="w-80 gap-0 overflow-hidden py-0">
      {imageUrl && (
        <CardContent className="p-0">
          <ZoomableImage
            src={imageUrl}
            alt="Your figurine"
            triggerClassName="w-full"
            className="w-full bg-white"
          />
        </CardContent>
      )}
      <CardFooter className="flex flex-col items-start gap-1 p-4 text-sm">
        <span className="font-semibold">Order request received 🎉</span>
        <span className="text-muted-foreground">
          {product} figurine · {size}
          {baseText ? ` · base: “${baseText}”` : ""}
        </span>
        <span className="text-muted-foreground">
          {priceInr
            ? `Total: Rs. ${priceInr.toLocaleString("en-IN")}`
            : "Price: our team will confirm"}
        </span>
        {checkoutUrl ? (
          <>
            <Button asChild className="mt-2 w-full">
              <a href={checkoutUrl} target="_blank" rel="noopener noreferrer">
                Pay now{priceInr ? ` · ₹${priceInr.toLocaleString("en-IN")}` : ""}
              </a>
            </Button>
            <span className="w-full text-center text-xs text-muted-foreground">
              or we’ll WhatsApp you at {whatsapp} to confirm
            </span>
          </>
        ) : (
          <span className="text-muted-foreground">
            We’ll WhatsApp you at {whatsapp} to confirm and take payment.
          </span>
        )}
      </CardFooter>
    </Card>
  );
}

/**
 * One-tap WhatsApp handoff card, rendered from a successful handoffToHuman
 * call. The link opens the team's WhatsApp chat prefilled with the session
 * URL, so the customer never has to copy a number.
 */
export function HandoffCard({ whatsappUrl }: { whatsappUrl: string }) {
  return (
    <Card className="w-80 gap-0 py-0">
      <CardFooter className="flex flex-col items-stretch gap-3 p-4 text-sm">
        <span className="font-semibold">Our team is on it 💬</span>
        <span className="text-muted-foreground">
          We&rsquo;ve shared your chat with the team — or message us right now:
        </span>
        <Button
          asChild
          className="bg-[#25D366] text-white hover:bg-[#1faf54]"
        >
          <a href={whatsappUrl} target="_blank" rel="noopener noreferrer">
            Chat with us on WhatsApp
          </a>
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          +91 78925 54719
        </p>
      </CardFooter>
    </Card>
  );
}

/** Small thumbnail for an image the customer uploaded. */
export function UploadedThumb({ url }: { url: string }) {
  return (
    <ZoomableImage
      src={url}
      alt="Uploaded"
      triggerClassName="w-fit"
      className="max-h-40 w-40 max-w-full rounded-lg border object-cover"
    />
  );
}
