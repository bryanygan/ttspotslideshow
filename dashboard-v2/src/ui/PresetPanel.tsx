import type { RecapState } from "../lib/useRecap";
import { COUNTS } from "../lib/constants";
import { PRESETS } from "../lib/presets";

// Target-size selector + the six smart-selection presets. Shared by both
// options; applying a preset replaces the current selection.
export function PresetPanel({ r }: { r: RecapState }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold uppercase tracking-wider text-zinc-500">
            Target size
          </span>
          <span className="font-semibold text-violet-300">
            {r.quickSelectCount} tracks
          </span>
        </div>
        <div className="grid grid-cols-4 gap-1.5">
          {COUNTS.map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => r.setQuickSelectCount(n)}
              className={`rounded-lg border py-2 text-sm font-semibold transition-all ${
                r.quickSelectCount === n
                  ? "border-violet-500 bg-violet-500/15 text-violet-200"
                  : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            onClick={() => r.applyPreset(preset.id)}
            title={preset.hint}
            disabled={r.candidates.length === 0}
            className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-2.5 text-left text-sm font-semibold text-zinc-200 transition-colors hover:border-violet-500/60 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <span className="text-base leading-none">{preset.emoji}</span>
            <span className="truncate">{preset.label}</span>
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={r.clearSelection}
        disabled={r.selectedKeys.size === 0}
        className="rounded-xl border border-zinc-800 py-2 text-xs font-bold uppercase tracking-wider text-zinc-400 transition-colors hover:border-zinc-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        Clear selection
      </button>
    </div>
  );
}
