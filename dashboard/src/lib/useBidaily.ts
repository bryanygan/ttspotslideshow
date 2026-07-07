import { useCallback, useEffect, useRef, useState } from "react";
import type { BidailyStatus, BidailyEntry } from "./types";
import { runBidaily, fetchBidailyStatus, fetchBidailyHistory } from "./api";

export interface BidailyState {
  status: BidailyStatus | null;
  history: BidailyEntry[];
  historyLoading: boolean;
  error: string | null;
  starting: boolean;
  start: () => void;
  refreshHistory: () => void;
}

// Drives the Bi-daily section: current/last run status (polled while running),
// the ability to trigger a run, and the history of past dated slide sets.
export function useBidaily(apiBase: string, active: boolean): BidailyState {
  const [status, setStatus] = useState<BidailyStatus | null>(null);
  const [history, setHistory] = useState<BidailyEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      setHistory(await fetchBidailyHistory(apiBase));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history.");
    } finally {
      setHistoryLoading(false);
    }
  }, [apiBase]);

  const poll = useCallback(async () => {
    try {
      const s = await fetchBidailyStatus(apiBase);
      setStatus(s);
      if (s.running) {
        pollRef.current = setTimeout(poll, 2000);
      } else {
        refreshHistory(); // just finished — pull in the new slide set
      }
    } catch {
      // Transient poll error — try again shortly.
      pollRef.current = setTimeout(poll, 3000);
    }
  }, [apiBase, refreshHistory]);

  const start = useCallback(async () => {
    setStarting(true);
    setError(null);
    try {
      await runBidaily(apiBase);
      poll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run.");
    } finally {
      setStarting(false);
    }
  }, [apiBase, poll]);

  useEffect(() => {
    if (!active) return;
    fetchBidailyStatus(apiBase)
      .then((s) => {
        setStatus(s);
        if (s.running) poll();
      })
      .catch(() => {});
    refreshHistory();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [active, apiBase, poll, refreshHistory]);

  return { status, history, historyLoading, error, starting, start, refreshHistory };
}
