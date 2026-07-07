import { useState } from "react";
import type { RecapState } from "../lib/useRecap";

// Rendered slides + save-to-Photos guidance, shown after a successful generate.
// Shared by both options.
export function SlideGallery({ r }: { r: RecapState }) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  if (r.slideUrls.length === 0) return null;

  const caption = r.summary?.caption;

  async function handleCopy() {
    if (!caption) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(caption);
      } else {
        // Fallback for non-secure contexts (e.g. http:// over LAN on a phone),
        // where navigator.clipboard is unavailable.
        const ta = document.createElement("textarea");
        ta.value = caption;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("copy command failed");
      }
      setCopyFailed(false);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Last resort: prompt the user to long-press the (select-all) text.
      setCopyFailed(true);
      setTimeout(() => setCopyFailed(false), 4000);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-200">
          Your slides ({r.slideUrls.length})
        </h3>
        <span className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-2.5 py-1 text-xs text-emerald-300">
          📱 Long-press a slide → Add to Photos
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {r.slideUrls.map((url, i) => (
          <a
            key={url}
            href={`${r.apiBase}${url}`}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex flex-col gap-1.5"
          >
            <img
              src={`${r.apiBase}${url}`}
              alt={`Slide ${i + 1}`}
              className="w-full rounded-xl border border-zinc-800 transition-colors group-hover:border-violet-500/60"
            />
            <span className="text-center text-[11px] font-medium text-zinc-500">
              Slide {i + 1}
            </span>
          </a>
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
              <button
                type="button"
                onClick={handleCopy}
                className="rounded-lg border border-violet-700/60 bg-violet-900/40 px-2.5 py-1.5 text-[11px] font-semibold text-violet-300 transition-colors hover:bg-violet-800/60"
              >
                {copied ? "Copied!" : copyFailed ? "Long-press ↓" : "Copy"}
              </button>
            </div>
          </div>
          <pre
            className={`select-all whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-violet-100/90 transition-opacity ${
              r.regeneratingCaption ? "opacity-40" : ""
            }`}
          >
            {caption}
          </pre>
          {copyFailed && (
            <span className="text-[10px] text-violet-400/80">
              Auto-copy blocked here — long-press the text above to select and copy.
            </span>
          )}
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
