import { useEffect, useRef, useState } from "react";
import { canShareFiles, downloadSlides, prefetchSlides, shareSlides } from "../lib/saveSlides";

type Status = "loading" | "ready" | "saving" | "tap-again" | "done" | "error";

// One-tap "save every slide" button. On iPhone it opens the share sheet with
// "Save N Images" (→ Photos); elsewhere it downloads each PNG. `urls` are the
// slides' full PNG URLs (already prefixed with the API base).
export function SaveAllButton({ urls }: { urls: string[] }) {
  const [shareable] = useState(canShareFiles);
  const [status, setStatus] = useState<Status>(shareable ? "loading" : "ready");
  const [error, setError] = useState<string | null>(null);
  const filesRef = useRef<File[] | null>(null);
  const pendingRef = useRef<Promise<File[]> | null>(null);
  const key = urls.join("|");

  // Fetch the PNGs as soon as the gallery shows, so the tap can share instantly.
  useEffect(() => {
    const list = key ? key.split("|") : [];
    if (!shareable || list.length === 0) return;
    const ctrl = new AbortController();
    filesRef.current = null;
    setStatus("loading");
    setError(null);
    const pending = prefetchSlides(list, ctrl.signal);
    pendingRef.current = pending;
    pending.then(
      (files) => {
        filesRef.current = files;
        setStatus("ready");
      },
      (err) => {
        if (ctrl.signal.aborted) return;
        if (pendingRef.current === pending) pendingRef.current = null;
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      },
    );
    return () => {
      ctrl.abort();
      if (pendingRef.current === pending) pendingRef.current = null;
    };
  }, [key, shareable]); // keyed on the joined URLs; `urls` is a new array every render

  async function save() {
    setError(null);
    if (!shareable) {
      setStatus("saving");
      await downloadSlides(urls);
      setStatus("done");
      return;
    }
    try {
      setStatus("saving");
      let files = filesRef.current;
      if (!files) {
        // Retry after an error, or a tap before the prefetch finished.
        pendingRef.current ??= prefetchSlides(urls);
        files = await pendingRef.current;
        filesRef.current = files;
      }
      const outcome = await shareSlides(files);
      setStatus(outcome === "shared" ? "done" : outcome === "needs-tap" ? "tap-again" : "ready");
    } catch (err) {
      pendingRef.current = null;
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  if (urls.length === 0) return null;

  const n = urls.length;
  const label: Record<Status, string> = {
    loading: `Preparing ${n} slide${n === 1 ? "" : "s"}…`,
    ready: shareable ? `Save all ${n} to Photos` : `Download all ${n} PNGs`,
    saving: shareable ? "Opening share sheet…" : "Downloading…",
    "tap-again": "Ready — tap again to save",
    done: shareable ? "Saved ✓ — tap to save again" : "Downloaded ✓",
    error: "Retry save",
  };

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={save}
        disabled={status === "saving"}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white shadow-lg shadow-emerald-950/40 transition-colors hover:bg-emerald-500 disabled:opacity-60"
      >
        <span aria-hidden>{shareable ? "📲" : "⬇"}</span>
        {label[status]}
      </button>
      {shareable && status === "ready" && (
        <p className="text-center text-[11px] text-zinc-500">
          Pick <strong className="text-zinc-300">Save {n} Images</strong> in the share sheet.
        </p>
      )}
      {error && <p className="text-center text-[11px] text-rose-400">{error}</p>}
    </div>
  );
}
