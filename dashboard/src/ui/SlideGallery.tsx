import type { RecapState } from "../lib/useRecap";
import { CopyButton } from "./CopyButton";
import { SaveAllButton } from "./SaveAllButton";
import { SlideTile } from "./SlideTile";

// Rendered slides + save-to-Photos guidance, shown after a successful generate.
// Shared by both options.
export function SlideGallery({ r }: { r: RecapState }) {
  if (r.slideUrls.length === 0) return null;

  const caption = r.summary?.caption;
  const fullUrls = r.slideUrls.map((url) => `${r.apiBase}${url}`);

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-200">
        Your slides ({r.slideUrls.length})
      </h3>

      <SaveAllButton urls={fullUrls} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {fullUrls.map((src, i) => (
          <SlideTile key={src} src={src} index={i} />
        ))}
      </div>

      {caption && (
        <div className="flex flex-col gap-2 rounded-xl border border-violet-800/50 bg-violet-950/30 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-violet-400">
              TikTok Caption
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={r.regenerateCaption}
                disabled={r.regeneratingCaption}
                className="rounded-lg border border-violet-700/60 bg-violet-900/40 px-2.5 py-1.5 text-[11px] font-semibold text-violet-300 transition-colors hover:bg-violet-800/60 disabled:opacity-50"
              >
                {r.regeneratingCaption ? "Rerolling…" : "🔄 Regenerate"}
              </button>
              <CopyButton text={caption} />
            </div>
          </div>
          <pre
            className={`select-all whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-violet-100/90 transition-opacity ${
              r.regeneratingCaption ? "opacity-40" : ""
            }`}
          >
            {caption}
          </pre>
        </div>
      )}

      {r.summary && (
        <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/30 p-3 text-xs leading-relaxed text-emerald-200/90">
          Rendered <strong>{r.summary.slide_count}</strong> slide(s). Also saved on
          the host at:
          <div className="mt-1.5 select-all overflow-x-auto rounded bg-black/40 p-1.5 font-mono text-[11px] break-all">
            {r.summary.out_dir}
          </div>
        </div>
      )}
    </div>
  );
}
