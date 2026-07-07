import type { HealthState } from "../lib/useHealth";

// A slim status strip shown under the header. Silent when everything is fine.
// Turns the old cryptic blank/CORS failure into a clear, self-recovering state.
export function ConnectionBanner({ h }: { h: HealthState }) {
  const warnings = h.health?.warnings ?? [];
  const degraded = h.conn === "online" && h.health?.status === "degraded";
  const hasWarnings = h.conn === "online" && warnings.length > 0;

  // All good — render nothing.
  if (h.conn === "online" && !degraded && !hasWarnings) return null;

  if (h.conn === "offline") {
    return (
      <div className="flex flex-wrap items-center justify-center gap-2 border-b border-rose-800/60 bg-rose-950/60 px-3 py-1.5 text-center text-xs text-rose-200">
        <span>
          ⚠️ Can’t reach the backend server.
          {h.retryInSec != null ? ` Retrying in ${h.retryInSec}s…` : " Retrying…"}
        </span>
        <button
          type="button"
          onClick={h.retryNow}
          className="rounded-md border border-rose-700/70 bg-rose-900/50 px-2 py-0.5 font-semibold text-rose-100 hover:bg-rose-800/70"
        >
          Retry now
        </button>
      </div>
    );
  }

  if (h.conn === "connecting") {
    return (
      <div className="border-b border-zinc-800 bg-zinc-900/70 px-3 py-1.5 text-center text-xs text-zinc-400">
        Connecting to backend…
      </div>
    );
  }

  // Online but degraded (critical: db/disk) or with soft warnings (ollama/bidaily).
  const parts: string[] = [];
  const checks = h.health?.checks ?? {};
  if (!checks.db?.ok) parts.push("database error");
  if (!checks.disk?.ok) parts.push("low disk space");
  if (warnings.includes("ollama")) parts.push("caption model offline (captions use the fallback)");
  if (warnings.includes("bidaily")) {
    const age = checks.bidaily?.age_days;
    parts.push(
      typeof age === "number"
        ? `bi-daily slides are ${age} day${age === 1 ? "" : "s"} old`
        : "no bi-daily slides yet",
    );
  }
  const tone = degraded
    ? "border-rose-800/60 bg-rose-950/50 text-rose-200"
    : "border-amber-800/60 bg-amber-950/40 text-amber-200";

  return (
    <div className={`border-b ${tone} px-3 py-1.5 text-center text-xs`}>
      ⚠️ {parts.join(" · ") || "Some services need attention."}
    </div>
  );
}
