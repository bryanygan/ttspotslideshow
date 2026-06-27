import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import type { Candidate, GenerateSummary, SortBy } from "./types";
import { underratedScore } from "./types";
import {
  fetchCandidates,
  generateRecapStream,
  saveItunesUrl,
  uploadArt,
  uploadOcrScreenshot,
  fetchRecapHistory,
  fetchRecapSlides,
  parsePlaylist,
  savePlaylist,
  searchSpotify,
  MissingCoverError,
  UnconfirmedCoverError,
} from "./api";
import type { RecapHistoryEntry } from "./api";
import { PRESETS } from "./presets";

const API_BASE_KEY = "api_base";
const DEFAULT_API_BASE = "http://localhost:8000";

// Mirrors text_norm.normalize on the backend (lowercase, trim, collapse
// whitespace) so a manual entry dedupes against DB tracks by track_key.
function normalizeKeyPart(s: string): string {
  return s.trim().replace(/\s+/g, " ").toLowerCase();
}

// Fill the grid-required fields that search/manual candidates don't carry.
function withCandidateDefaults(
  partial: Partial<Candidate> & Pick<Candidate, "track_key" | "title" | "artist">,
): Candidate {
  return {
    track_id: "",
    album_art_url: "",
    play_count: 0,
    last_played_unix: 0,
    primary_bucket: "unknown",
    popularity: 50,
    last_featured: null,
    recently_featured: false,
    times_featured: 0,
    ...partial,
  };
}

// Everything the two UI options need. One instance lives in <App/> and is
// passed to whichever option is active, so selections survive the A/B toggle.
export interface RecapState {
  apiBase: string;
  setApiBase: (v: string) => void;

  days: number;
  setDays: (d: number) => void;
  sortBy: SortBy;
  setSortBy: (s: SortBy) => void;

  candidates: Candidate[];
  sortedCandidates: Candidate[];
  loading: boolean;
  error: string | null;
  refetch: () => void;

  selectedKeys: Set<string>;
  selectedOrder: string[];
  selectedTracks: Candidate[];
  isSelected: (key: string) => boolean;
  toggleSelect: (key: string) => void;
  clearSelection: () => void;

  quickSelectCount: number;
  setQuickSelectCount: (n: number) => void;
  applyPreset: (presetId: string, mode?: "overwrite" | "fill") => void;

  moveSelected: (key: string, dir: -1 | 1) => void;
  swapSelected: (oldKey: string, newKey: string) => void;
  replaceWithRandom: (oldKey: string) => void;

  // Cover / branding
  includeCover: boolean;
  setIncludeCover: (v: boolean) => void;
  coverTitle: string;
  setCoverTitle: (v: string) => void;
  coverSubtitle: string;
  setCoverSubtitle: (v: string) => void;
  coverTheme: string;
  setCoverTheme: (v: string) => void;
  watermark: string;
  setWatermark: (v: string) => void;
  coverOnly: boolean;
  setCoverOnly: (v: boolean) => void;
  coverColumns: number;
  setCoverColumns: (v: number) => void;
  coverRows: number;
  setCoverRows: (v: number) => void;
  slideWidth: number;
  setSlideWidth: (w: number) => void;
  slideHeight: number;
  setSlideHeight: (h: number) => void;
  lockAspectRatio: boolean;
  setLockAspectRatio: (v: boolean) => void;
  toggleLockAspectRatio: () => void;

  // Generation
  generating: boolean;
  summary: GenerateSummary | null;
  slideUrls: string[];
  slideCount: number;
  leftover: number;
  generate: () => void;
  layout: "2x2" | "3x3" | "4x4";
  setLayout: (v: "2x2" | "3x3" | "4x4") => void;

  // Real-time progress (SSE)
  progress: number;
  progressStage: string;
  progressDetail: string;
  progressEta: number | null;

  uploadArtFor: (track: Candidate, file: File) => void;
  missingCovers: Array<{ artist: string; title: string; track_key: string }>;
  setMissingCovers: (v: Array<{ artist: string; title: string; track_key: string }>) => void;
  saveArtLinkFor: (track: { artist: string; title: string; track_key: string }, url: string) => Promise<void>;

  // iTunes confirmation flow
  unconfirmedCovers: Array<{ artist: string; title: string; track_key: string; itunes_url: string }>;
  confirmItunesCover: (track: { artist: string; title: string; track_key: string; itunes_url: string }, accept: boolean) => Promise<void>;

  // OCR
  ocrTracks: Candidate[];
  ocrLoading: boolean;
  ocrError: string | null;
  runOcr: (files: File[]) => Promise<void>;
  addOcrTracksToSelection: () => void;
  clearOcrTracks: () => void;

  // Playlist import / export
  playlistTracks: Candidate[];
  playlistLoading: boolean;
  playlistError: string | null;
  playlistSource: "spotify" | "lastfm" | null;
  parsePlaylistLink: (url: string) => Promise<void>;
  addPlaylistTracksToSelection: () => void;
  clearPlaylistTracks: () => void;
  saveSelectionToSpotify: (name: string) => Promise<string | null>;
  playlistSaving: boolean;

  // Browse search / custom lookup
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  spotifyResults: Candidate[];
  searchLoading: boolean;
  searchError: string | null;
  runSpotifySearch: (q: string) => Promise<void>;
  clearSearch: () => void;
  addSearchTrack: (track: Candidate) => void;
  addCustomTrack: (input: { title: string; artist: string; albumArtUrl: string }) => void;

  // Recap history
  recapHistory: RecapHistoryEntry[];
  recapHistoryLoading: boolean;
  recapHistoryError: string | null;
  loadRecapHistory: () => void;
  selectedRecapId: string | null;
  selectedRecapSlides: string[];
  selectedRecapLoading: boolean;
  selectRecap: (recapId: string | null) => void;
}

export function useRecap(): RecapState {
  const [apiBase, setApiBaseRaw] = useState<string>(
    () => localStorage.getItem(API_BASE_KEY) || DEFAULT_API_BASE,
  );
  const [days, setDays] = useState(7);
  const [sortBy, setSortBy] = useState<SortBy>("plays");

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [selectedOrder, setSelectedOrder] = useState<string[]>([]);
  const [quickSelectCount, setQuickSelectCount] = useState(16);

  const [layout, setLayoutRaw] = useState<"2x2" | "3x3" | "4x4">("2x2");
  const setLayout = useCallback((newLayout: "2x2" | "3x3" | "4x4") => {
    setLayoutRaw(newLayout);
    if (newLayout === "3x3") {
      setQuickSelectCount(18);
    } else if (newLayout === "4x4") {
      setQuickSelectCount(16);
    } else {
      setQuickSelectCount(16);
    }
  }, []);

  const [includeCover, setIncludeCover] = useState(true);
  const [coverTitle, setCoverTitle] = useState("");
  const [coverSubtitle, setCoverSubtitle] = useState("");
  const [coverTheme, setCoverTheme] = useState("none");
  const [watermark, setWatermark] = useState("");
  const [coverOnly, setCoverOnly] = useState(false);
  const [coverColumns, setCoverColumns] = useState(5);
  const [coverRows, setCoverRows] = useState(9);
  const [slideWidth, setSlideWidthRaw] = useState(1080);
  const [slideHeight, setSlideHeightRaw] = useState(1700);
  const [lockAspectRatio, setLockAspectRatio] = useState(true);
  const [aspectRatio, setAspectRatio] = useState(1080 / 1700);

  const toggleLockAspectRatio = useCallback(() => {
    setLockAspectRatio((prev) => {
      const next = !prev;
      if (next) {
        setAspectRatio(slideWidth / slideHeight);
      }
      return next;
    });
  }, [slideWidth, slideHeight]);

  const setSlideWidth = useCallback((w: number) => {
    setSlideWidthRaw(w);
    if (lockAspectRatio) {
      setSlideHeightRaw(Math.round(w / aspectRatio));
    }
  }, [lockAspectRatio, aspectRatio]);

  const setSlideHeight = useCallback((h: number) => {
    setSlideHeightRaw(h);
    if (lockAspectRatio) {
      setSlideWidthRaw(Math.round(h * aspectRatio));
    }
  }, [lockAspectRatio, aspectRatio]);

  const [generating, setGenerating] = useState(false);
  const [summary, setSummary] = useState<GenerateSummary | null>(null);
  const [slideUrls, setSlideUrls] = useState<string[]>([]);
  const [missingCovers, setMissingCovers] = useState<Array<{ artist: string; title: string; track_key: string }>>([]);
  const [unconfirmedCovers, setUnconfirmedCovers] = useState<Array<{ artist: string; title: string; track_key: string; itunes_url: string }>>([]);

  const [progress, setProgress] = useState(0);
  const [progressStage, setProgressStage] = useState("");
  const [progressDetail, setProgressDetail] = useState("");
  const [progressEta, setProgressEta] = useState<number | null>(null);

  const [ocrTracks, setOcrTracks] = useState<Candidate[]>([]);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrError, setOcrError] = useState<string | null>(null);

  const [playlistTracks, setPlaylistTracks] = useState<Candidate[]>([]);
  const [playlistLoading, setPlaylistLoading] = useState(false);
  const [playlistError, setPlaylistError] = useState<string | null>(null);
  const [playlistSource, setPlaylistSource] = useState<"spotify" | "lastfm" | null>(null);
  const [playlistSaving, setPlaylistSaving] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [spotifyResults, setSpotifyResults] = useState<Candidate[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [recapHistory, setRecapHistory] = useState<RecapHistoryEntry[]>([]);
  const [recapHistoryLoading, setRecapHistoryLoading] = useState(false);
  const [recapHistoryError, setRecapHistoryError] = useState<string | null>(null);
  const [selectedRecapId, setSelectedRecapId] = useState<string | null>(null);
  const [selectedRecapSlides, setSelectedRecapSlides] = useState<string[]>([]);
  const [selectedRecapLoading, setSelectedRecapLoading] = useState(false);

  const setApiBase = useCallback((v: string) => {
    let normalized = v.trim();
    if (normalized) {
      if (!/^https?:\/\//i.test(normalized)) {
        normalized = `http://${normalized}`;
      }
      normalized = normalized.replace(/\/+$/, "");
    } else {
      normalized = DEFAULT_API_BASE;
    }
    setApiBaseRaw(normalized);
    localStorage.setItem(API_BASE_KEY, normalized);
  }, []);

  const fetchAbortRef = useRef<AbortController | null>(null);

  const refetch = useCallback(async () => {
    // Cancel any in-flight candidate fetch so stale responses can't overwrite
    // the result of a newer timeframe selection.
    fetchAbortRef.current?.abort();
    const controller = new AbortController();
    fetchAbortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const list = await fetchCandidates(apiBase, days, controller.signal);
      setCandidates(() => {
        const existingKeys = new Set(list.map((c) => c.track_key));
        const toKeep = selectedTracksRef.current.filter((c) => !existingKeys.has(c.track_key));
        return [...list, ...toKeep];
      });
      setSummary(null);
      setSlideUrls([]);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to fetch candidates.");
    } finally {
      setLoading(false);
    }
  }, [apiBase, days]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const sortedCandidates = useMemo(() => {
    const list = [...candidates];
    if (sortBy === "plays") {
      return list.sort(
        (a, b) =>
          b.play_count - a.play_count ||
          b.last_played_unix - a.last_played_unix,
      );
    }
    return list.sort(
      (a, b) =>
        underratedScore(b) - underratedScore(a) ||
        b.last_played_unix - a.last_played_unix,
    );
  }, [candidates, sortBy]);

  const selectedTracks = useMemo(
    () =>
      selectedOrder
        .map((key) => candidates.find((c) => c.track_key === key))
        .filter((c): c is Candidate => c !== undefined),
    [selectedOrder, candidates],
  );

  const selectedTracksRef = useRef<Candidate[]>([]);
  useEffect(() => {
    selectedTracksRef.current = selectedTracks;
  }, [selectedTracks]);

  const isSelected = useCallback(
    (key: string) => selectedKeys.has(key),
    [selectedKeys],
  );

  const toggleSelect = useCallback((key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    setSelectedOrder((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
    setSummary(null);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedKeys(new Set());
    setSelectedOrder([]);
    setSummary(null);
  }, []);

  const applyPreset = useCallback(
    (presetId: string, mode: "overwrite" | "fill" = "overwrite") => {
      const preset = PRESETS.find((p) => p.id === presetId);
      if (!preset) return;
      if (mode === "fill") {
        const keys = preset.fn(candidates, candidates.length);
        const newOrder = [...selectedOrder];
        const newKeys = new Set(selectedKeys);
        for (const key of keys) {
          if (newOrder.length >= quickSelectCount) break;
          if (!newKeys.has(key)) {
            newKeys.add(key);
            newOrder.push(key);
          }
        }
        setSelectedKeys(newKeys);
        setSelectedOrder(newOrder);
      } else {
        const keys = preset.fn(candidates, quickSelectCount);
        setSelectedKeys(new Set(keys));
        setSelectedOrder(keys);
      }
      setSummary(null);
    },
    [candidates, quickSelectCount, selectedKeys, selectedOrder],
  );

  const moveSelected = useCallback((key: string, dir: -1 | 1) => {
    setSelectedOrder((prev) => {
      const i = prev.indexOf(key);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
    setSummary(null);
  }, []);

  const swapSelected = useCallback((oldKey: string, newKey: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      next.delete(oldKey);
      next.add(newKey);
      return next;
    });
    setSelectedOrder((prev) => prev.map((k) => (k === oldKey ? newKey : k)));
    setSummary(null);
  }, []);

  const replaceWithRandom = useCallback(
    (oldKey: string) => {
      const pool = candidates.filter((c) => !selectedKeys.has(c.track_key));
      if (pool.length === 0) return;
      const pick = pool[Math.floor(Math.random() * pool.length)];
      swapSelected(oldKey, pick.track_key);
    },
    [candidates, selectedKeys, swapSelected],
  );

  const slideCapacity = layout === "3x3" ? 9 : (layout === "4x4" ? 16 : 4);
  const slideCount = Math.floor(selectedKeys.size / slideCapacity);
  const leftover = selectedKeys.size % slideCapacity;

  const saveArtLinkFor = useCallback(
    async (track: { artist: string; title: string; track_key: string }, url: string) => {
      setError(null);
      try {
        const resp = await fetch(`${apiBase}/api/art-test/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            artist: track.artist,
            title: track.title,
            album_art_url: url,
          }),
        });
        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.error || `Failed to save cover art URL (${resp.status}).`);
        }
        // Optimistically update candidates
        setCandidates((prev) =>
          prev.map((c) =>
            c.track_key === track.track_key
              ? { ...c, album_art_url: url }
              : c,
          ),
        );
        // Clear from missingCovers list
        setMissingCovers((prev) => prev.filter((t) => t.track_key !== track.track_key));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save cover art URL.");
      }
    },
    [apiBase],
  );

  const generate = useCallback(async () => {
    if (selectedTracks.length === 0 && !coverOnly) return;
    setGenerating(true);
    setError(null);
    setSummary(null);
    setSlideUrls([]);
    setMissingCovers([]);
    setUnconfirmedCovers([]);
    setProgress(0);
    setProgressStage("");
    setProgressDetail("");
    setProgressEta(null);
    try {
      const result = await generateRecapStream(apiBase, {
        tracks: selectedTracks,
        cover_title: (includeCover || coverOnly) ? coverTitle : null,
        cover_subtitle: (includeCover || coverOnly) ? coverSubtitle : null,
        cover_theme: (includeCover || coverOnly) ? coverTheme : null,
        watermark: watermark.trim() || null,
        cover_pool: candidates.map((c) => c.album_art_url).filter(Boolean),
        layout,
        cover_only: coverOnly,
        cover_columns: coverColumns,
        cover_rows: coverRows,
        width: slideWidth,
        height: slideHeight,
      }, (evt) => {
        setProgress(evt.progress);
        setProgressStage(evt.stage);
        setProgressDetail(evt.detail);
        setProgressEta(evt.eta);
      });
      setSummary(result.summary);
      setSlideUrls(result.slides);
    } catch (err) {
      if (err instanceof UnconfirmedCoverError) {
        setUnconfirmedCovers(err.unconfirmedCovers);
        setError("Some tracks only have iTunes covers. Please confirm or replace them below.");
      } else if (err instanceof MissingCoverError) {
        setMissingCovers(err.missingCovers);
        setError("Some tracks are missing Spotify album covers. Please upload or link them below.");
      } else {
        setError(err instanceof Error ? err.message : "Failed to generate slideshow.");
      }
    } finally {
      setGenerating(false);
    }
  }, [
    apiBase,
    selectedTracks,
    includeCover,
    coverTitle,
    coverSubtitle,
    coverTheme,
    watermark,
    candidates,
    layout,
    coverOnly,
    coverColumns,
    slideWidth,
    slideHeight,
  ]);

  const uploadArtFor = useCallback(
    async (track: Candidate, file: File) => {
      setError(null);
      try {
        const { url } = await uploadArt(apiBase, track, file);
        // Optimistically swap the art (cache-bust so the new image shows).
        setCandidates((prev) =>
          prev.map((c) =>
            c.track_key === track.track_key
              ? { ...c, album_art_url: `${url}?t=${Date.now()}` }
              : c,
          ),
        );
        // Clear from missingCovers list
        setMissingCovers((prev) => prev.filter((t) => t.track_key !== track.track_key));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to upload artwork.");
      }
    },
    [apiBase],
  );

  const confirmItunesCover = useCallback(
    async (track: { artist: string; title: string; track_key: string; itunes_url: string }, accept: boolean) => {
      if (accept) {
        // Save the iTunes URL so future generate calls use it as stored URL.
        try {
          await saveItunesUrl(apiBase, track, track.itunes_url);
          // Optimistically update the candidate's art
          setCandidates((prev) =>
            prev.map((c) =>
              c.track_key === track.track_key ? { ...c, album_art_url: track.itunes_url } : c,
            ),
          );
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to save cover.");
          return;
        }
      } else {
        // Move to missingCovers so the upload/link row appears
        setMissingCovers((prev) => [...prev, { artist: track.artist, title: track.title, track_key: track.track_key }]);
      }
      setUnconfirmedCovers((prev) => prev.filter((t) => t.track_key !== track.track_key));
    },
    [apiBase],
  );

  const runOcr = useCallback(
    async (files: File[]) => {
      setOcrLoading(true);
      setOcrError(null);
      try {
        const promises = files.map((file) => uploadOcrScreenshot(apiBase, file));
        const results = await Promise.all(promises);
        const allNewTracks = results.flat();

        setOcrTracks((prev) => {
          const existingKeys = new Set(prev.map((t) => t.track_key));
          const seenNew = new Set<string>();
          const uniqueNew: Candidate[] = [];
          for (const track of allNewTracks) {
            if (!existingKeys.has(track.track_key) && !seenNew.has(track.track_key)) {
              seenNew.add(track.track_key);
              uniqueNew.push(track);
            }
          }
          return [...prev, ...uniqueNew];
        });
      } catch (err) {
        setOcrError(err instanceof Error ? err.message : "OCR failed.");
      } finally {
        setOcrLoading(false);
      }
    },
    [apiBase],
  );

  const addOcrTracksToSelection = useCallback(() => {
    setOcrTracks((prev) => {
      const newKeys: string[] = [];
      const newTracks: Candidate[] = [];
      for (const t of prev) {
        if (!selectedKeys.has(t.track_key)) {
          newKeys.push(t.track_key);
          newTracks.push(t);
        }
      }
      // Merge OCR tracks into candidates so they're selectable
      setCandidates((cands) => {
        const existingKeys = new Set(cands.map((c) => c.track_key));
        const toAdd = newTracks.filter((t) => !existingKeys.has(t.track_key));
        return [...cands, ...toAdd];
      });
      setSelectedKeys((prev) => {
        const next = new Set(prev);
        for (const k of newKeys) next.add(k);
        return next;
      });
      setSelectedOrder((prev) => [...prev, ...newKeys]);
      return [];
    });
  }, [selectedKeys]);

  const clearOcrTracks = useCallback(() => {
    setOcrTracks([]);
    setOcrError(null);
  }, []);

  const parsePlaylistLink = useCallback(
    async (url: string) => {
      setPlaylistLoading(true);
      setPlaylistError(null);
      try {
        const result = await parsePlaylist(apiBase, url);
        setPlaylistSource(result.source);
        setPlaylistTracks(result.tracks);
        if (result.tracks.length === 0) {
          setPlaylistError("No tracks found in that playlist.");
        }
      } catch (err) {
        setPlaylistTracks([]);
        setPlaylistSource(null);
        setPlaylistError(err instanceof Error ? err.message : "Failed to parse playlist.");
      } finally {
        setPlaylistLoading(false);
      }
    },
    [apiBase],
  );

  const addPlaylistTracksToSelection = useCallback(() => {
    setPlaylistTracks((prev) => {
      const newKeys: string[] = [];
      const newTracks: Candidate[] = [];
      for (const t of prev) {
        if (!selectedKeys.has(t.track_key)) {
          newKeys.push(t.track_key);
          newTracks.push(t);
        }
      }
      // Merge playlist tracks into candidates so they're selectable & orderable.
      setCandidates((cands) => {
        const existingKeys = new Set(cands.map((c) => c.track_key));
        const toAdd = newTracks.filter((t) => !existingKeys.has(t.track_key));
        return [...cands, ...toAdd];
      });
      setSelectedKeys((prevSel) => {
        const next = new Set(prevSel);
        for (const k of newKeys) next.add(k);
        return next;
      });
      setSelectedOrder((prevOrder) => [...prevOrder, ...newKeys]);
      return [];
    });
  }, [selectedKeys]);

  const clearPlaylistTracks = useCallback(() => {
    setPlaylistTracks([]);
    setPlaylistError(null);
    setPlaylistSource(null);
  }, []);

  const saveSelectionToSpotify = useCallback(
    async (name: string): Promise<string | null> => {
      if (selectedTracks.length === 0) return null;
      setPlaylistSaving(true);
      setPlaylistError(null);
      try {
        const result = await savePlaylist(apiBase, selectedTracks, name.trim() || undefined);
        return result.url;
      } catch (err) {
        setPlaylistError(err instanceof Error ? err.message : "Failed to save playlist.");
        return null;
      } finally {
        setPlaylistSaving(false);
      }
    },
    [apiBase, selectedTracks],
  );

  const loadRecapHistory = useCallback(async () => {
    setRecapHistoryLoading(true);
    setRecapHistoryError(null);
    try {
      const history = await fetchRecapHistory(apiBase);
      setRecapHistory(history);
    } catch (err) {
      setRecapHistoryError(err instanceof Error ? err.message : "Failed to load recap history.");
    } finally {
      setRecapHistoryLoading(false);
    }
  }, [apiBase]);

  const selectRecap = useCallback(
    async (recapId: string | null) => {
      setSelectedRecapId(recapId);
      setSelectedRecapSlides([]);
      if (!recapId) return;
      setSelectedRecapLoading(true);
      try {
        const slides = await fetchRecapSlides(apiBase, recapId);
        setSelectedRecapSlides(slides);
      } catch {
        setSelectedRecapSlides([]);
      } finally {
        setSelectedRecapLoading(false);
      }
    },
    [apiBase],
  );

  const runSpotifySearch = useCallback(
    async (q: string) => {
      const query = q.trim();
      if (!query) return;
      setSearchLoading(true);
      setSearchError(null);
      try {
        const results = await searchSpotify(apiBase, query);
        setSpotifyResults(results);
        if (results.length === 0) setSearchError("No Spotify results for that query.");
      } catch (err) {
        setSpotifyResults([]);
        setSearchError(err instanceof Error ? err.message : "Spotify search failed.");
      } finally {
        setSearchLoading(false);
      }
    },
    [apiBase],
  );

  const clearSearch = useCallback(() => {
    setSearchQuery("");
    setSpotifyResults([]);
    setSearchError(null);
  }, []);

  // Merge a candidate into the pool (if new) and select it. Shared by Spotify
  // results and manual entries.
  const addCandidateToSelection = useCallback((cand: Candidate) => {
    setCandidates((prev) =>
      prev.some((c) => c.track_key === cand.track_key) ? prev : [...prev, cand],
    );
    setSelectedKeys((prev) => {
      if (prev.has(cand.track_key)) return prev;
      const next = new Set(prev);
      next.add(cand.track_key);
      return next;
    });
    setSelectedOrder((prev) =>
      prev.includes(cand.track_key) ? prev : [...prev, cand.track_key],
    );
    setSummary(null);
  }, []);

  const addSearchTrack = useCallback(
    (track: Candidate) => {
      addCandidateToSelection(withCandidateDefaults(track));
    },
    [addCandidateToSelection],
  );

  const addCustomTrack = useCallback(
    (input: { title: string; artist: string; albumArtUrl: string }) => {
      const title = input.title.trim();
      const artist = input.artist.trim();
      if (!title || !artist) return;
      const track_key = `${normalizeKeyPart(artist)}\t${normalizeKeyPart(title)}`;
      addCandidateToSelection(
        withCandidateDefaults({
          track_key,
          title,
          artist,
          album_art_url: input.albumArtUrl.trim(),
        }),
      );
    },
    [addCandidateToSelection],
  );

  return {
    apiBase,
    setApiBase,
    days,
    setDays,
    sortBy,
    setSortBy,
    candidates,
    sortedCandidates,
    loading,
    error,
    refetch,
    selectedKeys,
    selectedOrder,
    selectedTracks,
    isSelected,
    toggleSelect,
    clearSelection,
    quickSelectCount,
    setQuickSelectCount,
    applyPreset,
    moveSelected,
    swapSelected,
    replaceWithRandom,
    includeCover,
    setIncludeCover,
    coverTitle,
    setCoverTitle,
    coverSubtitle,
    setCoverSubtitle,
    coverTheme,
    setCoverTheme,
    watermark,
    setWatermark,
    coverOnly,
    setCoverOnly,
    coverColumns,
    setCoverColumns,
    coverRows,
    setCoverRows,
    slideWidth,
    setSlideWidth,
    slideHeight,
    setSlideHeight,
    lockAspectRatio,
    setLockAspectRatio,
    toggleLockAspectRatio,
    generating,
    summary,
    slideUrls,
    slideCount,
    leftover,
    generate,
    layout,
    setLayout,
    progress,
    progressStage,
    progressDetail,
    progressEta,
    uploadArtFor,
    missingCovers,
    setMissingCovers,
    saveArtLinkFor,
    unconfirmedCovers,
    confirmItunesCover,
    ocrTracks,
    ocrLoading,
    ocrError,
    runOcr,
    addOcrTracksToSelection,
    clearOcrTracks,
    playlistTracks,
    playlistLoading,
    playlistError,
    playlistSource,
    parsePlaylistLink,
    addPlaylistTracksToSelection,
    clearPlaylistTracks,
    saveSelectionToSpotify,
    playlistSaving,
    searchQuery,
    setSearchQuery,
    spotifyResults,
    searchLoading,
    searchError,
    runSpotifySearch,
    clearSearch,
    addSearchTrack,
    addCustomTrack,
    recapHistory,
    recapHistoryLoading,
    recapHistoryError,
    loadRecapHistory,
    selectedRecapId,
    selectedRecapSlides,
    selectedRecapLoading,
    selectRecap,
  };
}
