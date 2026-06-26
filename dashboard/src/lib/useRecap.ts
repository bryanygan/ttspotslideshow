import { useCallback, useEffect, useMemo, useState } from "react";
import type { Candidate, GenerateSummary, SortBy } from "./types";
import { underratedScore } from "./types";
import {
  fetchCandidates,
  generateRecap,
  uploadArt,
} from "./api";
import { PRESETS } from "./presets";

const API_BASE_KEY = "api_base";
const DEFAULT_API_BASE = "http://localhost:8000";

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
  applyPreset: (presetId: string) => void;

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

  // Generation
  generating: boolean;
  summary: GenerateSummary | null;
  slideUrls: string[];
  slideCount: number;
  leftover: number;
  generate: () => void;

  uploadArtFor: (track: Candidate, file: File) => void;
  missingCovers: Array<{ artist: string; title: string; track_key: string }>;
  setMissingCovers: (v: Array<{ artist: string; title: string; track_key: string }>) => void;
  saveArtLinkFor: (track: { artist: string; title: string; track_key: string }, url: string) => Promise<void>;
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

  const [includeCover, setIncludeCover] = useState(true);
  const [coverTitle, setCoverTitle] = useState("");
  const [coverSubtitle, setCoverSubtitle] = useState("");
  const [coverTheme, setCoverTheme] = useState("none");
  const [watermark, setWatermark] = useState("");

  const [generating, setGenerating] = useState(false);
  const [summary, setSummary] = useState<GenerateSummary | null>(null);
  const [slideUrls, setSlideUrls] = useState<string[]>([]);
  const [missingCovers, setMissingCovers] = useState<Array<{ artist: string; title: string; track_key: string }>>([]);

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

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchCandidates(apiBase, days);
      setCandidates(list);
      setSelectedKeys(new Set());
      setSelectedOrder([]);
      setSummary(null);
      setSlideUrls([]);
    } catch (err) {
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
    (presetId: string) => {
      const preset = PRESETS.find((p) => p.id === presetId);
      if (!preset) return;
      const keys = preset.fn(candidates, quickSelectCount);
      setSelectedKeys(new Set(keys));
      setSelectedOrder(keys);
      setSummary(null);
    },
    [candidates, quickSelectCount],
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

  const slideCount = Math.floor(selectedKeys.size / 4);
  const leftover = selectedKeys.size % 4;

  const saveArtLinkFor = useCallback(
    async (track: { artist: string; title: string; track_key: string }, url: string) => {
      setError(null);
      try {
        await fetch(`${apiBase}/api/art-test/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            artist: track.artist,
            title: track.title,
            album_art_url: url,
          }),
        });
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
    if (selectedTracks.length === 0) return;
    setGenerating(true);
    setError(null);
    setSummary(null);
    setSlideUrls([]);
    setMissingCovers([]);
    try {
      const result = await generateRecap(apiBase, {
        tracks: selectedTracks,
        cover_title: includeCover ? coverTitle : null,
        cover_subtitle: includeCover ? coverSubtitle : null,
        cover_theme: includeCover ? coverTheme : null,
        watermark: watermark.trim() || null,
        cover_pool: candidates.map((c) => c.album_art_url).filter(Boolean),
      });
      setSummary(result.summary);
      setSlideUrls(result.slides);
    } catch (err) {
      if (err instanceof Error && err.name === "MissingCoverError") {
        setMissingCovers((err as any).missingCovers);
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
    generating,
    summary,
    slideUrls,
    slideCount,
    leftover,
    generate,
    uploadArtFor,
    missingCovers,
    setMissingCovers,
    saveArtLinkFor,
  };
}
