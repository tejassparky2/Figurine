"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const SIZE = 900;
const BACKGROUND_MIN = 232;

type Subject = {
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
};

/**
 * Remove only neutral-white pixels connected to an image edge. Unlike a
 * global white color key, this keeps white coats, shirts, eyes and shoes.
 * Returns null when the source CDN disallows pixel reads; drawing then falls
 * back to a multiply blend, which still works well on Studio's white renders.
 */
function extractSubject(image: HTMLImageElement): Subject | null {
  const scale = Math.min(1, 1024 / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const source = document.createElement("canvas");
  source.width = width;
  source.height = height;
  const context = source.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, width, height);

  let imageData: ImageData;
  try {
    imageData = context.getImageData(0, 0, width, height);
  } catch {
    return null;
  }

  const pixels = imageData.data;
  const count = width * height;
  const visited = new Uint8Array(count);
  const queue = new Int32Array(count);
  let head = 0;
  let tail = 0;

  const isBackdrop = (index: number) => {
    const offset = index * 4;
    const r = pixels[offset];
    const g = pixels[offset + 1];
    const b = pixels[offset + 2];
    return Math.min(r, g, b) >= BACKGROUND_MIN && Math.max(r, g, b) - Math.min(r, g, b) <= 22;
  };
  const offer = (index: number) => {
    if (visited[index] || !isBackdrop(index)) return;
    visited[index] = 1;
    queue[tail++] = index;
  };

  for (let x = 0; x < width; x += 1) {
    offer(x);
    offer((height - 1) * width + x);
  }
  for (let y = 0; y < height; y += 1) {
    offer(y * width);
    offer(y * width + width - 1);
  }
  while (head < tail) {
    const index = queue[head++];
    const x = index % width;
    const y = Math.floor(index / width);
    if (x > 0) offer(index - 1);
    if (x + 1 < width) offer(index + 1);
    if (y > 0) offer(index - width);
    if (y + 1 < height) offer(index + width);
  }

  for (let index = 0; index < count; index += 1) {
    if (visited[index]) pixels[index * 4 + 3] = 0;
  }

  // Soften just the immediate matte edge. Applying this to every white pixel
  // would make white clothing translucent.
  const edge = new Uint8Array(count);
  for (let index = 0; index < count; index += 1) {
    if (!visited[index]) continue;
    const x = index % width;
    const y = Math.floor(index / width);
    if (x > 0) edge[index - 1] = 1;
    if (x + 1 < width) edge[index + 1] = 1;
    if (y > 0) edge[index - width] = 1;
    if (y + 1 < height) edge[index + width] = 1;
  }
  for (let index = 0; index < count; index += 1) {
    if (!edge[index] || visited[index]) continue;
    const offset = index * 4;
    const min = Math.min(pixels[offset], pixels[offset + 1], pixels[offset + 2]);
    if (min > 220) {
      pixels[offset + 3] = Math.min(pixels[offset + 3], Math.max(0, Math.round((245 - min) * 10.2)));
    }
  }
  context.putImageData(imageData, 0, 0);

  let left = width;
  let top = height;
  let right = -1;
  let bottom = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (pixels[(y * width + x) * 4 + 3] < 40) continue;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x);
      bottom = Math.max(bottom, y);
    }
  }
  if (right < left || bottom < top) return null;

  const margin = 3;
  left = Math.max(0, left - margin);
  top = Math.max(0, top - margin);
  right = Math.min(width - 1, right + margin);
  bottom = Math.min(height - 1, bottom + margin);
  const cropWidth = right - left + 1;
  const cropHeight = bottom - top + 1;
  const crop = document.createElement("canvas");
  crop.width = cropWidth;
  crop.height = cropHeight;
  crop.getContext("2d")?.drawImage(
    source,
    left,
    top,
    cropWidth,
    cropHeight,
    0,
    0,
    cropWidth,
    cropHeight,
  );
  return { canvas: crop, width: cropWidth, height: cropHeight };
}

function polygon(
  context: CanvasRenderingContext2D,
  points: Array<[number, number]>,
) {
  context.beginPath();
  points.forEach(([x, y], index) =>
    index === 0 ? context.moveTo(x, y) : context.lineTo(x, y),
  );
  context.closePath();
}

function drawPreview(
  canvas: HTMLCanvasElement,
  image: HTMLImageElement,
  subject: Subject | null,
  baseText: string,
) {
  canvas.width = SIZE;
  canvas.height = SIZE;
  const context = canvas.getContext("2d");
  if (!context) return;

  const backdrop = context.createRadialGradient(450, 300, 30, 450, 360, 650);
  backdrop.addColorStop(0, "#ffffff");
  backdrop.addColorStop(0.7, "#f7f5f2");
  backdrop.addColorStop(1, "#e7e3de");
  context.fillStyle = backdrop;
  context.fillRect(0, 0, SIZE, SIZE);

  const floor = context.createLinearGradient(0, 600, 0, SIZE);
  floor.addColorStop(0, "rgba(244,241,237,0)");
  floor.addColorStop(1, "rgba(211,205,198,0.72)");
  context.fillStyle = floor;
  context.fillRect(0, 575, SIZE, 325);

  context.save();
  context.filter = "blur(22px)";
  context.fillStyle = "rgba(42,38,35,0.26)";
  context.beginPath();
  context.ellipse(450, 812, 325, 40, 0, 0, Math.PI * 2);
  context.fill();
  context.restore();

  // Top plane: narrower at the rear, wider where it meets the front face.
  polygon(context, [
    [184, 632],
    [716, 632],
    [746, 696],
    [154, 696],
  ]);
  const topGradient = context.createLinearGradient(0, 632, 0, 696);
  topGradient.addColorStop(0, "#303338");
  topGradient.addColorStop(0.55, "#17191d");
  topGradient.addColorStop(1, "#090a0c");
  context.fillStyle = topGradient;
  context.fill();
  context.strokeStyle = "#050607";
  context.lineWidth = 6;
  context.stroke();
  context.strokeStyle = "rgba(105,108,114,0.55)";
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(198, 641);
  context.lineTo(702, 641);
  context.stroke();

  context.save();
  context.shadowColor = "rgba(0,0,0,0.24)";
  context.shadowBlur = 16;
  context.shadowOffsetY = 9;
  if (subject) {
    const figureHeight = 600;
    const figureWidth = (subject.width / subject.height) * figureHeight;
    context.drawImage(
      subject.canvas,
      (SIZE - figureWidth) / 2,
      698 - figureHeight,
      figureWidth,
      figureHeight,
    );
  } else {
    // CORS-safe fallback: white multiplies away against the backdrop/base, so
    // the source render can still be placed without reading its pixels.
    const height = 700;
    const width = (image.naturalWidth / image.naturalHeight) * height;
    context.globalCompositeOperation = "multiply";
    context.drawImage(image, (SIZE - width) / 2, 700 - height, width, height);
  }
  context.restore();

  // Front face flares outward toward the floor, matching the printed base.
  polygon(context, [
    [154, 692],
    [746, 692],
    [797, 801],
    [103, 801],
  ]);
  const frontGradient = context.createLinearGradient(0, 692, 0, 801);
  frontGradient.addColorStop(0, "#25282d");
  frontGradient.addColorStop(1, "#08090b");
  context.fillStyle = frontGradient;
  context.fill();
  context.strokeStyle = "#050607";
  context.lineWidth = 6;
  context.stroke();

  polygon(context, [
    [173, 710],
    [727, 710],
    [765, 783],
    [135, 783],
  ]);
  context.fillStyle = "#17191d";
  context.fill();
  context.strokeStyle = "#3d4046";
  context.lineWidth = 2.5;
  context.stroke();

  const text = baseText.trim();
  if (text) {
    let fontSize = 48;
    do {
      context.font = `700 ${fontSize}px Arial, Helvetica, sans-serif`;
      if (context.measureText(text).width <= 540) break;
      fontSize -= 2;
    } while (fontSize > 25);
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.lineJoin = "round";
    context.fillStyle = "rgba(0,0,0,0.9)";
    context.fillText(text, 450, 750 + 4);
    context.strokeStyle = "#c9c4b8";
    context.lineWidth = 2;
    context.fillStyle = "#f5f2e9";
    context.strokeText(text, 450, 750);
    context.fillText(text, 450, 750);
  }
}

export function BasePreview({
  imageUrl,
  baseText = "",
  className,
}: {
  imageUrl: string;
  baseText?: string;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [source, setSource] = useState<{
    image: HTMLImageElement;
    subject: Subject | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const finish = (image: HTMLImageElement) => {
      if (!cancelled) setSource({ image, subject: extractSubject(image) });
    };
    const image = new window.Image();
    image.crossOrigin = "anonymous";
    image.onload = () => finish(image);
    image.onerror = () => {
      // A few CDNs allow display but do not send a CORS header. Retry without
      // pixel access; drawPreview's multiply fallback still removes white.
      const fallback = new window.Image();
      fallback.onload = () => finish(fallback);
      fallback.src = imageUrl;
    };
    image.src = imageUrl;
    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  useEffect(() => {
    if (canvasRef.current && source) {
      drawPreview(canvasRef.current, source.image, source.subject, baseText);
    }
  }, [baseText, source]);

  return (
    <div className={cn("relative aspect-square overflow-hidden bg-white", className)}>
      <canvas
        ref={canvasRef}
        aria-label={`Figurine shown on its base${baseText.trim() ? ` with text ${baseText.trim()}` : ""}`}
        className={cn(
          "size-full transition-opacity duration-200",
          source ? "opacity-100" : "opacity-0",
        )}
        role="img"
      />
      {!source && (
        <div className="absolute inset-0 animate-pulse bg-secondary/50" aria-hidden="true" />
      )}
    </div>
  );
}
