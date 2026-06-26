import type { RecapState } from "../lib/useRecap";
import { AlbumArt } from "./AlbumArt";
import {
  ChevronUpIcon,
  ChevronDownIcon,
  ShuffleIcon,
  CloseIcon,
} from "./icons";

// The ordered list of picked tracks with reorder (up/down), swap, random
// replace, and remove. Order here becomes the slide order. Shared by both
// options.
export function SelectedTray({ r }: { r: RecapState }) {
  if (r.selectedTracks.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-center text-sm text-zinc-500">
        No tracks picked yet. Tap songs to build your slideshow, or use a smart
        preset.
      </div>
    );
  }

  const swapPool = r.candidates.filter((c) => !r.selectedKeys.has(c.track_key));

  return (
    <div className="flex flex-col gap-2.5">
      {r.selectedTracks.map((track, index) => (
        <div
          key={track.track_key}
          className="flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-900/50 p-2.5"
        >
          <div className="flex items-center gap-2.5">
            {/* Reorder buttons */}
            <div className="flex shrink-0 flex-col">
              <button
                type="button"
                onClick={() => r.moveSelected(track.track_key, -1)}
                disabled={index === 0}
                aria-label="Move up"
                className="rounded p-0.5 text-zinc-500 transition-colors hover:text-violet-300 disabled:opacity-25"
              >
                <ChevronUpIcon className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => r.moveSelected(track.track_key, 1)}
                disabled={index === r.selectedTracks.length - 1}
                aria-label="Move down"
                className="rounded p-0.5 text-zinc-500 transition-colors hover:text-violet-300 disabled:opacity-25"
              >
                <ChevronDownIcon className="h-4 w-4" />
              </button>
            </div>

            <span className="w-5 shrink-0 text-right font-mono text-xs font-semibold text-zinc-600">
              {index + 1}
            </span>

            <AlbumArt apiBase={r.apiBase} track={track} className="h-9 w-9" rounded="rounded-md" />

            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-white" title={track.title}>
                {track.title}
              </div>
              <div className="truncate text-xs text-zinc-400" title={track.artist}>
                {track.artist}
              </div>
            </div>

            <button
              type="button"
              onClick={() => r.toggleSelect(track.track_key)}
              aria-label="Remove track"
              className="shrink-0 rounded-lg p-1.5 text-zinc-500 transition-colors hover:bg-rose-500/10 hover:text-rose-400"
            >
              <CloseIcon className="h-4 w-4" />
            </button>
          </div>

          <div className="flex items-center gap-2 border-t border-zinc-800/60 pt-2">
            <select
              value=""
              onChange={(e) => {
                if (e.target.value) r.swapSelected(track.track_key, e.target.value);
              }}
              className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 focus:border-violet-500 focus:outline-none"
            >
              <option value="" disabled>
                Swap for…
              </option>
              {swapPool.map((c) => (
                <option key={c.track_key} value={c.track_key}>
                  {c.artist} — {c.title}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => r.replaceWithRandom(track.track_key)}
              className="flex shrink-0 items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 text-xs font-semibold text-zinc-300 transition-colors hover:border-violet-500/60 hover:text-white"
              title="Replace with a random track"
            >
              <ShuffleIcon className="h-3.5 w-3.5" />
              Random
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
