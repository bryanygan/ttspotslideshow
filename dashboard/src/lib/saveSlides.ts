import { slideDownloadUrl } from "./slides";

// Helpers for saving a whole slideshow to the phone in one go.
//
// On iOS, navigator.share({ files }) opens the share sheet with a
// "Save N Images" action that drops every slide into Photos at once. Safari
// only allows share() during a user tap, so the PNGs are fetched ahead of
// time (prefetchSlides) and the tap itself just hands them over.

// "…/output/slides/2026-10-06/slide_01.png" → "2026-10-06_slide_01.png"
function fileNameFor(url: string, index: number): string {
  const parts = new URL(url, window.location.href).pathname.split("/").filter(Boolean);
  const name = parts[parts.length - 1] || `slide_${index + 1}.png`;
  const folder = parts[parts.length - 2];
  return (folder ? `${folder}_${name}` : name).replace(/[^A-Za-z0-9._-]/g, "_");
}

export async function prefetchSlides(urls: string[], signal?: AbortSignal): Promise<File[]> {
  return Promise.all(
    urls.map(async (url, i) => {
      const resp = await fetch(url, { signal });
      if (!resp.ok) throw new Error(`Slide ${i + 1} failed to load (HTTP ${resp.status})`);
      const blob = await resp.blob();
      return new File([blob], fileNameFor(url, i), { type: blob.type || "image/png" });
    }),
  );
}

// True when this browser can share image files (iOS/Android over HTTPS).
// False on plain-http LAN access and most desktop browsers.
export function canShareFiles(): boolean {
  if (typeof navigator === "undefined" || !navigator.share || !navigator.canShare) return false;
  try {
    const probe = new File([new Uint8Array(1)], "probe.png", { type: "image/png" });
    return navigator.canShare({ files: [probe] });
  } catch {
    return false;
  }
}

export type ShareOutcome = "shared" | "cancelled" | "needs-tap";

export async function shareSlides(files: File[]): Promise<ShareOutcome> {
  try {
    await navigator.share({ files });
    return "shared";
  } catch (err) {
    const name = err instanceof DOMException ? err.name : "";
    // User closed the share sheet without picking anything.
    if (name === "AbortError") return "cancelled";
    // The tap "expired" while files were still downloading — a second tap works.
    if (name === "NotAllowedError") return "needs-tap";
    throw err;
  }
}

// Desktop fallback: trigger one download per slide (the server sets
// Content-Disposition on ?download=1). Spaced out so browsers don't drop any.
export async function downloadSlides(urls: string[]): Promise<void> {
  for (const url of urls) {
    const a = document.createElement("a");
    a.href = slideDownloadUrl(url);
    a.download = "";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
}
