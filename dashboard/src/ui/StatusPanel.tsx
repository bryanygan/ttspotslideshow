import { useEffect, useState, useRef } from "react";
import { Spinner } from "./Spinner";

interface ServiceStatus {
  [key: string]: string;
}

interface TaskInfo {
  next_run: string | null;
  status: string;
}

interface TasksStatus {
  [key: string]: TaskInfo;
}

interface SystemStatusData {
  uptime: number;
  services: ServiceStatus;
  tasks: TasksStatus;
  logs: string[];
}

interface LogData {
  name: string;
  lines: string[];
}

interface StatusPanelProps {
  apiBase: string;
}

export function StatusPanel({ apiBase }: StatusPanelProps) {
  const [status, setStatus] = useState<SystemStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedLog, setSelectedLog] = useState<string>("watchdog");
  const [logData, setLogData] = useState<LogData | null>(null);
  const [loadingLog, setLoadingLog] = useState(false);
  const [logFilter, setLogFilter] = useState("");
  const [autoRefreshLogs, setAutoRefreshLogs] = useState(true);

  const logEndRef = useRef<HTMLDivElement | null>(null);

  // Fetch general system status
  const fetchStatus = async () => {
    try {
      const res = await fetch(`${apiBase}/api/system-status`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      setStatus(data);
      setError(null);
    } catch (err: unknown) {
      console.error(err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  // Fetch selected log
  const fetchLog = async (logName: string) => {
    setLoadingLog(true);
    try {
      const res = await fetch(`${apiBase}/api/logs?name=${logName}`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      setLogData(data);
    } catch (err: unknown) {
      console.error(err);
    } finally {
      setLoadingLog(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000); // refresh status every 15s
    return () => clearInterval(interval);
  }, [apiBase]);

  useEffect(() => {
    fetchLog(selectedLog);
  }, [selectedLog, apiBase]);

  // Auto-refresh logs every 5 seconds if enabled
  useEffect(() => {
    if (!autoRefreshLogs) return;
    const interval = setInterval(() => {
      fetchLog(selectedLog);
    }, 5000);
    return () => clearInterval(interval);
  }, [selectedLog, autoRefreshLogs, apiBase]);

  // Scroll to bottom of logs when log data changes
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logData?.lines]);

  const formatUptime = (seconds: number) => {
    const d = Math.floor(seconds / (3600 * 24));
    const h = Math.floor((seconds % (3600 * 24)) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);

    const parts = [];
    if (d > 0) parts.push(`${d}d`);
    if (h > 0) parts.push(`${h}h`);
    if (m > 0) parts.push(`${m}m`);
    parts.push(`${s}s`);
    return parts.join(" ");
  };

  const getServiceColor = (state: string) => {
    if (state === "RUNNING") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    if (state.startsWith("START")) return "bg-amber-500/20 text-amber-400 border-amber-500/30";
    return "bg-rose-500/20 text-rose-400 border-rose-500/30";
  };

  const getTaskColor = (state: string) => {
    if (state === "Ready" || state === "Running") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    if (state === "Disabled") return "bg-zinc-500/20 text-zinc-400 border-zinc-700";
    return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  };

  const getLogLineClass = (line: string) => {
    const upper = line.toUpperCase();
    if (upper.includes("ERROR") || upper.includes("FAILED") || upper.includes("FATAL") || upper.includes("EXCEPTION")) {
      return "text-rose-400 bg-rose-950/20 px-2 py-0.5 rounded border-l-2 border-rose-500 my-0.5";
    }
    if (upper.includes("WARN") || upper.includes("WARNING")) {
      return "text-amber-400 bg-amber-950/20 px-2 py-0.5 rounded border-l-2 border-amber-500 my-0.5";
    }
    if (upper.includes("SUCCESS") || upper.includes("HEALTHY")) {
      return "text-emerald-400";
    }
    return "text-zinc-300";
  };

  const filteredLines = logData?.lines.filter(line => 
    line.toLowerCase().includes(logFilter.toLowerCase())
  ) || [];

  return (
    <main className="mx-auto max-w-3xl px-3 py-6 sm:px-4 text-zinc-100 flex flex-col gap-6">
      {/* Overview Card */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 sm:p-5 backdrop-blur">
        <h2 className="text-lg font-bold tracking-tight text-white mb-4 flex items-center justify-between">
          <span>System Overview</span>
          <button 
            onClick={fetchStatus}
            className="text-xs font-semibold text-violet-400 hover:text-violet-300 transition-colors px-2 py-1 rounded bg-violet-600/10 hover:bg-violet-600/20 cursor-pointer"
          >
            Refresh Now
          </button>
        </h2>

        {loading && !status ? (
          <div className="flex h-20 items-center justify-center">
            <Spinner className="h-6 w-6 text-violet-500" />
          </div>
        ) : error ? (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-400">
            Failed to load system status: {error}
          </div>
        ) : status ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1 rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-3">
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Dashboard Uptime</span>
              <span className="text-xl font-bold font-mono text-violet-400">{formatUptime(status.uptime)}</span>
            </div>
            <div className="flex flex-col gap-1 rounded-lg border border-zinc-800/80 bg-zinc-900/30 p-3">
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Log Directory Size</span>
              <span className="text-xl font-bold font-mono text-zinc-300">Healthy</span>
            </div>
          </div>
        ) : null}
      </section>

      {/* Services and Tasks */}
      {status && (
        <section className="grid gap-6 sm:grid-cols-2">
          {/* Services */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 backdrop-blur">
            <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-400 mb-3">Windows Services (NSSM)</h3>
            <div className="flex flex-col gap-2.5">
              {Object.entries(status.services).map(([name, state]) => (
                <div key={name} className="flex items-center justify-between p-2 rounded-lg border border-zinc-900 bg-zinc-900/10">
                  <span className="font-mono text-xs font-semibold text-zinc-300">{name}</span>
                  <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold tracking-wide ${getServiceColor(state)}`}>
                    {state}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Tasks */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 backdrop-blur">
            <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-400 mb-3">Scheduled Tasks</h3>
            <div className="flex flex-col gap-2.5">
              {Object.entries(status.tasks).map(([name, info]) => (
                <div key={name} className="flex flex-col gap-1 p-2 rounded-lg border border-zinc-900 bg-zinc-900/10">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold text-zinc-300">{name}</span>
                    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold tracking-wide ${getTaskColor(info.status)}`}>
                      {info.status}
                    </span>
                  </div>
                  {info.next_run && info.next_run !== "N/A" && (
                    <span className="text-[10px] text-zinc-500 font-medium">
                      Next run: <span className="text-zinc-400 font-mono">{info.next_run}</span>
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Logs Viewer */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 sm:p-5 backdrop-blur flex flex-col gap-4 flex-1">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
            <span>Live Logs</span>
            {loadingLog && <Spinner className="h-4 w-4 text-violet-500" />}
          </h2>

          <div className="flex flex-wrap gap-2 items-center">
            {/* Log Selector */}
            {status && (
              <select
                value={selectedLog}
                onChange={(e) => setSelectedLog(e.target.value)}
                className="bg-zinc-900 border border-zinc-700 text-zinc-200 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:border-violet-500 font-semibold cursor-pointer"
              >
                {status.logs.map((log) => (
                  <option key={log} value={log}>
                    {log}.log
                  </option>
                ))}
              </select>
            )}

            {/* Auto Refresh Switch */}
            <label className="flex items-center gap-1.5 text-xs text-zinc-400 font-medium cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefreshLogs}
                onChange={(e) => setAutoRefreshLogs(e.target.checked)}
                className="rounded text-violet-600 focus:ring-violet-500 bg-zinc-900 border-zinc-700 h-3.5 w-3.5 cursor-pointer"
              />
              <span>Auto-refresh (5s)</span>
            </label>
          </div>
        </div>

        {/* Filter Input */}
        <input
          type="text"
          placeholder="Filter log lines..."
          value={logFilter}
          onChange={(e) => setLogFilter(e.target.value)}
          className="w-full rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:border-violet-500 focus:outline-none"
        />

        {/* Log Lines Area */}
        <div className="relative rounded-lg border border-zinc-800 bg-black/60 p-3 h-96 overflow-y-auto font-mono text-[11px] leading-relaxed flex flex-col">
          {filteredLines.length === 0 ? (
            <div className="text-zinc-600 text-center py-10 italic">
              {logData ? "No matching log lines." : "Loading logs..."}
            </div>
          ) : (
            filteredLines.map((line, idx) => (
              <div key={idx} className={getLogLineClass(line)}>
                {line}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </section>
    </main>
  );
}
