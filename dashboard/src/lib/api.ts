import type { Candidate, GenerateSummary } from "./types";

// Resolve a possibly-relative album-art / override URL against the backend.
// Spotify URLs are absolute (http...); override URLs are server-relative.
export function resolveArt(apiBase: string, url: string): string {
  if (!url) return "";
  if (url.includes("mzstatic.com")) {
    const encoded = btoa(url);
    const proxied = `${apiBase}/api/art-proxy?url=${encodeURIComponent(encoded)}`;
    console.log(`[resolveArt] Proxying iTunes URL: "${url}" -> "${proxied}"`);
    return proxied;
  }
  return url.startsWith("http") ? url : `${apiBase}${url}`;
}

export async function fetchCandidates(
  apiBase: string,
  days: number,
  signal?: AbortSignal,
): Promise<Candidate[]> {
  const resp = await fetch(`${apiBase}/api/candidates?days=${days}`, { signal });
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
  layout?: "2x2" | "3x3" | "4x4";
  cover_only?: boolean;
  cover_columns?: number;
  cover_rows?: number;
  width?: number;
  height?: number;
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

export interface ProgressEvent {
  stage: string;
  progress: number;
  current: number;
  total: number;
  eta: number | null;
  detail: string;
}

export async function generateRecapStream(
  apiBase: string,
  payload: GeneratePayload,
  onProgress: (evt: ProgressEvent) => void,
): Promise<GenerateResult> {
  const resp = await fetch(`${apiBase}/api/generate-stream`, {
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

  const reader = resp.body?.getReader();
  if (!reader) {
    throw new Error("Response body is not readable.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    // Keep the last (possibly incomplete) line in the buffer
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const jsonStr = line.slice(6);
      let evt: any;
      try {
        evt = JSON.parse(jsonStr);
      } catch {
        continue;
      }

      if (evt.event === "complete") {
        return { summary: evt.summary, slides: evt.slides ?? [] };
      }
      if (evt.event === "error") {
        if (evt.type === "unconfirmed_covers") {
          throw new UnconfirmedCoverError(evt.unconfirmed_covers);
        }
        if (evt.type === "missing_covers") {
          throw new MissingCoverError("Missing album cover art", evt.missing_covers);
        }
        throw new Error(evt.message || "Generation failed.");
      }
      // Regular progress event
      onProgress({
        stage: evt.stage,
        progress: evt.progress,
        current: evt.current,
        total: evt.total,
        eta: evt.eta,
        detail: evt.detail,
      });
    }
  }

  throw new Error("Stream ended without a complete or error event.");
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
  const encodedUrl = btoa(itunesUrl);
  console.log(`[saveItunesUrl] Submitting confirm request for: "${track.artist} - ${track.title}". Original URL: "${itunesUrl}". Encoded: "${encodedUrl}"`);
  try {
    const resp = await fetch(`${apiBase}/api/track/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        artist: track.artist,
        title: track.title,
        album_art_url: encodedUrl,
        is_encoded: true
      }),
    });
    if (!resp.ok) {
      console.error(`[saveItunesUrl] Request failed with HTTP status ${resp.status}`);
      throw new Error(`Failed to save artwork URL (${resp.statusText}).`);
    }
    console.log(`[saveItunesUrl] Success for "${track.artist} - ${track.title}"`);
  } catch (err) {
    console.error(`[saveItunesUrl] Fetch error:`, err);
    throw err;
  }
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

export interface PlaylistParseResult {
  source: "spotify" | "lastfm";
  tracks: Candidate[];
}

// Parse a Spotify/Last.fm playlist link into selectable candidate tracks.
export async function parsePlaylist(
  apiBase: string,
  url: string,
): Promise<PlaylistParseResult> {
  const resp = await fetch(`${apiBase}/api/playlist/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `Couldn't parse playlist (HTTP ${resp.status}).`);
  }
  const data = await resp.json();
  return { source: data.source, tracks: data.tracks ?? [] };
}

// Search Spotify for tracks matching a free-text query.
export async function searchSpotify(
  apiBase: string,
  q: string,
): Promise<Candidate[]> {
  const resp = await fetch(`${apiBase}/api/search/spotify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `Spotify search failed (HTTP ${resp.status}).`);
  }
  const data = await resp.json();
  return data.tracks ?? [];
}

export interface SavePlaylistResult {
  playlist_id: string;
  url: string;
  added: number;
}

// Save selected tracks back to a new or existing Spotify playlist.
export async function savePlaylist(
  apiBase: string,
  tracks: Candidate[],
  name?: string,
  playlistId?: string,
): Promise<SavePlaylistResult> {
  const resp = await fetch(`${apiBase}/api/playlist/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tracks, name, playlist_id: playlistId }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `Couldn't save playlist (HTTP ${resp.status}).`);
  }
  return resp.json();
}

export interface LoggerRefreshResult {
  spotify_added: number;
  lastfm_added: number;
  total_plays: number;
  errors: string[];
}

// Ask the backend to pull the newest plays right now (Spotify recently-played
// + Last.fm scrobbles), so the candidate list can be refreshed on demand.
export async function refreshLogger(apiBase: string): Promise<LoggerRefreshResult> {
  const resp = await fetch(`${apiBase}/api/logger/refresh`, { method: "POST" });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || `Refresh failed (HTTP ${resp.status}).`);
  }
  return {
    spotify_added: data.spotify_added ?? 0,
    lastfm_added: data.lastfm_added ?? 0,
    total_plays: data.total_plays ?? 0,
    errors: data.errors ?? [],
  };
}

export interface RecapHistoryEntry {
  recap_id: string;
  date: string;
  slide_count: number;
  generated_at: number;
}

export async function fetchRecapHistory(
  apiBase: string,
): Promise<RecapHistoryEntry[]> {
  const resp = await fetch(`${apiBase}/api/recap-history`);
  if (!resp.ok) throw new Error(`Couldn't fetch recap history (HTTP ${resp.status}).`);
  const data = await resp.json();
  return data.history ?? [];
}

export async function fetchRecapSlides(
  apiBase: string,
  recapId: string,
): Promise<string[]> {
  const resp = await fetch(`${apiBase}/api/recap-history/${recapId}/slides`);
  if (!resp.ok) throw new Error(`Couldn't fetch recap slides (HTTP ${resp.status}).`);
  const data = await resp.json();
  return data.slides ?? [];
}
