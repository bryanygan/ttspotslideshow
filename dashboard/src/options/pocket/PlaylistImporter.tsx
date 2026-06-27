import { useRef, useState } from "react";
import type { RecapState } from "../../lib/useRecap";
import { resolveArt } from "../../lib/api";
import type { Candidate } from "../../lib/types";

// ---- Icons (inline) -------------------------------------------------------
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

export function PlaylistImporter({ r }: { r: RecapState }) {
  const [url, setUrl] = useState("");
  const [checkedKeys, setCheckedKeys] = useState<Set<string>>(new Set());

  // Save-to-Spotify state
  const [saveName, setSaveName] = useState("");
  const [savedUrl, setSavedUrl] = useState<string | null>(null);

  const handleParse = () => {
    if (!url.trim()) return;
    r.parsePlaylistLink(url.trim());
  };

  // Pre-check all results when a new set arrives.
  const prevLen = useRef(0);
  if (r.playlistTracks.length !== prevLen.current) {
    prevLen.current = r.playlistTracks.length;
    if (r.playlistTracks.length > 0) {
      setCheckedKeys(new Set(r.playlistTracks.map((t) => t.track_key)));
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
    r.addPlaylistTracksToSelection();
    r.clearPlaylistTracks();
    setUrl("");
  };

  const handleClear = () => {
    r.clearPlaylistTracks();
    setUrl("");
  };

  const handleSave = async () => {
    setSavedUrl(null);
    const resultUrl = await r.saveSelectionToSpotify(saveName);
    if (resultUrl) setSavedUrl(resultUrl);
  };

  const checkedCount = checkedKeys.size;
  const alreadySelected = (key: string) => r.selectedKeys.has(key);

  return (
    <div className="flex flex-col gap-6 pt-2 min-h-screen bg-[#0b0b12] pb-28 mx-auto w-full max-w-3xl px-4">
      <div>
        <h2 className="font-display text-2xl font-bold text-white">Playlist Import / Export</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Paste a Spotify playlist link (or ID) or a Last.fm user loved/library URL to seed
          your picks — or save your current picks back to a new Spotify playlist.
        </p>
      </div>

      {/* Import input */}
      <div className="flex flex-col gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-4">
        <label className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
          Import from link
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleParse(); }}
            placeholder="https://open.spotify.com/playlist/...  or  https://www.last.fm/user/<name>/loved"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
          />
          <button
            type="button"
            disabled={!url.trim() || r.playlistLoading}
            onClick={handleParse}
            className="rounded-lg bg-gradient-to-r from-violet-600 to-fuchsia-600 px-4 py-2 text-sm font-bold text-white shadow-md transition-opacity hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {r.playlistLoading ? "Loading…" : "Load"}
          </button>
        </div>
        <p className="text-[11px] text-zinc-500">
          Spotify playlists resolve fully. Last.fm supports a user's <code className="text-zinc-300">/loved</code> and
          <code className="text-zinc-300"> /library</code> (top tracks) URLs.
        </p>
      </div>

      {/* Parse error */}
      {r.playlistError && (
        <div className="rounded-2xl border border-rose-500/20 bg-rose-950/10 p-4 text-sm text-rose-300">
          <span className="font-semibold">Error: </span>{r.playlistError}
        </div>
      )}

      {/* Results */}
      {!r.playlistLoading && r.playlistTracks.length > 0 && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm font-bold text-white">
                {r.playlistTracks.length} track{r.playlistTracks.length !== 1 ? "s" : ""}
              </span>
              {r.playlistSource && (
                <span className="ml-2 rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-bold uppercase text-violet-300">
                  {r.playlistSource}
                </span>
              )}
              <span className="ml-2 text-xs text-zinc-400">({checkedCount} selected)</span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleClear}
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

          <div className="flex flex-col gap-2">
            {r.playlistTracks.map((track) => (
              <PlaylistTrackRow
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

      {/* Export / save-back */}
      <div className="flex flex-col gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-4">
        <label className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
          Save current picks to Spotify ({r.selectedKeys.size})
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="text"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            placeholder="New playlist name (optional)"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-violet-500 focus:outline-none"
          />
          <button
            type="button"
            disabled={r.selectedKeys.size === 0 || r.playlistSaving}
            onClick={handleSave}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white shadow-md transition-colors hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {r.playlistSaving ? "Saving…" : "Save to Spotify"}
          </button>
        </div>
        {savedUrl && (
          <a
            href={savedUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-semibold text-emerald-400 hover:text-emerald-300"
          >
            ✓ Saved — open playlist on Spotify ↗
          </a>
        )}
        <p className="text-[11px] text-zinc-500">
          Only tracks with a Spotify ID can be saved (Last.fm-only tracks are skipped).
          Requires the playlist-modify scopes — you may need to re-authorize once.
        </p>
      </div>
    </div>
  );
}

function PlaylistTrackRow({
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
      <div
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-all ${
          checked
            ? "border-violet-500 bg-violet-500 text-white"
            : "border-zinc-600 bg-transparent text-transparent"
        }`}
      >
        <CheckIcon className="h-3 w-3" />
      </div>

      <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-zinc-800">
        {artUrl ? (
          <img src={artUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="h-full w-full flex items-center justify-center text-zinc-600">
            <span className="text-lg">♪</span>
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-white">{track.title}</div>
        <div className="truncate text-xs text-zinc-400">{track.artist}</div>
      </div>

      {alreadyInPicks && (
        <span className="shrink-0 rounded-full bg-violet-500/20 px-2 py-0.5 text-[10px] font-bold text-violet-300">
          In picks
        </span>
      )}
    </div>
  );
}
