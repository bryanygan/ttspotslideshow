import { useState } from "react";
import { useBidaily } from "../lib/useBidaily";
import type { BidailyEntry } from "../lib/types";
import { CopyButton } from "./CopyButton";

function fmtDate(iso: string): string {
  // iso is YYYY-MM-DD — render as a friendly label without timezone drift.
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

// The automated bi-daily pipeline, surfaced in the dashboard: run it on demand,
// watch progress, and browse the history of past dated slide sets.
export function BiDailyPanel({ apiBase, active }: { apiBase: string; active: boolean }) {
  const b = useBidaily(apiBase, active);
  const [open, setOpen] = useState<BidailyEntry | null>(null);

  const s = b.status;
  const running = !!s?.running;
  const lastLog = s?.log ?? [];

  let statusPill: { text: string; cls: string };
  if (running) {
    statusPill = { text: "Running…", cls: "border-violet-700/60 bg-violet-950/50 text-violet-300" };
  } else if (s?.ok === true) {
    statusPill = { text: "Last run: success", cls: "border-emerald-800/60 bg-emerald-950/40 text-emerald-300" };
  } else if (s?.ok === false) {
    statusPill = { text: "Last run: failed", cls: "border-rose-800/60 bg-rose-950/50 text-rose-300" };
  } else {
    statusPill = { text: "Idle", cls: "border-zinc-700 bg-zinc-900 text-zinc-400" };
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5 px-3 py-4 sm:px-4">
      <div>
        <h2 className="text-lg font-bold text-zinc-100">Bi-daily auto-slides</h2>
        <p className="mt-1 text-sm leading-relaxed text-zinc-400">
          Runs automatically every other day at 9am — pulls your newest plays and builds a fresh
          4-slide set with an AI caption. Trigger one now, or browse past sets below.
        </p>
      </div>

      {/* Status + run control */}
      <section className="flex flex-col gap-3 rounded-xl border border-zinc-800 bg-zinc-950/60 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusPill.cls}`}>
            {statusPill.text}
          </span>
          <button
            type="button"
            onClick={b.start}
            disabled={running || b.starting}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-violet-500 disabled:opacity-50"
          >
            {running ? "Running…" : b.starting ? "Starting…" : "Run now"}
          </button>
        </div>

        {b.error && <p className="text-xs text-rose-300">{b.error}</p>}

        {(running || lastLog.length > 0) && (
          <pre className="max-h-44 overflow-auto rounded-lg border border-zinc-800 bg-black/50 p-2 font-mono text-[11px] leading-relaxed text-zinc-300">
            {lastLog.length ? lastLog.join("\n") : "Waiting for output…"}
          </pre>
        )}
      </section>

      {/* History */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-200">
            Previous slides ({b.history.length})
          </h3>
          <button
            type="button"
            onClick={b.refreshHistory}
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-[11px] font-semibold text-zinc-300 hover:bg-zinc-800"
          >
            {b.historyLoading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {b.history.length === 0 && !b.historyLoading && (
          <p className="text-sm text-zinc-500">No bi-daily slide sets yet.</p>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {b.history.map((e) => (
            <button
              key={e.date}
              type="button"
              onClick={() => setOpen(e)}
              className="group flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-950/60 p-2.5 text-left transition-colors hover:border-violet-500/60"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-zinc-100">{fmtDate(e.date)}</span>
                <span className="text-[11px] text-zinc-500">{e.slide_count} slides</span>
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {e.slides.slice(0, 4).map((url, i) => (
                  <img
                    key={url}
                    src={`${apiBase}${url}`}
                    alt={`${e.date} slide ${i + 1}`}
                    loading="lazy"
                    className="w-full rounded-md border border-zinc-800"
                  />
                ))}
              </div>
              {e.caption && (
                <p className="line-clamp-2 text-[11px] leading-snug text-zinc-500">{e.caption}</p>
              )}
            </button>
          ))}
        </div>
      </section>

      {/* Expanded viewer */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4"
          onClick={() => setOpen(null)}
        >
          <div
            className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-t-2xl border border-zinc-800 bg-zinc-950 p-4 sm:rounded-2xl"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-bold text-zinc-100">{fmtDate(open.date)}</h3>
              <button
                type="button"
                onClick={() => setOpen(null)}
                className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs font-semibold text-zinc-300 hover:bg-zinc-800"
              >
                Close
              </button>
            </div>

            <span className="mb-2 block rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-2.5 py-1 text-center text-xs text-emerald-300">
              📱 Long-press a slide → Add to Photos
            </span>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {open.slides.map((url, i) => (
                <a
                  key={url}
                  href={`${apiBase}${url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex flex-col gap-1.5"
                >
                  <img
                    src={`${apiBase}${url}`}
                    alt={`Slide ${i + 1}`}
                    className="w-full rounded-xl border border-zinc-800"
                  />
                  <span className="text-center text-[11px] text-zinc-500">Slide {i + 1}</span>
                </a>
              ))}
            </div>

            {open.caption && (
              <div className="mt-3 flex flex-col gap-2 rounded-xl border border-violet-800/50 bg-violet-950/30 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-violet-400">
                    TikTok Caption
                  </span>
                  <CopyButton text={open.caption} />
                </div>
                <pre className="select-all whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-violet-100/90">
                  {open.caption}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
