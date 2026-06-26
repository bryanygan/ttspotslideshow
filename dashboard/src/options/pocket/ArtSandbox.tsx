import { useEffect, useState, useCallback, useMemo } from "react";

interface Track {
  title: string;
  artist: string;
  album_art_url: string;
}

interface ArtSandboxProps {
  apiBase: string;
}

export function ArtSandbox({ apiBase }: ArtSandboxProps) {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [spotifyUrl, setSpotifyUrl] = useState<string | null>(null);
  const [itunesUrl, setItunesUrl] = useState<string | null>(null);
  const [loadingArt, setLoadingArt] = useState<boolean>(false);
  const [loadingTracks, setLoadingTracks] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Choices mapping index -> 'spotify' | 'itunes' | 'both' | 'wrong'
  const [choices, setChoices] = useState<Record<number, "spotify" | "itunes" | "both" | "wrong">>({});

  const fetchTracks = useCallback(async () => {
    setLoadingTracks(true);
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/art-test/tracks`);
      if (!resp.ok) throw new Error(`HTTP error ${resp.status}`);
      const data = await resp.json();
      setTracks(data.tracks || []);
      setCurrentIndex(0);
      setChoices({});
    } catch (err: any) {
      setError(err.message || "Failed to load test tracks.");
    } finally {
      setLoadingTracks(false);
    }
  }, [apiBase]);

  const resolveCurrentTrack = useCallback(async (track: Track) => {
    setLoadingArt(true);
    setSpotifyUrl(null);
    setItunesUrl(null);
    try {
      const resp = await fetch(
        `${apiBase}/api/art-test/resolve?artist=${encodeURIComponent(
          track.artist
        )}&title=${encodeURIComponent(track.title)}`
      );
      if (!resp.ok) throw new Error(`HTTP error ${resp.status}`);
      const data = await resp.json();
      setSpotifyUrl(data.spotify_url);
      setItunesUrl(data.itunes_url);
    } catch (err) {
      console.error("Failed to resolve art:", err);
    } finally {
      setLoadingArt(false);
    }
  }, [apiBase]);

  useEffect(() => {
    fetchTracks();
  }, [fetchTracks]);

  useEffect(() => {
    if (tracks.length > 0 && currentIndex < tracks.length) {
      resolveCurrentTrack(tracks[currentIndex]);
    }
  }, [currentIndex, tracks, resolveCurrentTrack]);

  const handleSelectOption = useCallback(
    async (option: "spotify" | "itunes" | "both" | "wrong") => {
      if (tracks.length === 0 || currentIndex >= tracks.length) return;
      const track = tracks[currentIndex];

      // Update choices local state immediately
      setChoices((prev) => ({ ...prev, [currentIndex]: option }));

      // Determine what URL we are saving to database
      let saveUrl = "";
      if (option === "spotify" || option === "both") {
        saveUrl = spotifyUrl || "";
      } else if (option === "itunes") {
        saveUrl = itunesUrl || "";
      }

      // Save to backend database asynchronously
      try {
        await fetch(`${apiBase}/api/art-test/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            artist: track.artist,
            title: track.title,
            album_art_url: saveUrl,
          }),
        });
      } catch (err) {
        console.error("Failed to save cover choice:", err);
      }

      // Auto advance
      if (currentIndex < tracks.length - 1) {
        setCurrentIndex((prev) => prev + 1);
      }
    },
    [currentIndex, tracks, spotifyUrl, itunesUrl, apiBase]
  );

  // Keyboard controls listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        document.activeElement?.tagName === "INPUT" ||
        document.activeElement?.tagName === "TEXTAREA"
      ) {
        return;
      }

      switch (e.key) {
        case "1":
          handleSelectOption("spotify");
          break;
        case "2":
          handleSelectOption("itunes");
          break;
        case "3":
          handleSelectOption("both");
          break;
        case "4":
          handleSelectOption("wrong");
          break;
        case "ArrowLeft":
          if (currentIndex > 0) setCurrentIndex((prev) => prev - 1);
          break;
        case "ArrowRight":
          if (currentIndex < tracks.length - 1) setCurrentIndex((prev) => prev + 1);
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentIndex, tracks.length, handleSelectOption]);

  const stats = useMemo(() => {
    const total = Object.keys(choices).length;
    if (total === 0) {
      return {
        spotify: 0,
        itunes: 0,
        both: 0,
        wrong: 0,
        spotifyCount: 0,
        itunesCount: 0,
        bothCount: 0,
        wrongCount: 0,
        total: 0,
      };
    }

    let spotifyCount = 0;
    let itunesCount = 0;
    let bothCount = 0;
    let wrongCount = 0;

    Object.values(choices).forEach((c) => {
      if (c === "spotify") spotifyCount++;
      if (c === "itunes") itunesCount++;
      if (c === "both") bothCount++;
      if (c === "wrong") wrongCount++;
    });

    return {
      spotify: Math.round((spotifyCount / total) * 100),
      itunes: Math.round((itunesCount / total) * 100),
      both: Math.round((bothCount / total) * 100),
      wrong: Math.round((wrongCount / total) * 100),
      spotifyCount,
      itunesCount,
      bothCount,
      wrongCount,
      total,
    };
  }, [choices]);

  const currentTrack = tracks[currentIndex];

  if (loadingTracks && tracks.length === 0) {
    return (
      <div className="flex min-h-[calc(100vh-2.75rem)] flex-col items-center justify-center bg-zinc-950 px-4 text-zinc-100">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-violet-600 border-t-transparent" />
        <span className="mt-4 text-sm text-zinc-400">Loading 100 test tracks from DB...</span>
      </div>
    );
  }

  if (error && tracks.length === 0) {
    return (
      <div className="flex min-h-[calc(100vh-2.75rem)] flex-col items-center justify-center bg-zinc-950 px-4 text-zinc-100">
        <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center max-w-md">
          <p className="text-sm font-semibold text-red-400">Error Loading Sandbox</p>
          <p className="mt-2 text-xs text-zinc-400 leading-relaxed">{error}</p>
          <button
            onClick={fetchTracks}
            className="mt-4 rounded-lg bg-red-950 hover:bg-red-900 border border-red-800 px-4 py-2 text-xs font-semibold text-red-300 transition-colors"
          >
            Retry Loading
          </button>
        </div>
      </div>
    );
  }

  if (tracks.length === 0) {
    return (
      <div className="flex min-h-[calc(100vh-2.75rem)] flex-col items-center justify-center bg-zinc-950 px-4 text-zinc-100">
        <p className="text-zinc-400">No tracks available in database to run evaluation.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 text-zinc-100 flex flex-col gap-6">
      {/* Header Panel */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border border-white/5 bg-zinc-900/30 rounded-2xl p-5 backdrop-blur-md">
        <div>
          <h2 className="text-lg font-bold bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
            Album Art Sandbox
          </h2>
          <p className="text-xs text-zinc-400 mt-1 leading-relaxed max-w-xl">
            Evaluate the resolution and accuracy of Spotify Web API covers vs iTunes search covers. Clicking a cover saves it as the corrected version in your SQLite database.
          </p>
        </div>
        <button
          onClick={fetchTracks}
          className="rounded-xl bg-zinc-800/80 hover:bg-zinc-800 border border-zinc-700/60 px-4 py-2 text-xs font-bold text-zinc-300 transition-all shrink-0 hover:text-white"
        >
          Load New 100 Random Tracks
        </button>
      </div>

      {/* Progress & Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Progress Bar Panel */}
        <div className="md:col-span-2 border border-white/5 bg-zinc-900/30 rounded-2xl p-4 flex flex-col justify-between">
          <div className="flex justify-between items-center text-xs text-zinc-400 mb-2">
            <span className="font-semibold text-violet-400">Progress</span>
            <span>
              {stats.total} / {tracks.length} Evaluated
            </span>
          </div>
          <div className="w-full bg-zinc-800 h-2.5 rounded-full overflow-hidden border border-zinc-700">
            <div
              className="bg-gradient-to-r from-violet-500 to-fuchsia-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${(stats.total / tracks.length) * 100}%` }}
            />
          </div>
          <span className="text-[10px] text-zinc-500 mt-2 block">
            Keyboard Controls: <strong>[1]</strong> Spotify, <strong>[2]</strong> iTunes, <strong>[3]</strong> Both Correct, <strong>[4]</strong> Both Wrong. Arrow keys navigate.
          </span>
        </div>

        {/* Real-time stats */}
        <div className="md:col-span-2 border border-white/5 bg-zinc-900/30 rounded-2xl p-4 grid grid-cols-4 gap-2 text-center items-center">
          <div className="flex flex-col">
            <span className="text-lg font-bold text-green-400">{stats.bothCount}</span>
            <span className="text-[10px] text-zinc-500 leading-snug uppercase tracking-wider">Both Ok (3)</span>
          </div>
          <div className="flex flex-col border-l border-white/5">
            <span className="text-lg font-bold text-violet-400">{stats.spotifyCount}</span>
            <span className="text-[10px] text-zinc-500 leading-snug uppercase tracking-wider">Spotify Only (1)</span>
          </div>
          <div className="flex flex-col border-l border-white/5">
            <span className="text-lg font-bold text-fuchsia-400">{stats.itunesCount}</span>
            <span className="text-[10px] text-zinc-500 leading-snug uppercase tracking-wider">iTunes Only (2)</span>
          </div>
          <div className="flex flex-col border-l border-white/5">
            <span className="text-lg font-bold text-red-400">{stats.wrongCount}</span>
            <span className="text-[10px] text-zinc-500 leading-snug uppercase tracking-wider">Both Bad (4)</span>
          </div>
        </div>
      </div>

      {/* Main Evaluator UI */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
        {/* Left Column: Spotify Cover */}
        <div
          onClick={() => handleSelectOption("spotify")}
          className={`group flex flex-col overflow-hidden rounded-2xl border transition-all cursor-pointer select-none bg-zinc-900/40 hover:bg-zinc-900/60 ${
            choices[currentIndex] === "spotify"
              ? "border-violet-500 shadow-lg shadow-violet-500/10"
              : "border-white/5 hover:border-violet-500/40"
          }`}
        >
          <div className="flex justify-between items-center p-3 border-b border-white/5 bg-zinc-950/40">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-green-400">
              <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
              [1] Spotify Search API
            </span>
            <span className="text-[10px] font-semibold text-zinc-500 uppercase">Max 640×640</span>
          </div>
          <div className="flex-1 flex items-center justify-center p-6 bg-zinc-950/20 aspect-square relative">
            {loadingArt ? (
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-violet-600/30 border-t-violet-500" />
            ) : spotifyUrl ? (
              <img
                src={spotifyUrl}
                alt="Spotify cover search"
                className="w-full h-full object-contain rounded-xl shadow-lg border border-white/5 transition-transform duration-200 group-hover:scale-[1.02]"
              />
            ) : (
              <span className="text-xs text-zinc-500">No cover resolved on Spotify</span>
            )}
          </div>
          <div className="p-3 text-center text-xs font-medium text-zinc-400 border-t border-white/5 bg-zinc-950/40 group-hover:text-violet-300 transition-colors">
            Click here if **Spotify Cover** is correct
          </div>
        </div>

        {/* Right Column: iTunes Cover */}
        <div
          onClick={() => handleSelectOption("itunes")}
          className={`group flex flex-col overflow-hidden rounded-2xl border transition-all cursor-pointer select-none bg-zinc-900/40 hover:bg-zinc-900/60 ${
            choices[currentIndex] === "itunes"
              ? "border-fuchsia-500 shadow-lg shadow-fuchsia-500/10"
              : "border-white/5 hover:border-fuchsia-500/40"
          }`}
        >
          <div className="flex justify-between items-center p-3 border-b border-white/5 bg-zinc-950/40">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-sky-400">
              <span className="h-2 w-2 rounded-full bg-sky-400 animate-pulse" />
              [2] iTunes Search API
            </span>
            <span className="text-[10px] font-semibold text-zinc-500 uppercase text-right">Max 1000×1000</span>
          </div>
          <div className="flex-1 flex items-center justify-center p-6 bg-zinc-950/20 aspect-square relative">
            {loadingArt ? (
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-fuchsia-600/30 border-t-fuchsia-500" />
            ) : itunesUrl ? (
              <img
                src={itunesUrl}
                alt="iTunes cover search"
                className="w-full h-full object-contain rounded-xl shadow-lg border border-white/5 transition-transform duration-200 group-hover:scale-[1.02]"
              />
            ) : (
              <span className="text-xs text-zinc-500">No cover resolved on iTunes</span>
            )}
          </div>
          <div className="p-3 text-center text-xs font-medium text-zinc-400 border-t border-white/5 bg-zinc-950/40 group-hover:text-fuchsia-300 transition-colors">
            Click here if **iTunes Cover** is correct
          </div>
        </div>
      </div>

      {/* Active Track Title & Actions */}
      <div className="border border-white/5 bg-zinc-900/30 rounded-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-900/20 border border-violet-500/10 text-xs font-bold text-violet-400">
              {currentIndex + 1}
            </span>
            <div>
              <p className="text-sm font-bold text-zinc-100">{currentTrack?.title}</p>
              <p className="text-xs text-zinc-400 font-medium mt-0.5">{currentTrack?.artist}</p>
            </div>
          </div>
          {currentTrack?.album_art_url && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold text-zinc-500 uppercase">Original Cover:</span>
              <img
                src={currentTrack.album_art_url}
                alt="Original cover"
                className="h-8 w-8 rounded-md object-cover border border-white/5"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            </div>
          )}
        </div>

        {/* Global Action Buttons */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <button
            onClick={() => handleSelectOption("spotify")}
            className={`py-2.5 px-4 rounded-xl text-xs font-bold border transition-all ${
              choices[currentIndex] === "spotify"
                ? "bg-violet-600 border-violet-500 text-white"
                : "bg-zinc-900/60 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white"
            }`}
          >
            [1] Spotify Correct
          </button>
          <button
            onClick={() => handleSelectOption("itunes")}
            className={`py-2.5 px-4 rounded-xl text-xs font-bold border transition-all ${
              choices[currentIndex] === "itunes"
                ? "bg-fuchsia-600 border-fuchsia-500 text-white"
                : "bg-zinc-900/60 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white"
            }`}
          >
            [2] iTunes Correct
          </button>
          <button
            onClick={() => handleSelectOption("both")}
            className={`py-2.5 px-4 rounded-xl text-xs font-bold border transition-all ${
              choices[currentIndex] === "both"
                ? "bg-green-600 border-green-500 text-white"
                : "bg-zinc-900/60 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white"
            }`}
          >
            [3] Both Correct & Same
          </button>
          <button
            onClick={() => handleSelectOption("wrong")}
            className={`py-2.5 px-4 rounded-xl text-xs font-bold border transition-all ${
              choices[currentIndex] === "wrong"
                ? "bg-red-950 hover:bg-red-900 border-red-800 text-red-300"
                : "bg-zinc-900/60 hover:bg-zinc-800 border-zinc-800 text-zinc-300 hover:text-white"
            }`}
          >
            [4] Both Wrong / Skip
          </button>
        </div>

        {/* Back and Forth navigation */}
        <div className="flex justify-between items-center border-t border-white/5 pt-4">
          <button
            disabled={currentIndex === 0}
            onClick={() => setCurrentIndex((prev) => prev - 1)}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white transition-colors disabled:opacity-30 disabled:pointer-events-none font-semibold cursor-pointer"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Previous Song
          </button>
          <button
            disabled={currentIndex === tracks.length - 1}
            onClick={() => setCurrentIndex((prev) => prev + 1)}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white transition-colors disabled:opacity-30 disabled:pointer-events-none font-semibold cursor-pointer"
          >
            Next Song
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>

      {/* Grid of All Tracks */}
      <div className="border border-white/5 bg-zinc-900/30 rounded-2xl p-5 flex flex-col gap-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
          Sandbox Track Pool ({tracks.length})
        </h3>
        <div className="grid grid-cols-5 sm:grid-cols-10 gap-2 max-h-[140px] overflow-y-auto pr-2">
          {tracks.map((_, i) => {
            const status = choices[i];
            let dotColor = "bg-zinc-800 border-zinc-700/60";
            if (status === "both") dotColor = "bg-green-600/30 border-green-500/40 text-green-300";
            if (status === "spotify") dotColor = "bg-violet-600/30 border-violet-500/40 text-violet-300";
            if (status === "itunes") dotColor = "bg-fuchsia-600/30 border-fuchsia-500/40 text-fuchsia-300";
            if (status === "wrong") dotColor = "bg-red-950/30 border-red-800 text-red-300";

            return (
              <button
                key={i}
                onClick={() => setCurrentIndex(i)}
                className={`h-8 rounded-lg flex items-center justify-center text-xs font-bold border transition-all ${dotColor} ${
                  currentIndex === i ? "ring-2 ring-violet-500 scale-[1.05]" : "opacity-80 hover:opacity-100"
                }`}
              >
                {i + 1}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
