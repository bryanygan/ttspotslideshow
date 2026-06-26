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
  cover_pool?: string[];
}

export interface GenerateResult {
  summary: GenerateSummary;
  slides: string[];
}

export class MissingCoverError extends Error {
  missingCovers: Array<{ artist: string; title: string; track_key: string }>;
  constructor(message: string, missingCovers: any[]) {
    super(message);
    this.name = "MissingCoverError";
    this.missingCovers = missingCovers;
  }
}

export class UnconfirmedCoverError extends Error {
  /** Tracks that only have an iTunes fallback cover needing user confirmation. */
  unconfirmedCovers: Array<{ artist: string; title: string; track_key: string; itunes_url: string }>;
  constructor(unconfirmedCovers: any[]) {
    super(`iTunes cover confirmation required for ${unconfirmedCovers.length} track(s).`);
    this.name = "UnconfirmedCoverError";
    this.unconfirmedCovers = unconfirmedCovers;
  }
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
    if (err.error === "unconfirmed_covers" && Array.isArray(err.unconfirmed_covers)) {
      throw new UnconfirmedCoverError(err.unconfirmed_covers);
    }
    if (err.error === "Missing album cover art" && Array.isArray(err.missing_covers)) {
      throw new MissingCoverError(err.error, err.missing_covers);
    }
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

/**
 * Save a confirmed iTunes URL to the art-test DB so future generate calls
 * use it as a stored URL (skipping the iTunes-confirmation step).
 */
export async function saveItunesUrl(
  apiBase: string,
  track: { artist: string; title: string },
  itunesUrl: string,
): Promise<void> {
  const resp = await fetch(`${apiBase}/api/art-test/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artist: track.artist, title: track.title, album_art_url: itunesUrl }),
  });
  if (!resp.ok) throw new Error(`Failed to save artwork URL (${resp.statusText}).`);
}

export async function uploadOcrScreenshot(
  apiBase: string,
  file: File,
): Promise<Candidate[]> {
  const resp = await fetch(`${apiBase}/api/ocr`, {
    method: "POST",
    headers: {
      "Content-Type": file.type,
    },
    body: file,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `OCR failed (HTTP ${resp.status}).`);
  }
  const data = await resp.json();
  return data.tracks ?? [];
}
