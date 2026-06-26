import type { RecapState } from "../lib/useRecap";
import { AlertIcon } from "./icons";

// Pre-generate stats: candidate total, picked count, 4-up slide math, and a
// nudge when the selection isn't a clean multiple of 4. Shared by both options.
export function Summary({ r }: { r: RecapState }) {
  const rows: Array<[string, string, string]> = [
    ["Candidates", String(r.candidates.length), "text-zinc-200"],
    ["Picked", String(r.selectedKeys.size), "text-violet-300"],
    [
      "Slides",
      r.leftover === 0
        ? `${r.slideCount}`
        : `${r.slideCount} (+${r.leftover} leftover)`,
      "text-fuchsia-300",
    ],
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2">
        {rows.map(([label, value, color]) => (
          <div
            key={label}
            className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-3 py-2.5 text-center"
          >
            <div className={`font-mono text-lg font-bold ${color}`}>{value}</div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              {label}
            </div>
          </div>
        ))}
      </div>

      {r.selectedKeys.size > 0 && r.leftover !== 0 && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-900/60 bg-amber-950/30 p-3 text-xs text-amber-300">
          <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Slides render 4-up. Add or remove tracks to reach a multiple of 4
            (4, 8, 12, 16) so none go to waste.
          </span>
        </div>
      )}
    </div>
  );
}
