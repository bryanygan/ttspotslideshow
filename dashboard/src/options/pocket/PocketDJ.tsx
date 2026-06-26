import { useState, useMemo, useEffect, useRef } from "react";
import type { RecapState } from "../../lib/useRecap";
import { WINDOWS, windowLabel, COVER_THEMES } from "../../lib/constants";
import { resolveArt } from "../../lib/api";
import { AlbumArt } from "../../ui/AlbumArt";
import { ArtUploadButton } from "../../ui/ArtUploadButton";
import { CoverControls } from "../../ui/CoverControls";
import { PresetPanel } from "../../ui/PresetPanel";
import { SelectedTray } from "../../ui/SelectedTray";
import { SlideGallery } from "../../ui/SlideGallery";
import { Summary } from "../../ui/Summary";
import { ErrorBanner } from "../../ui/ErrorBanner";
import { underratedScore } from "../../lib/types";
import {
  GridIcon,
  StackIcon,
  WandIcon,
  CheckIcon,
  MusicIcon,
  ChevronRightIcon,
} from "../../ui/icons";

type Tab = "browse" | "picks" | "create";

// Option A — "Pocket DJ": app-like, thumb-first. Bottom tabs, album-art-forward
// browse grid, a floating picks pill, and a cover-preview hero on Create.
export function PocketDJ({ r }: { r: RecapState }) {
  const [tab, setTab] = useState<Tab>("browse");

  return (
    <div className="min-h-screen bg-[#0b0b12] pb-28 font-sans text-zinc-100">
      {tab === "browse" && <BrowseHeader r={r} />}

      <main className="mx-auto w-full max-w-3xl px-4 pt-4">
        {r.error && (
          <div className="mb-4">
            <ErrorBanner message={r.error} />
          </div>
        )}

        {tab === "browse" && <BrowseGrid r={r} />}
        {tab === "picks" && <PicksTab r={r} />}
        {tab === "create" && <CreateTab r={r} />}
      </main>

      {/* Floating picks pill — review your selection from anywhere. */}
      {r.selectedKeys.size > 0 && tab !== "picks" && (
        <button
          type="button"
          onClick={() => setTab("picks")}
          className="fixed bottom-20 right-4 z-40 flex items-center gap-1.5 rounded-full border border-violet-500/30 bg-violet-600 px-3.5 py-2 text-xs font-bold text-white shadow-lg shadow-violet-950/50 hover:bg-violet-500 transition-all active:scale-95"
        >
          <span>{r.selectedKeys.size} picked · Review</span>
          <ChevronRightIcon className="h-3.5 w-3.5" />
        </button>
      )}

      <TabBar tab={tab} setTab={setTab} pickCount={r.selectedKeys.size} />
    </div>
  );
}

// ---- Browse ---------------------------------------------------------------

function BrowseHeader({ r }: { r: RecapState }) {
  return (
    <div className="sticky top-11 z-30 border-b border-white/5 bg-[#0b0b12]/85 backdrop-blur">
      <div className="mx-auto flex max-w-3xl flex-col gap-2.5 px-4 py-3">
        <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
          {WINDOWS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => r.setDays(d)}
              className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-bold transition-all ${
                r.days === d
                  ? "bg-violet-500 text-white shadow-md shadow-violet-900/40"
                  : "bg-white/5 text-zinc-400 hover:bg-white/10"
              }`}
            >
              {windowLabel(d)}
            </button>
          ))}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
            {r.candidates.length} tracks
          </span>
          <div className="flex rounded-full bg-white/5 p-0.5 text-xs font-bold">
            {(["plays", "underrated"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => r.setSortBy(s)}
                className={`rounded-full px-3 py-1 capitalize transition-colors ${
                  r.sortBy === s ? "bg-violet-500 text-white" : "text-zinc-400"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function BrowseGrid({ r }: { r: RecapState }) {
  if (r.loading) {
    return (
      <div className="grid grid-cols-2 gap-3 pt-2 sm:grid-cols-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="animate-pulse">
            <div className="aspect-square w-full rounded-2xl bg-white/5" />
            <div className="mt-2 h-3 w-3/4 rounded bg-white/5" />
            <div className="mt-1.5 h-2.5 w-1/2 rounded bg-white/5" />
          </div>
        ))}
      </div>
    );
  }

  if (r.sortedCandidates.length === 0) {
    return (
      <EmptyState
        title="No tracks here yet"
        body={`Nothing was logged in the last ${windowLabel(r.days)}. Try a longer window above.`}
      />
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 pt-2 sm:grid-cols-3">
      {r.sortedCandidates.map((track) => {
        const selected = r.isSelected(track.track_key);
        return (
          <div
            key={track.track_key}
            role="button"
            tabIndex={0}
            onClick={() => r.toggleSelect(track.track_key)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                r.toggleSelect(track.track_key);
              }
            }}
            className={`group cursor-pointer rounded-2xl p-1.5 transition-all ${
              selected ? "bg-violet-500/15 ring-2 ring-violet-500" : "hover:bg-white/5"
            }`}
          >
            <div className="relative">
              <AlbumArt
                apiBase={r.apiBase}
                track={track}
                className="aspect-square w-full"
                rounded="rounded-xl"
              />
              {/* selection check */}
              <div
                className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full border-2 transition-all ${
                  selected
                    ? "border-violet-400 bg-violet-500 text-white"
                    : "border-white/60 bg-black/30 text-transparent"
                }`}
              >
                <CheckIcon className="h-4 w-4" />
              </div>
              <ArtUploadButton
                onFile={(file) => r.uploadArtFor(track, file)}
                className="absolute left-2 top-2 rounded-full bg-black/50 p-1.5 text-white/80 opacity-0 transition-opacity hover:bg-black/70 hover:text-white group-hover:opacity-100"
              />
              {r.sortBy === "underrated" && (
                <span className="absolute bottom-2 left-2 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[10px] font-bold text-violet-300">
                  {underratedScore(track).toFixed(1)}
                </span>
              )}
            </div>

            <div className="px-1 pt-2">
              <div className="truncate text-sm font-semibold text-white" title={track.title}>
                {track.title}
              </div>
              <div className="truncate text-xs text-zinc-400" title={track.artist}>
                {track.artist}
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-300">
                  {track.play_count} play{track.play_count !== 1 ? "s" : ""}
                </span>
                <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-violet-300">
                  {track.primary_bucket}
                </span>
                {track.last_featured && (
                  <span className="rounded bg-fuchsia-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-fuchsia-300">
                    Featured
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---- Picks ----------------------------------------------------------------

function PicksTab({ r }: { r: RecapState }) {
  return (
    <div className="flex flex-col gap-6 pt-2">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-2xl font-bold text-white">Your picks</h2>
        {r.selectedKeys.size > 0 && (
          <button
            type="button"
            onClick={r.clearSelection}
            className="text-xs font-bold uppercase tracking-wider text-rose-400 hover:text-rose-300"
          >
            Clear all
          </button>
        )}
      </div>

      <section className="flex flex-col gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-4">
        <h3 className="font-display text-sm font-semibold text-zinc-300">Smart fill</h3>
        <PresetPanel r={r} />
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="font-display text-sm font-semibold text-zinc-300">
          Order ({r.selectedTracks.length})
        </h3>
        <SelectedTray r={r} />
      </section>
    </div>
  );
}

// ---- Create ---------------------------------------------------------------

function CreateTab({ r }: { r: RecapState }) {
  const theme = COVER_THEMES.find((t) => t.value === r.coverTheme) ?? COVER_THEMES[0];
  const canGenerate = r.selectedKeys.size > 0 && !r.generating;

  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let interval: any;
    if (r.generating) {
      setProgress(0);
      interval = setInterval(() => {
        setProgress((prev) => {
          if (prev < 40) {
            return prev + Math.floor(Math.random() * 10 + 5);
          } else if (prev < 85) {
            return prev + Math.floor(Math.random() * 3 + 1);
          } else if (prev < 95) {
            return prev + 1;
          }
          return prev;
        });
      }, 150);
    } else {
      setProgress(0);
    }
    return () => clearInterval(interval);
  }, [r.generating]);

  // A representative sample of covers for the live preview. The real cover uses
  // a randomized all-time set rendered server-side; this just conveys the look.
  const previewArts = useMemo(() => {
    const arts = r.candidates
      .map((c) => resolveArt(r.apiBase, c.album_art_url))
      .filter(Boolean);
    for (let i = arts.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arts[i], arts[j]] = [arts[j], arts[i]];
    }
    return arts.slice(0, 28);
  }, [r.candidates, r.apiBase]);

  return (
    <div className="flex flex-col gap-6 pt-2">
      <h2 className="font-display text-2xl font-bold text-white">Create recap</h2>

      {/* Hero: a live preview of the collage cover as the user tunes it. */}
      {r.includeCover && (
        <div className="flex flex-col items-center gap-2">
          <div className="relative aspect-[9/16] w-44 overflow-hidden rounded-2xl shadow-xl">
            <div className="absolute inset-0 grid grid-cols-4">
              {previewArts.map((src, i) => (
                <div key={i} className="aspect-square bg-zinc-800">
                  <img src={src} alt="" className="h-full w-full object-cover" />
                </div>
              ))}
            </div>
            {r.coverTheme !== "none" && (
              <div className={`absolute inset-0 bg-gradient-to-br ${theme.swatch} opacity-55`} />
            )}
            <div className="absolute inset-0 bg-black/30" />
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 px-3 text-center">
              <span className="text-[8px] font-bold uppercase tracking-[0.2em] text-white/75">
                {r.coverSubtitle}
              </span>
              <span className="font-display text-base font-bold leading-tight text-white drop-shadow">
                {r.coverTitle}
              </span>
            </div>
            {r.watermark && (
              <span className="absolute inset-x-0 bottom-2 text-center font-mono text-[7px] uppercase tracking-wider text-white/70">
                {r.watermark}
              </span>
            )}
          </div>
          <p className="max-w-xs text-center text-[11px] text-zinc-500">
            Cover is a randomized collage of your all-time album covers.
          </p>
        </div>
      )}

      <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-4">
        <CoverControls r={r} />
      </section>

      <Summary r={r} />

      {/* iTunes Confirmation Panel — shown before missingCovers */}
      {r.unconfirmedCovers.length > 0 && (
        <section className="rounded-2xl border border-amber-500/20 bg-amber-950/10 p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h3 className="font-display text-sm font-semibold text-amber-300 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
              iTunes Cover Confirmation ({r.unconfirmedCovers.length})
            </h3>
            <p className="text-xs text-zinc-400">
              These tracks don't have a Spotify cover — we found the following on iTunes. Are they correct?
            </p>
          </div>

          <div className="flex flex-col gap-3">
            {r.unconfirmedCovers.map((track) => (
              <ItunesConfirmRow
                key={track.track_key}
                track={track}
                onConfirm={(accept) => r.confirmItunesCover(track, accept)}
              />
            ))}
          </div>
        </section>
      )}

      {r.missingCovers.length > 0 && (
        <section className="rounded-2xl border border-rose-500/20 bg-rose-950/10 p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h3 className="font-display text-sm font-semibold text-rose-300 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
              Missing Spotify Cover Art ({r.missingCovers.length})
            </h3>
            <p className="text-xs text-zinc-400">
              The following tracks do not have cover art on Spotify. Please upload an image or paste a direct image URL link:
            </p>
          </div>

          <div className="flex flex-col gap-3">
            {r.missingCovers.map((track) => (
              <MissingCoverRow
                key={track.track_key}
                track={track}
                onUpload={(file) => r.uploadArtFor(track as any, file)}
                onSaveLink={(url) => r.saveArtLinkFor(track, url)}
              />
            ))}
          </div>
        </section>
      )}

      <button
        type="button"
        onClick={r.generate}
        disabled={!canGenerate}
        className={`relative overflow-hidden flex items-center justify-center gap-2 rounded-2xl py-4 text-base font-bold transition-all ${
          canGenerate
            ? "bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-500 text-white shadow-lg shadow-violet-900/40 active:scale-[0.98]"
            : "cursor-not-allowed bg-white/5 text-zinc-600"
        }`}
      >
        {/* Progress bar overlay */}
        {r.generating && (
          <div
            className="absolute inset-y-0 left-0 bg-white/20 transition-all duration-300 ease-out"
            style={{ width: `${progress}%` }}
          />
        )}

        <span className="relative z-10 flex items-center gap-2">
          {r.generating ? (
            <span>Generating… {progress}%</span>
          ) : (
            <>
              <WandIcon className="h-5 w-5" /> Generate recap slides
            </>
          )}
        </span>
      </button>

      <SlideGallery r={r} />
    </div>
  );
}

function MissingCoverRow({
  track,
  onUpload,
  onSaveLink,
}: {
  track: { artist: string; title: string; track_key: string };
  onUpload: (file: File) => void;
  onSaveLink: (url: string) => void;
}) {
  const [linkUrl, setLinkUrl] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3">
      <div className="flex flex-col min-w-0 flex-1">
        <span className="truncate text-sm font-semibold text-white">{track.title}</span>
        <span className="truncate text-xs text-zinc-400">{track.artist}</span>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="file"
          ref={fileInputRef}
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onUpload(file);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-semibold text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer"
        >
          Upload Image
        </button>

        <div className="flex items-center gap-1 flex-1 sm:flex-none">
          <input
            type="text"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            placeholder="Paste image link..."
            className="w-full sm:w-44 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100 focus:border-violet-500 focus:outline-none"
          />
          <button
            type="button"
            disabled={!linkUrl.trim()}
            onClick={() => onSaveLink(linkUrl.trim())}
            className="rounded-lg bg-violet-600 px-2.5 py-1.5 text-xs font-bold text-white hover:bg-violet-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            Save Link
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Chrome ---------------------------------------------------------------

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/5 bg-white/[0.02] px-6 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-zinc-500">
        <MusicIcon className="h-7 w-7" />
      </div>
      <h3 className="font-display text-lg font-bold text-zinc-200">{title}</h3>
      <p className="max-w-xs text-sm text-zinc-500">{body}</p>
    </div>
  );
}

function TabBar({
  tab,
  setTab,
  pickCount,
}: {
  tab: Tab;
  setTab: (t: Tab) => void;
  pickCount: number;
}) {
  const items: Array<{ id: Tab; label: string; Icon: typeof GridIcon; badge?: number }> = [
    { id: "browse", label: "Browse", Icon: GridIcon },
    { id: "picks", label: "Picks", Icon: StackIcon, badge: pickCount },
    { id: "create", label: "Create", Icon: WandIcon },
  ];
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-[#0b0b12]/85 pb-safe backdrop-blur-lg">
      <div className="mx-auto grid max-w-3xl grid-cols-3">
        {items.map(({ id, label, Icon, badge }) => {
          const active = tab === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`relative flex flex-col items-center gap-1 py-2.5 text-[11px] font-semibold transition-colors ${
                active ? "text-violet-400" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              <Icon className="h-6 w-6" />
              {label}
              {badge ? (
                <span className="absolute right-1/2 top-1.5 translate-x-4 rounded-full bg-fuchsia-500 px-1.5 text-[9px] font-bold text-white">
                  {badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function ItunesConfirmRow({
  track,
  onConfirm,
}: {
  track: { artist: string; title: string; track_key: string; itunes_url: string };
  onConfirm: (accept: boolean) => void;
}) {
  const [denied, setDenied] = useState(false);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3">
      <div className="flex items-center gap-3">
        {/* iTunes cover preview */}
        <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-zinc-800 shadow">
          <img
            src={track.itunes_url}
            alt=""
            className="h-full w-full object-cover"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        </div>

        {/* Track info */}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-white">{track.title}</div>
          <div className="truncate text-xs text-zinc-400">{track.artist}</div>
          <div className="mt-0.5 text-[10px] text-amber-400/80">iTunes fallback</div>
        </div>

        {/* Confirm / Deny — only shown while not yet denied */}
        {!denied && (
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => onConfirm(true)}
              className="flex items-center gap-1 rounded-lg bg-emerald-600/20 border border-emerald-500/30 px-2.5 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-600/30 transition-colors"
            >
              ✓ Looks right
            </button>
            <button
              type="button"
              onClick={() => setDenied(true)}
              className="flex items-center gap-1 rounded-lg bg-rose-600/20 border border-rose-500/30 px-2.5 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-600/30 transition-colors"
            >
              ✕ Wrong
            </button>
          </div>
        )}
      </div>

      {/* Manual replacement — shown after denying */}
      {denied && (
        <div className="flex flex-col gap-2 pt-1 border-t border-white/5">
          <p className="text-xs text-zinc-400">
            Upload or paste a direct image link below, then hit Save — the track will appear in the Upload section:
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onConfirm(false)}
              className="rounded-lg bg-zinc-800 border border-zinc-700 px-2.5 py-1.5 text-xs font-semibold text-zinc-300 hover:bg-zinc-700 transition-colors whitespace-nowrap"
            >
              Move to upload section ↓
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
