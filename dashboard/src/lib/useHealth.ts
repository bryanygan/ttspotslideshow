import { useCallback, useEffect, useRef, useState } from "react";
import type { Health } from "./types";
import { fetchHealth } from "./api";

export type ConnState = "connecting" | "online" | "offline";

export interface HealthState {
  conn: ConnState;
  health: Health | null;
  retryInSec: number | null; // countdown until the next auto-retry while offline
  retryNow: () => void;
}

// Polls /api/health as a liveness probe. While online, re-checks every 20s and
// surfaces degraded/warning states. While offline (backend down / tunnel 502),
// auto-retries with exponential backoff and a visible countdown, then recovers
// automatically once the backend is back — turning the old blank/CORS failure
// into a self-healing state.
export function useHealth(apiBase: string): HealthState {
  const [conn, setConn] = useState<ConnState>("connecting");
  const [health, setHealth] = useState<Health | null>(null);
  const [retryInSec, setRetryInSec] = useState<number | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(2);
  const abortRef = useRef<AbortController | null>(null);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const check = useCallback(async () => {
    clearTimer();
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const h = await fetchHealth(apiBase, controller.signal);
      setHealth(h);
      setConn("online");
      setRetryInSec(null);
      backoffRef.current = 2; // reset backoff after a success
      timerRef.current = setTimeout(check, 20000); // steady re-check while online
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setConn("offline");
      const wait = Math.min(30, Math.round(backoffRef.current));
      backoffRef.current = Math.min(30, backoffRef.current * 1.6);
      let remaining = wait;
      setRetryInSec(remaining);
      const tick = () => {
        remaining -= 1;
        if (remaining <= 0) {
          setRetryInSec(0);
          check();
        } else {
          setRetryInSec(remaining);
          timerRef.current = setTimeout(tick, 1000);
        }
      };
      timerRef.current = setTimeout(tick, 1000);
    }
  }, [apiBase]);

  const retryNow = useCallback(() => {
    setConn("connecting");
    backoffRef.current = 2;
    check();
  }, [check]);

  useEffect(() => {
    setConn("connecting");
    backoffRef.current = 2;
    check();
    return () => {
      clearTimer();
      abortRef.current?.abort();
    };
  }, [check]);

  return { conn, health, retryInSec, retryNow };
}
