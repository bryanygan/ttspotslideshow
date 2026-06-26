import type { Candidate } from "./types";
import { underratedScore } from "./types";

// A preset takes the full candidate pool + a target size and returns an ordered
// list of track_keys to select. All presets are pure so both UI options call
// the exact same logic.
export type PresetFn = (candidates: Candidate[], count: number) => string[];

function take(sorted: Candidate[], count: number): string[] {
  return sorted.slice(0, Math.min(count, sorted.length)).map((c) => c.track_key);
}

const byPlays = (a: Candidate, b: Candidate) =>
  b.play_count - a.play_count || b.last_played_unix - a.last_played_unix;

const byRecent = (a: Candidate, b: Candidate) =>
  b.last_played_unix - a.last_played_unix;

const byUnderrated = (a: Candidate, b: Candidate) =>
  underratedScore(b) - underratedScore(a) ||
  b.last_played_unix - a.last_played_unix;

export const topPlayed: PresetFn = (candidates, count) =>
  take([...candidates].sort(byPlays), count);

export const freshHits: PresetFn = (candidates, count) =>
  take([...candidates].sort(byRecent), count);

export const underrated: PresetFn = (candidates, count) =>
  take([...candidates].sort(byUnderrated), count);

export const randomMix: PresetFn = (candidates, count) =>
  take([...candidates].sort(() => 0.5 - Math.random()), count);

export const noRepeats: PresetFn = (candidates, count) => {
  // Filter out tracks recently featured, then sort by plays
  const fresh = candidates.filter((c) => !c.recently_featured);
  return take(fresh.sort(byPlays), count);
};

// Group by a field (artist / genre bucket), pick the highest-play group first,
// then top up from the next groups until we hit the target count.
function topGroupFill(
  candidates: Candidate[],
  count: number,
  field: "artist" | "primary_bucket",
): string[] {
  const groupPlays: Record<string, number> = {};
  for (const c of candidates) {
    groupPlays[c[field]] = (groupPlays[c[field]] || 0) + c.play_count;
  }
  const groupsByPlays = Object.keys(groupPlays).sort(
    (a, b) => groupPlays[b] - groupPlays[a],
  );
  if (groupsByPlays.length === 0) return [];

  const keys: string[] = [];
  const seen = new Set<string>();
  for (const group of groupsByPlays) {
    if (keys.length >= count) break;
    const tracks = candidates
      .filter((c) => c[field] === group)
      .sort(byPlays);
    for (const t of tracks) {
      if (keys.length >= count) break;
      if (seen.has(t.track_key)) continue;
      seen.add(t.track_key);
      keys.push(t.track_key);
    }
  }
  return keys;
}

export const sameArtist: PresetFn = (candidates, count) =>
  topGroupFill(candidates, count, "artist");

export const sameGenre: PresetFn = (candidates, count) =>
  topGroupFill(candidates, count, "primary_bucket");

export interface PresetDef {
  id: string;
  label: string;
  emoji: string;
  hint: string;
  fn: PresetFn;
}

export const PRESETS: PresetDef[] = [
  { id: "top", label: "Top Played", emoji: "🔥", hint: "Most-played tracks in the window", fn: topPlayed },
  { id: "fresh", label: "Fresh Hits", emoji: "⏱️", hint: "Most recently played", fn: freshHits },
  { id: "artist", label: "Artist Vibe", emoji: "🎤", hint: "Built around your top artist", fn: sameArtist },
  { id: "genre", label: "Genre Vibe", emoji: "💿", hint: "Built around your top genre", fn: sameGenre },
  { id: "underrated", label: "Underrated", emoji: "💎", hint: "High plays, low global popularity", fn: underrated },
  { id: "random", label: "Random Mix", emoji: "🔀", hint: "A random handful from the pool", fn: randomMix },
  { id: "norepeats", label: "No Repeats", emoji: "🚫", hint: "Skip tracks featured in the last 14 days", fn: noRepeats },
];
