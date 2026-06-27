import type { RecapState } from "../lib/useRecap";
import { COVER_THEMES, HOOK_PRESETS } from "../lib/constants";

// The TikTok cover + watermark form. Shared by both options (violet accent,
// zinc surfaces) since the divergent identity lives in the browse/nav, not the
// settings form.
const SUBTITLE_PRESETS = [
  "Last 7 Days",
  "Last 14 Days",
  "Last 30 Days",
  "Last 90 Days",
  "Last 6 Months",
  "Last 1 Year",
];

// The TikTok cover + watermark form. Shared by both options (violet accent,
// zinc surfaces) since the divergent identity lives in the browse/nav, not the
// settings form.
export function CoverControls({ r }: { r: RecapState }) {
  const inputClass =
    "w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/40";
  const selectClass =
    "w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-300 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/40";
  const labelClass =
    "text-[11px] font-semibold uppercase tracking-wider text-zinc-500";

  return (
    <div className="flex flex-col gap-5">
      <label className="flex cursor-pointer select-none items-center justify-between gap-3">
        <span className="text-sm font-medium text-zinc-200">Add a cover / hook slide</span>
        <input
          type="checkbox"
          checked={r.includeCover}
          disabled={r.coverOnly}
          onChange={(e) => r.setIncludeCover(e.target.checked)}
          className="h-5 w-5 shrink-0 accent-violet-600 disabled:opacity-40"
        />
      </label>

      <label className="flex cursor-pointer select-none items-center justify-between gap-3">
        <span className="text-sm font-medium text-zinc-200">Generate only cover slide</span>
        <input
          type="checkbox"
          checked={r.coverOnly}
          onChange={(e) => {
            r.setCoverOnly(e.target.checked);
            if (e.target.checked) {
              r.setIncludeCover(true);
            }
          }}
          className="h-5 w-5 shrink-0 accent-violet-600"
        />
      </label>

      {(r.includeCover || r.coverOnly) && (
        <div className="flex flex-col gap-5 border-l-2 border-violet-500/40 pl-4">
          <div className="flex flex-col gap-2">
            <span className={labelClass}>Hook text</span>
            <input
              type="text"
              value={r.coverTitle}
              onChange={(e) => r.setCoverTitle(e.target.value)}
              className={inputClass}
              placeholder="Blank (type custom text)"
            />
            <select
              value={HOOK_PRESETS.includes(r.coverTitle) ? r.coverTitle : ""}
              onChange={(e) => r.setCoverTitle(e.target.value)}
              className={selectClass}
            >
              <option value="">Custom / Blank</option>
              {HOOK_PRESETS.map((hook) => (
                <option key={hook} value={hook}>
                  {hook}
                </option>
              ))}
              <option value="WEEKLY RECAP">WEEKLY RECAP</option>
              <option value="MONTHLY RECAP">MONTHLY RECAP</option>
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <span className={labelClass}>Subtitle</span>
            <input
              type="text"
              value={r.coverSubtitle}
              onChange={(e) => r.setCoverSubtitle(e.target.value)}
              className={inputClass}
              placeholder="Blank (type custom subtitle)"
            />
            <select
              value={SUBTITLE_PRESETS.includes(r.coverSubtitle) ? r.coverSubtitle : ""}
              onChange={(e) => r.setCoverSubtitle(e.target.value)}
              className={selectClass}
            >
              <option value="">Custom / Blank</option>
              {SUBTITLE_PRESETS.map((sub) => (
                <option key={sub} value={sub}>
                  {sub}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <span className={labelClass}>Cover theme</span>
            <div className="grid grid-cols-2 gap-2">
              {COVER_THEMES.map((theme) => (
                <button
                  key={theme.value}
                  type="button"
                  onClick={() => r.setCoverTheme(theme.value)}
                  className={`flex items-center gap-2 rounded-lg border p-2 text-left text-xs font-medium transition-all ${
                    r.coverTheme === theme.value
                      ? "border-violet-500 bg-violet-500/10 text-white"
                      : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
                  }`}
                >
                  <span
                    className={`h-6 w-6 shrink-0 rounded-md bg-gradient-to-br ${theme.swatch}`}
                  />
                  <span className="truncate">{theme.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <span className={labelClass}>Cover Grid Size (Columns)</span>
            <div className="grid grid-cols-4 gap-2">
              {[3, 4, 5, 6].map((cols) => (
                <button
                  key={cols}
                  type="button"
                  onClick={() => r.setCoverColumns(cols)}
                  className={`rounded-lg border py-2 text-center text-xs font-semibold transition-all ${
                    r.coverColumns === cols
                      ? "border-violet-500 bg-violet-500/15 text-violet-200"
                      : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
                  }`}
                >
                  {cols} Cols
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <span className={labelClass}>Watermark / footer</span>
        <input
          type="text"
          value={r.watermark}
          onChange={(e) => r.setWatermark(e.target.value)}
          className={`${inputClass} font-mono`}
          placeholder="@username"
        />
      </div>

      <div className="flex flex-col gap-2">
        <span className={labelClass}>Grid Layout</span>
        <div className="grid grid-cols-3 gap-2">
          {(["2x2", "3x3", "4x4"] as const).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => r.setLayout(l)}
              className={`rounded-lg border py-2 text-center text-sm font-semibold transition-all ${
                r.layout === l
                  ? "border-violet-500 bg-violet-500/15 text-violet-200"
                  : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t border-zinc-800/80 pt-4 mt-2">
        <div className="flex items-center justify-between">
          <span className={labelClass}>Slide Dimensions</span>
          <label className="flex cursor-pointer select-none items-center gap-2">
            <span className="text-[11px] text-zinc-400">Lock Aspect Ratio</span>
            <input
              type="checkbox"
              checked={r.lockAspectRatio}
              onChange={r.toggleLockAspectRatio}
              className="h-4 w-4 rounded accent-violet-600"
            />
          </label>
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-zinc-400">Width</span>
            <span className="font-mono text-zinc-200">{r.slideWidth}px</span>
          </div>
          <input
            type="range"
            min={480}
            max={2160}
            step={10}
            value={r.slideWidth}
            onChange={(e) => r.setSlideWidth(parseInt(e.target.value))}
            className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-zinc-400">Height</span>
            <span className="font-mono text-zinc-200">{r.slideHeight}px</span>
          </div>
          <input
            type="range"
            min={480}
            max={3840}
            step={10}
            value={r.slideHeight}
            onChange={(e) => r.setSlideHeight(parseInt(e.target.value))}
            className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
          />
        </div>
      </div>
    </div>
  );
}
