import { useState } from "react";
import type { RecapState } from "../lib/useRecap";
import { PRESETS } from "../lib/presets";

// Target-size selector + the six smart-selection presets. Shared by both
// options; applying a preset replaces the current selection.
export function PresetPanel({ r }: { r: RecapState }) {
  const [customRaw, setCustomRaw] = useState("");

  const layoutCounts = r.layout === "3x3"
    ? [9, 18, 27, 36]
    : r.layout === "4x4"
    ? [16, 32, 48, 64]
    : [12, 16, 20, 24]; // 2x2

  const step = r.layout === "3x3" ? 9 : (r.layout === "4x4" ? 16 : 4);
  const isCustom = !layoutCounts.includes(r.quickSelectCount);

  function commitCustom(raw: string) {
    const n = parseInt(raw, 10);
    if (n > 0) r.setQuickSelectCount(n);
    setCustomRaw("");
  }

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
        <div className="grid grid-cols-5 gap-1.5">
          {layoutCounts.map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => { r.setQuickSelectCount(n); setCustomRaw(""); }}
              className={`rounded-lg border py-2 text-sm font-semibold transition-all ${
                r.quickSelectCount === n
                  ? "border-violet-500 bg-violet-500/15 text-violet-200"
                  : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
              }`}
            >
              {n}
            </button>
          ))}
          <input
            type="number"
            min={step}
            step={step}
            value={customRaw}
            onChange={(e) => setCustomRaw(e.target.value)}
            onBlur={(e) => commitCustom(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") commitCustom((e.target as HTMLInputElement).value); }}
            placeholder={isCustom ? String(r.quickSelectCount) : "…"}
            className={`rounded-lg border py-2 text-center text-sm font-semibold transition-all focus:outline-none ${
              isCustom
                ? "border-violet-500 bg-violet-500/15 text-violet-200 placeholder:text-violet-300"
                : "border-zinc-800 bg-transparent text-zinc-400 placeholder:text-zinc-600 focus:border-zinc-600"
            }`}
          />
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
