import { useEffect, useState } from "react";
import { useRecap } from "./lib/useRecap";
import { PocketDJ } from "./options/pocket/PocketDJ";
import { ArtSandbox } from "./options/pocket/ArtSandbox";
import { OcrScanner } from "./options/pocket/OcrScanner";
import { Sheet } from "./ui/Sheet";
import { GearIcon, MusicIcon } from "./ui/icons";

// App shell: one useRecap() instance plus a slim top bar (brand + settings).
function App() {
  const r = useRecap();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tempApiBase, setTempApiBase] = useState(r.apiBase);
  const [viewMode, setViewMode] = useState<"picker" | "art-test" | "ocr">("picker");

  // Sync tempApiBase when the settings sheet is opened
  useEffect(() => {
    if (settingsOpen) {
      setTempApiBase(r.apiBase);
    }
  }, [settingsOpen, r.apiBase]);

  return (
    <div>
      <header className="fixed inset-x-0 top-0 z-50 h-11 border-b border-white/10 bg-black/85 backdrop-blur">
        <div className="mx-auto flex h-full max-w-3xl items-center justify-between px-4">
          <span className="flex items-center gap-2 font-display text-sm font-bold tracking-wide text-white">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-tr from-violet-600 to-fuchsia-500 text-white">
              <MusicIcon className="h-4 w-4" />
            </span>
            Weekly Recap
          </span>

          {/* View switcher tabs */}
          <div className="flex bg-zinc-900 border border-zinc-800 rounded-lg p-0.5 text-xs font-semibold">
            <button
              onClick={() => setViewMode("picker")}
              className={`px-3 py-1 rounded-md transition-all cursor-pointer ${
                viewMode === "picker"
                  ? "bg-violet-600 text-white shadow"
                  : "text-zinc-400 hover:text-zinc-100"
              }`}
            >
              Recap Picker
            </button>
            <button
              onClick={() => setViewMode("ocr")}
              className={`px-3 py-1 rounded-md transition-all cursor-pointer ${
                viewMode === "ocr"
                  ? "bg-violet-600 text-white shadow"
                  : "text-zinc-400 hover:text-zinc-100"
              }`}
            >
              Screenshot
            </button>
            <button
              onClick={() => setViewMode("art-test")}
              className={`px-3 py-1 rounded-md transition-all cursor-pointer ${
                viewMode === "art-test"
                  ? "bg-violet-600 text-white shadow"
                  : "text-zinc-400 hover:text-zinc-100"
              }`}
            >
              Art Sandbox
            </button>
          </div>

          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Settings"
            className="rounded-full p-1.5 text-zinc-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            <GearIcon className="h-5 w-5" />
          </button>
        </div>
      </header>

      <div className="pt-11">
        {viewMode === "picker" ? <PocketDJ r={r} /> : viewMode === "ocr" ? <OcrScanner r={r} /> : <ArtSandbox apiBase={r.apiBase} />}
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
              r.refetch();
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
