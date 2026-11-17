"use client";

import { useRef } from "react";
import Image from "next/image";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Suggestions,
  Suggestion,
} from "@/components/ai-elements/suggestion";

/**
 * Guided empty-state for a brand-new chat. Instead of a blank ChatGPT-style
 * screen, the customer sees what this is (photo → figurine), real customer
 * transformations, the 4 steps ahead, and one obvious action: upload a photo.
 */

// Real customer photo→figurine composites, reused from everything3dindia.com.
const EXAMPLES = [
  { src: "/welcome/hero1-figurine.jpg", alt: "Couple photo turned into a couple figurine" },
  { src: "/welcome/hero-amrita.jpg", alt: "Couple playing guitar turned into figurines" },
  { src: "/welcome/hero2-figurine.jpg", alt: "Parents' photo turned into figurines" },
  { src: "/welcome/hero-uncle.jpg", alt: "Grandparents' anniversary photo turned into figurines" },
];

const STEPS = [
  "Upload a clear photo",
  "Pick from two designs",
  "Approve it — changes are free",
  "Pick a size & order",
];

// Tappable starters for customers who don't have a photo ready.
const STARTERS = [
  "Couple figurine 💑",
  "Me + my pet 🐶",
  "Doctor figurine 🩺",
  "I have a ChatGPT design",
  "What does it cost?",
];

export function WelcomeScreen({
  onPhotos,
  onStarter,
  uploading,
  disabled,
}: {
  onPhotos: (files: File[]) => void;
  onStarter: (text: string) => void;
  uploading: boolean;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-4 py-3 sm:gap-7 sm:py-4">
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.currentTarget.files ?? []);
          e.currentTarget.value = ""; // allow re-picking the same file
          if (files.length) onPhotos(files);
        }}
      />

      <div className="space-y-1.5 text-center sm:space-y-2">
        <h2 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          Turn your photo into a 3D-printed figurine
        </h2>
        <p className="mx-auto max-w-md text-pretty text-sm text-muted-foreground sm:text-base">
          Designed from your photo, made in Bangalore, delivered
          anywhere in India.
        </p>
      </div>

      {/* Real customer transformations — scrolls horizontally on mobile.
          Tile sizes are chosen so all four fit the max-w-2xl column centered
          on desktop (centering + overflow would clip the left edge). */}
      <div className="-mx-3 flex w-[calc(100%+1.5rem)] snap-x gap-2.5 overflow-x-auto px-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:mx-0 sm:w-full sm:justify-center sm:gap-3 sm:px-0">
        {EXAMPLES.map((ex) => (
          <Image
            key={ex.src}
            src={ex.src}
            alt={ex.alt}
            width={288}
            height={288}
            className="size-28 shrink-0 snap-start rounded-xl border object-cover sm:size-36"
          />
        ))}
      </div>

      {/* Keep the primary action above process details on short phone screens. */}
      <div className="flex w-full max-w-md flex-col items-center gap-2">
        <Button
          size="lg"
          className="h-11 w-full rounded-full text-base sm:h-12"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || uploading}
        >
          {uploading ? (
            <>
              <Spinner className="size-4" />
              Uploading…
            </>
          ) : (
            <>
              <Upload className="size-4" />
              Upload a photo
            </>
          )}
        </Button>
        <p className="text-xs text-muted-foreground">
          Design previews are free — you only pay when you order.
        </p>
      </div>

      {/* Title-only 2×2 steps explain the process without burying the CTA. */}
      <ol className="grid w-full max-w-md grid-cols-2 gap-1.5 sm:max-w-xl sm:gap-2">
        {STEPS.map((step, i) => (
          <li
            key={step}
            className="flex min-h-11 items-center gap-2 rounded-xl border bg-secondary/30 px-2.5 py-2 sm:min-h-12 sm:gap-3 sm:px-4 sm:py-2.5"
          >
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary sm:size-7 sm:text-xs">
              {i + 1}
            </span>
            <p className="text-[13px] leading-tight font-medium sm:text-sm">
              {step}
            </p>
          </li>
        ))}
      </ol>

      <Suggestions className="justify-start sm:justify-center">
        {STARTERS.map((s) => (
          <Suggestion
            key={s}
            suggestion={s}
            onClick={onStarter}
            disabled={disabled || uploading}
          />
        ))}
      </Suggestions>
    </div>
  );
}
