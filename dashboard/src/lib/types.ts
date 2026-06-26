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
}

export type SortBy = "plays" | "underrated";

// Shape of summary returned by POST /api/generate.
export interface GenerateSummary {
  slide_count: number;
  out_dir: string;
  [key: string]: unknown;
}

// Underrated = personal plays relative to global popularity. Popularity is
// clamped to >= 1 so a 0-popularity track doesn't divide by zero.
export function underratedScore(c: Candidate): number {
  return c.play_count / (c.popularity || 1);
}
