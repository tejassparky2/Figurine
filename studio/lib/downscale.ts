/**
 * Browser-side image downscaling, run before upload. Two reasons:
 * - The chat model's vision API rejects images over 5 MB (a phone photo or a
 *   big ChatGPT PNG easily exceeds that, failing the whole chat turn).
 * - Nothing downstream needs more than ~2K pixels; smaller uploads are faster
 *   and cheaper.
 */
export async function downscaleImage(
  blob: Blob,
  maxDim = 2048,
  quality = 0.85,
): Promise<{ blob: Blob; mediaType: string }> {
  const original = { blob, mediaType: blob.type || "image/png" };
  try {
    const bitmap = await createImageBitmap(blob);
    const scale = Math.min(1, maxDim / Math.max(bitmap.width, bitmap.height));

    // Small enough in pixels AND bytes: keep as-is. Heavy files (big PNGs)
    // get re-encoded to JPEG even when the dimensions are fine.
    if (scale === 1 && blob.size < 3 * 1024 * 1024) return original;

    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) return original;
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);

    const out = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", quality),
    );
    if (!out) return original;
    return { blob: out, mediaType: "image/jpeg" };
  } catch {
    // Format the browser can't decode — send the original and let the
    // server-side size cap catch anything oversized.
    return original;
  }
}
