import type { Candidate, GenerateSummary } from "./types";

// Resolve a possibly-relative album-art / override URL against the backend.
// Spotify URLs are absolute (http...); override URLs are server-relative.
export function resolveArt(apiBase: string, url: string): string {
  if (!url) return "";
  return url.startsWith("http") ? url : `${apiBase}${url}`;
}

export async function fetchCandidates(
  apiBase: string,
  days: number,
): Promise<Candidate[]> {
  const resp = await fetch(`${apiBase}/api/candidates?days=${days}`);
  if (!resp.ok) throw new Error(`Couldn't reach the backend (HTTP ${resp.status}).`);
  const data = await resp.json();
  return data.candidates ?? [];
}

export interface GeneratePayload {
  tracks: Candidate[];
  cover_title: string | null;
  cover_subtitle: string | null;
  cover_theme: string | null;
  watermark: string | null;
}

export interface GenerateResult {
  summary: GenerateSummary;
  slides: string[];
}

export async function generateRecap(
  apiBase: string,
  payload: GeneratePayload,
): Promise<GenerateResult> {
  const resp = await fetch(`${apiBase}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `Generation failed (HTTP ${resp.status}).`);
  }
  const data = await resp.json();
  return { summary: data.summary, slides: data.slides ?? [] };
}

// Upload a replacement cover for one track. The backend keys the override on
// artist + title via headers and stores the raw image body.
export async function uploadArt(
  apiBase: string,
  track: Candidate,
  file: File,
): Promise<{ url: string }> {
  const resp = await fetch(`${apiBase}/api/overrides/upload`, {
    method: "POST",
    headers: {
      "Content-Type": file.type,
      "X-Artist": encodeURIComponent(track.artist),
      "X-Title": encodeURIComponent(track.title),
    },
    body: file,
  });
  if (!resp.ok) throw new Error(`Upload failed (${resp.statusText}).`);
  const data = await resp.json();
  return { url: data.url };
}
