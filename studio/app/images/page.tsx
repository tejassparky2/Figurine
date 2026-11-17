import Link from "next/link";
import { ImageIcon, MessageSquare, Plus } from "lucide-react";
import { getImageGallery } from "@/lib/images";
import { getOwnerId } from "@/lib/owner";

export const dynamic = "force-dynamic";

/**
 * Gallery of every image across this visitor's chats — uploads and generated
 * designs. Clicking an image opens the chat it belongs to; often the fastest
 * way to find a past design.
 */
export default async function ImagesPage() {
  const images = await getImageGallery(await getOwnerId());

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6 sm:py-10">
      <header className="mb-6 flex items-center justify-between gap-3">
        <h1 className="text-base font-semibold sm:text-lg">Images</h1>
        <div className="flex items-center gap-2">
          <Link
            href="/chats"
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-secondary"
          >
            <MessageSquare className="size-4" />
            Chats
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-secondary"
          >
            <Plus className="size-4" />
            New design
          </Link>
        </div>
      </header>

      {images.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border py-16 text-center">
          <ImageIcon className="size-8 text-muted-foreground" />
          <p className="max-w-sm text-sm text-muted-foreground">
            No images yet — upload a photo or generate a design and it will
            show up here.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 sm:gap-3 md:grid-cols-5">
          {images.map((img) => (
            <Link
              key={img.sessionId + img.id}
              href={`/s/${img.sessionId}`}
              title={`${img.sessionTitle} — ${img.label}`}
              className="group relative block overflow-hidden rounded-lg border bg-white"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.url}
                alt={img.label}
                loading="lazy"
                className="aspect-square w-full object-contain transition-transform duration-200 group-hover:scale-105"
              />
              <span className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-6 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
                {img.sessionTitle}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
