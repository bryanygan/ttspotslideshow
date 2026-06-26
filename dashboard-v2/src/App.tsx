import { useState } from "react";
import { useRecap } from "./lib/useRecap";
import { PocketDJ } from "./options/pocket/PocketDJ";
import { Console } from "./options/console/Console";
import { Sheet } from "./ui/Sheet";
import { GearIcon } from "./ui/icons";

type Variant = "pocket" | "console";

const VARIANT_KEY = "dashv2_variant";

// App shell: one useRecap() instance shared by both options (so picks survive
// the A/B toggle), plus a slim comparison bar. This bar is the only "extra"
// chrome — once a direction is chosen, the winning option ships on its own.
function App() {
  const r = useRecap();
  const [variant, setVariant] = useState<Variant>(
    () => (localStorage.getItem(VARIANT_KEY) as Variant) || "pocket",
  );
  const [settingsOpen, setSettingsOpen] = useState(false);

  const choose = (v: Variant) => {
    setVariant(v);
    localStorage.setItem(VARIANT_KEY, v);
  };

  return (
    <div>
      <header className="fixed inset-x-0 top-0 z-50 h-11 border-b border-white/10 bg-black/85 backdrop-blur">
        <div className="relative mx-auto flex h-full max-w-7xl items-center justify-between px-3">
          <span className="flex items-center gap-2 font-mono text-xs font-semibold tracking-wide text-zinc-400">
            <span className="h-2 w-2 rounded-full bg-violet-500" />
            RECAP STUDIO
          </span>

          {/* A/B toggle — absolutely centered so it reads as a meta control. */}
          <div className="absolute left-1/2 flex -translate-x-1/2 overflow-hidden rounded-full border border-white/10 bg-white/5 text-xs font-bold">
            <button
              type="button"
              onClick={() => choose("pocket")}
              className={`px-3 py-1 transition-colors ${
                variant === "pocket" ? "bg-violet-600 text-white" : "text-zinc-400 hover:text-white"
              }`}
            >
              A · Pocket
            </button>
            <button
              type="button"
              onClick={() => choose("console")}
              className={`px-3 py-1 transition-colors ${
                variant === "console" ? "bg-violet-600 text-white" : "text-zinc-400 hover:text-white"
              }`}
            >
              B · Console
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
        {variant === "pocket" ? <PocketDJ r={r} /> : <Console r={r} />}
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
              value={r.apiBase}
              onChange={(e) => r.setApiBase(e.target.value)}
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
