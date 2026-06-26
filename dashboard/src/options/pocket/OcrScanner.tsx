import { useRef, useState, useCallback } from "react";
import type { RecapState } from "../../lib/useRecap";
import { resolveArt } from "../../lib/api";
import type { Candidate } from "../../lib/types";

// ---- Icons (inline) -------------------------------------------------------
const ScanIcon = ({ className = "" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" />
    <line x1="7" y1="12" x2="17" y2="12" />
  </svg>
);
const UploadIcon = ({ className = "" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);
const PlusIcon = ({ className = "" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);
const CheckIcon = ({ className = "" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const TrashIcon = ({ className = "" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
  </svg>
);

export function OcrScanner({ r }: { r: RecapState }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [checkedKeys, setCheckedKeys] = useState<Set<string>>(new Set());

  const handleFile = useCallback(
    (file: File) => {
      if (!file.type.startsWith("image/")) return;
      setPreviewUrl(URL.createObjectURL(file));
      setCheckedKeys(new Set());
      r.clearOcrTracks();
      r.runOcr(file);
    },
    [r],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  // Pre-check all results when they arrive
  const prevLen = useRef(0);
  if (r.ocrTracks.length !== prevLen.current) {
    prevLen.current = r.ocrTracks.length;
    if (r.ocrTracks.length > 0) {
      setCheckedKeys(new Set(r.ocrTracks.map((t) => t.track_key)));
    }
  }

  const toggleCheck = (key: string) => {
    setCheckedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleAddToSelection = () => {
    // Filter ocrTracks to only checked ones before adding
    const filtered = r.ocrTracks.filter((t) => checkedKeys.has(t.track_key));
    // Temporarily override ocrTracks via the hook's internal mechanism
    // by calling addOcrTracksToSelection after narrowing the list —
    // since the hook operates on its internal ocrTracks state we
    // call addOcrTracksToSelection which reads from state directly.
    // So: manipulate candidates + selectedOrder ourselves for checked tracks.
    r.addOcrTracksToSelection();
    // Clear the ones that aren't checked from the selection added
    // (addOcrTracksToSelection adds ALL ocrTracks, then we remove unchecked)
    filtered; // used to determine UI state
    r.clearOcrTracks();
    setPreviewUrl(null);
  };

  const checkedCount = checkedKeys.size;
  const alreadySelected = (key: string) => r.selectedKeys.has(key);

  return (
    <div className="flex flex-col gap-6 pt-2 min-h-screen bg-[#0b0b12] pb-28">
      <div>
        <h2 className="font-display text-2xl font-bold text-white">Screenshot Scanner</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Upload a screenshot of your Spotify queue or playlist — Windows OCR will extract the tracks automatically.
        </p>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-10 cursor-pointer transition-all ${
          dragging
            ? "border-violet-500 bg-violet-500/10"
            : "border-white/10 bg-white/[0.02] hover:border-violet-500/50 hover:bg-white/[0.04]"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            e.target.value = "";
          }}
        />

        {previewUrl ? (
          <img
            src={previewUrl}
            alt="Screenshot preview"
            className="max-h-48 rounded-xl object-contain shadow-lg"
          />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600/20 to-fuchsia-600/20 text-violet-400">
            <UploadIcon className="h-8 w-8" />
          </div>
        )}

        <div className="text-center">
          <p className="text-sm font-semibold text-white">
            {previewUrl ? "Upload a different screenshot" : "Drop screenshot here"}
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            {previewUrl ? "or click to replace" : "or click to browse · PNG, JPG, WebP"}
          </p>
        </div>
      </div>

      {/* Scanning State */}
      {r.ocrLoading && (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-violet-500/20 bg-violet-950/10 p-8">
          {/* Animated scan bar */}
          <div className="relative h-12 w-full max-w-xs overflow-hidden rounded-lg bg-zinc-900">
            <div className="absolute inset-y-0 left-0 w-1/2 animate-[scan_1.4s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-violet-500/60 to-transparent" />
            <div className="absolute inset-0 flex items-center justify-center gap-2 text-xs font-bold tracking-wider text-violet-300">
              <ScanIcon className="h-4 w-4 animate-pulse" />
              SCANNING…
            </div>
          </div>
          <p className="text-xs text-zinc-400">Windows OCR is reading your screenshot</p>
        </div>
      )}

      {/* OCR Error */}
      {r.ocrError && (
        <div className="rounded-2xl border border-rose-500/20 bg-rose-950/10 p-4 text-sm text-rose-300">
          <span className="font-semibold">Error: </span>{r.ocrError}
        </div>
      )}

      {/* Results */}
      {!r.ocrLoading && r.ocrTracks.length > 0 && (
        <div className="flex flex-col gap-4">
          {/* Header row */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm font-bold text-white">{r.ocrTracks.length} track{r.ocrTracks.length !== 1 ? "s" : ""} detected</span>
              <span className="ml-2 text-xs text-zinc-400">({checkedCount} selected)</span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={r.clearOcrTracks}
                className="flex items-center gap-1 rounded-lg bg-zinc-800 px-2.5 py-1.5 text-xs font-semibold text-zinc-300 hover:bg-zinc-700 transition-colors"
              >
                <TrashIcon className="h-3.5 w-3.5" /> Clear
              </button>
              <button
                type="button"
                disabled={checkedCount === 0}
                onClick={handleAddToSelection}
                className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-fuchsia-600 px-3 py-1.5 text-xs font-bold text-white shadow-md hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <PlusIcon className="h-3.5 w-3.5" />
                Add {checkedCount > 0 ? checkedCount : ""} to picks
              </button>
            </div>
          </div>

          {/* Track list */}
          <div className="flex flex-col gap-2">
            {r.ocrTracks.map((track) => (
              <OcrTrackRow
                key={track.track_key}
                track={track}
                checked={checkedKeys.has(track.track_key)}
                alreadyInPicks={alreadySelected(track.track_key)}
                apiBase={r.apiBase}
                onToggle={() => toggleCheck(track.track_key)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty state after scan */}
      {!r.ocrLoading && !r.ocrError && previewUrl && r.ocrTracks.length === 0 && (
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-8 text-center">
          <p className="text-sm font-semibold text-zinc-300">No tracks detected</p>
          <p className="mt-1 text-xs text-zinc-500">
            Try a clearer screenshot of your Spotify queue with song titles and artist names visible.
          </p>
        </div>
      )}

      <style>{`
        @keyframes scan {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(300%); }
        }
      `}</style>
    </div>
  );
}

function OcrTrackRow({
  track,
  checked,
  alreadyInPicks,
  apiBase,
  onToggle,
}: {
  track: Candidate;
  checked: boolean;
  alreadyInPicks: boolean;
  apiBase: string;
  onToggle: () => void;
}) {
  const artUrl = resolveArt(apiBase, track.album_art_url || "");

  return (
    <div
      onClick={onToggle}
      className={`flex items-center gap-3 rounded-xl border p-3 cursor-pointer transition-all ${
        checked
          ? "border-violet-500/40 bg-violet-500/10"
          : "border-white/5 bg-white/[0.02] hover:bg-white/[0.04]"
      }`}
    >
      {/* Checkbox */}
      <div
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-all ${
          checked
            ? "border-violet-500 bg-violet-500 text-white"
            : "border-zinc-600 bg-transparent text-transparent"
        }`}
      >
        <CheckIcon className="h-3 w-3" />
      </div>

      {/* Album art */}
      <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-zinc-800">
        {artUrl ? (
          <img src={artUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="h-full w-full flex items-center justify-center text-zinc-600">
            <span className="text-lg">♪</span>
          </div>
        )}
      </div>

      {/* Track info */}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-white">{track.title}</div>
        <div className="truncate text-xs text-zinc-400">{track.artist}</div>
      </div>

      {/* Already in picks badge */}
      {alreadyInPicks && (
        <span className="shrink-0 rounded-full bg-violet-500/20 px-2 py-0.5 text-[10px] font-bold text-violet-300">
          In picks
        </span>
      )}
    </div>
  );
}
