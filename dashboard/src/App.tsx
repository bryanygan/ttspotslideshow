import { useEffect, useState } from "react";
import { useRecap } from "./lib/useRecap";
import { useHealth } from "./lib/useHealth";
import { PocketDJ } from "./options/pocket/PocketDJ";
import { OcrScanner } from "./options/pocket/OcrScanner";
import { PlaylistImporter } from "./options/pocket/PlaylistImporter";
import { BiDailyPanel } from "./ui/BiDailyPanel";
import { StatusPanel } from "./ui/StatusPanel";
import { ConnectionBanner } from "./ui/ConnectionBanner";
import { Sheet } from "./ui/Sheet";
import { GearIcon, MusicIcon } from "./ui/icons";

// App shell: one useRecap() instance plus a slim top bar (brand + settings).
function App() {
  const r = useRecap();
  const health = useHealth(r.apiBase);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tempApiBase, setTempApiBase] = useState(r.apiBase);
  const [viewMode, setViewMode] = useState<"picker" | "ocr" | "playlist" | "bidaily" | "status">("picker");

  // Sync tempApiBase when the settings sheet is opened
  useEffect(() => {
    if (settingsOpen) {
      setTempApiBase(r.apiBase);
    }
  }, [settingsOpen, r.apiBase]);

  return (
    <div>
      <header className="fixed inset-x-0 top-0 z-50 h-11 border-b border-white/10 bg-black/85 backdrop-blur">
        <div className="mx-auto flex h-full max-w-3xl items-center justify-between gap-2 px-3 sm:px-4">
          <span className="flex shrink-0 items-center gap-2 font-display text-sm font-bold tracking-wide text-white">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-tr from-violet-600 to-fuchsia-500 text-white">
              <MusicIcon className="h-4 w-4" />
            </span>
            {/* Brand text costs too much width on phones — icon carries it there. */}
            <span className="hidden md:inline">Weekly Recap</span>
          </span>

          {/* View switcher tabs */}
          <div className="flex min-w-0 bg-zinc-900 border border-zinc-800 rounded-lg p-0.5 text-xs font-semibold">
            {(
              [
                { id: "picker", short: "Picker", full: "Recap Picker" },
                { id: "bidaily", short: "Auto", full: "Bi-daily" },
                { id: "ocr", short: "Scan", full: "Screenshot" },
                { id: "playlist", short: "Playlist", full: "Playlist" },
                { id: "status", short: "Status", full: "System Status" },
              ] as const
            ).map(({ id, short, full }) => (
              <button
                key={id}
                onClick={() => setViewMode(id)}
                className={`px-2.5 py-1 sm:px-3 rounded-md whitespace-nowrap transition-all cursor-pointer ${
                  viewMode === id
                    ? "bg-violet-600 text-white shadow"
                    : "text-zinc-400 hover:text-zinc-100"
                }`}
              >
                <span className="sm:hidden">{short}</span>
                <span className="hidden sm:inline">{full}</span>
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Settings"
            className="shrink-0 rounded-full p-1.5 text-zinc-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            <GearIcon className="h-5 w-5" />
          </button>
        </div>
      </header>

      <div className="pt-11">
        <div className="sticky top-11 z-40">
          <ConnectionBanner h={health} />
        </div>
        {viewMode === "picker" && <PocketDJ r={r} />}
        {viewMode === "bidaily" && (
          <BiDailyPanel apiBase={r.apiBase} active={viewMode === "bidaily"} />
        )}
        {viewMode === "ocr" && <OcrScanner r={r} />}
        {viewMode === "playlist" && <PlaylistImporter r={r} />}
        {viewMode === "status" && <StatusPanel apiBase={r.apiBase} />}
      </div>

      <Sheet
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        title="Settings"
        panelClass="rounded-t-2xl border border-zinc-800 bg-zinc-950 text-zinc-100"
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Backend API
            </span>
            <input
              type="text"
              value={tempApiBase}
              onChange={(e) => setTempApiBase(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  r.setApiBase(tempApiBase);
                }
              }}
              placeholder="http://localhost:8000"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
            />
            <p className="text-xs leading-relaxed text-zinc-500">
              Point this at your running <code className="text-zinc-300">dashboard_server.py</code>.
              Default is <code className="text-zinc-300">http://localhost:8000</code>. Saved on this
              device.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              r.setApiBase(tempApiBase);
              setSettingsOpen(false);
            }}
            className="rounded-lg bg-violet-600 py-2.5 text-sm font-bold text-white transition-colors hover:bg-violet-500"
          >
            Reload data
          </button>
        </div>
      </Sheet>
    </div>
  );
}

export default App;
