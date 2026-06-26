import type { RecapState } from "../../lib/useRecap";
import { AlbumArt } from "../../ui/AlbumArt";
import { MusicIcon } from "../../ui/icons";
import { windowLabel } from "../../lib/constants";
import { underratedScore } from "../../lib/types";

// Dense, data-first candidate list. Row click toggles selection; tapping the
// art replaces the cover (AlbumArt stops propagation). Metrics are monospaced.
export function CandidateTable({ r }: { r: RecapState }) {
  if (r.loading) {
    return (
      <div className="divide-y divide-zinc-800 overflow-hidden rounded-xl border border-zinc-800">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex animate-pulse items-center gap-3 px-3 py-3">
            <div className="h-10 w-10 rounded bg-zinc-800" />
            <div className="flex-1">
              <div className="h-3 w-1/3 rounded bg-zinc-800" />
              <div className="mt-1.5 h-2.5 w-1/4 rounded bg-zinc-800" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (r.sortedCandidates.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-zinc-800 px-6 py-16 text-center">
        <MusicIcon className="h-8 w-8 text-zinc-600" />
        <div className="font-semibold text-zinc-300">No tracks logged</div>
        <p className="max-w-xs text-sm text-zinc-500">
          Nothing in the last {windowLabel(r.days)}. Widen the window in the
          toolbar above.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800">
      {/* Column header — desktop only. */}
      <div className="hidden grid-cols-[auto_1fr_8rem_4rem_9rem] items-center gap-3 border-b border-zinc-800 bg-zinc-900/60 px-3 py-2 font-mono text-[10px] font-semibold uppercase tracking-wider text-zinc-500 sm:grid">
        <span className="w-5" />
        <span>Track</span>
        <span>Genre</span>
        <span className="text-right">Plays</span>
        <span>Popularity</span>
      </div>

      <div className="max-h-[calc(100vh-16rem)] divide-y divide-zinc-800 overflow-y-auto">
        {r.sortedCandidates.map((track) => {
          const selected = r.isSelected(track.track_key);
          return (
            <div
              key={track.track_key}
              role="button"
              tabIndex={0}
              onClick={() => r.toggleSelect(track.track_key)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  r.toggleSelect(track.track_key);
                }
              }}
              className={`grid cursor-pointer grid-cols-[auto_1fr] items-center gap-3 px-3 py-2.5 transition-colors hover:bg-zinc-900 sm:grid-cols-[auto_1fr_8rem_4rem_9rem] ${
                selected ? "bg-violet-500/[0.07]" : ""
              }`}
            >
              <input
                type="checkbox"
                checked={selected}
                onChange={() => r.toggleSelect(track.track_key)}
                onClick={(e) => e.stopPropagation()}
                className="h-4 w-4 shrink-0 accent-violet-600"
              />

              <div className="flex min-w-0 items-center gap-3">
                <AlbumArt
                  apiBase={r.apiBase}
                  track={track}
                  className="h-10 w-10"
                  rounded="rounded-md"
                  onUpload={(file) => r.uploadArtFor(track, file)}
                />
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-white" title={track.title}>
                    {track.title}
                  </div>
                  <div className="truncate text-xs text-zinc-400" title={track.artist}>
                    {track.artist}
                  </div>
                  {/* Mobile-only inline metrics. */}
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] text-zinc-500 sm:hidden">
                    <span className="text-zinc-300">{track.play_count} plays</span>
                    <span>· {track.primary_bucket}</span>
                    <span>· pop {track.popularity}</span>
                    {r.sortBy === "underrated" && (
                      <span className="text-violet-400">· {underratedScore(track).toFixed(1)}×</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Desktop columns. */}
              <div className="hidden sm:block">
                <span className="inline-block max-w-full truncate rounded border border-zinc-700 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-zinc-300">
                  {track.primary_bucket}
                </span>
              </div>
              <div className="hidden text-right font-mono text-sm font-semibold text-zinc-200 sm:block">
                {track.play_count}
              </div>
              <div className="hidden flex-col gap-1 sm:flex">
                <div className="flex items-center justify-between font-mono text-[10px] text-zinc-500">
                  <span>{track.popularity}</span>
                  {r.sortBy === "underrated" && (
                    <span className="font-semibold text-violet-400">
                      {underratedScore(track).toFixed(1)}×
                    </span>
                  )}
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className="h-full rounded-full bg-violet-500"
                    style={{ width: `${track.popularity}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
