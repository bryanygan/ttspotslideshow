import { useState } from "react";
import type { RecapState } from "../../lib/useRecap";
import { WINDOWS, windowLabel } from "../../lib/constants";
import { CandidateTable } from "./CandidateTable";
import { ConsoleControls } from "./ConsoleControls";
import { SelectedTray } from "../../ui/SelectedTray";
import { SlideGallery } from "../../ui/SlideGallery";
import { ErrorBanner } from "../../ui/ErrorBanner";
import { Sheet } from "../../ui/Sheet";
import { ChevronRightIcon } from "../../ui/icons";

// Option B — "Console": dense, minimal, data-first. Two-pane on desktop; on
// mobile a single list with a persistent CLI-style command bar that opens a
// composer sheet.
export function Console({ r }: { r: RecapState }) {
  const [composerOpen, setComposerOpen] = useState(false);

  return (
    <div className="min-h-screen bg-zinc-950 pb-24 font-sans text-zinc-100 lg:pb-0">
      <Toolbar r={r} />

      <div className="mx-auto max-w-7xl px-4 py-5 lg:grid lg:grid-cols-[360px_1fr] lg:gap-6">
        {/* Desktop rail */}
        <aside className="hidden self-start lg:sticky lg:top-[6.5rem] lg:flex lg:max-h-[calc(100vh-7.5rem)] lg:flex-col lg:gap-6 lg:overflow-y-auto lg:pr-1">
          <ConsoleControls r={r} />
          {r.selectedTracks.length > 0 && (
            <div className="flex flex-col gap-3">
              <h3 className="font-mono text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                Order ({r.selectedTracks.length})
              </h3>
              <SelectedTray r={r} />
            </div>
          )}
        </aside>

        {/* Main */}
        <main className="flex flex-col gap-5">
          {r.error && <ErrorBanner message={r.error} />}
          <SlideGallery r={r} />
          <CandidateTable r={r} />
        </main>
      </div>

      {/* Mobile command bar */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-zinc-800 bg-zinc-950/90 pb-safe backdrop-blur lg:hidden">
        <div className="flex items-center gap-3 px-4 py-3">
          <div className="font-mono text-xs leading-tight">
            <div className="font-semibold text-zinc-100">{r.selectedKeys.size} selected</div>
            <div className="text-zinc-500">
              {r.slideCount} slide{r.slideCount !== 1 ? "s" : ""}
              {r.leftover ? ` · +${r.leftover}` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setComposerOpen(true)}
            className="ml-auto flex items-center gap-1.5 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-violet-500"
          >
            Compose <ChevronRightIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Mobile composer sheet */}
      <Sheet
        open={composerOpen}
        onClose={() => setComposerOpen(false)}
        title={<span className="font-mono uppercase tracking-wider">Compose recap</span>}
        panelClass="rounded-t-2xl border border-zinc-800 bg-zinc-950 text-zinc-100"
      >
        <div className="flex flex-col gap-6">
          {r.selectedTracks.length > 0 && (
            <div className="flex flex-col gap-3">
              <h3 className="font-mono text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                Order ({r.selectedTracks.length})
              </h3>
              <SelectedTray r={r} />
            </div>
          )}
          <ConsoleControls r={r} />
        </div>
      </Sheet>
    </div>
  );
}

function Toolbar({ r }: { r: RecapState }) {
  return (
    <div className="sticky top-11 z-30 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5">
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          {WINDOWS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => r.setDays(d)}
              className={`shrink-0 rounded-md border px-2.5 py-1 font-mono text-xs font-semibold transition-colors ${
                r.days === d
                  ? "border-violet-500 bg-violet-500/10 text-violet-200"
                  : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
              }`}
            >
              {windowLabel(d)}
            </button>
          ))}
        </div>

        <div className="ml-auto flex shrink-0 overflow-hidden rounded-md border border-zinc-800 text-xs font-semibold">
          {(["plays", "underrated"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => r.setSortBy(s)}
              className={`px-3 py-1 capitalize transition-colors ${
                r.sortBy === s ? "bg-violet-600 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {s === "underrated" ? "Rated" : s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
