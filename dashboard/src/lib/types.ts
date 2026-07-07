// One track in the candidate pool, as returned by GET /api/candidates.
export interface Candidate {
  track_key: string;
  track_id: string;
  title: string;
  artist: string;
  album_art_url: string;
  play_count: number;
  last_played_unix: number;
  primary_bucket: string;
  popularity: number;
  last_featured: string | null;
  recently_featured: boolean;
  times_featured: number;
}

export type SortBy = "plays" | "underrated";

// Shape of summary returned by POST /api/generate.
export interface GenerateSummary {
  slide_count: number;
  out_dir: string;
  caption?: string;
  [key: string]: unknown;
}

// Underrated = personal plays relative to global popularity. Popularity is
// clamped to >= 1 so a 0-popularity track doesn't divide by zero.
export function underratedScore(c: Candidate): number {
  return c.play_count / (c.popularity || 1);
}

// GET /api/health — backend subsystem status for the connection monitor.
export interface HealthCheck {
  ok: boolean;
  error?: string;
  [key: string]: unknown;
}
export interface Health {
  status: "ok" | "degraded";
  warnings: string[];
  checks: Record<string, HealthCheck>;
}

// GET /api/bidaily/status — current/last automated run.
export interface BidailyStatus {
  running: boolean;
  started_at: number | null;
  finished_at: number | null;
  ok: boolean | null;
  error: string | null;
  log: string[];
}

// GET /api/bidaily/history — one past dated slide set.
export interface BidailyEntry {
  date: string;
  slide_count: number;
  generated_at: number;
  caption: string | null;
  slides: string[];
}
