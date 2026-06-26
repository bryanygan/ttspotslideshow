import type { ReactNode } from "react";
import type { RecapState } from "../../lib/useRecap";
import { PresetPanel } from "../../ui/PresetPanel";
import { CoverControls } from "../../ui/CoverControls";
import { Summary } from "../../ui/Summary";
import { Spinner } from "../../ui/Spinner";
import { ChevronRightIcon } from "../../ui/icons";

// A labelled section with a monospaced eyebrow — the Console identity device.
function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="font-mono text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
        {label}
      </h3>
      {children}
    </section>
  );
}

// Presets + cover + summary + generate. Used both in the desktop rail and the
// mobile composer sheet so the two stay in lockstep.
export function ConsoleControls({ r }: { r: RecapState }) {
  const canGenerate = r.selectedKeys.size > 0 && !r.generating;
  return (
    <div className="flex flex-col gap-6">
      <Section label="Smart selection">
        <PresetPanel r={r} />
      </Section>

      <div className="h-px bg-zinc-800" />

      <Section label="Cover & branding">
        <CoverControls r={r} />
      </Section>

      <div className="h-px bg-zinc-800" />

      <Section label="Summary">
        <Summary r={r} />
      </Section>

      <button
        type="button"
        onClick={r.generate}
        disabled={!canGenerate}
        className={`flex items-center justify-center gap-2 rounded-lg py-3 text-sm font-bold transition-colors ${
          canGenerate
            ? "bg-violet-600 text-white hover:bg-violet-500"
            : "cursor-not-allowed bg-zinc-800 text-zinc-600"
        }`}
      >
        {r.generating ? (
          <>
            <Spinner className="h-4 w-4" /> Generating…
          </>
        ) : (
          <>
            Generate slides <ChevronRightIcon className="h-4 w-4" />
          </>
        )}
      </button>
    </div>
  );
}
