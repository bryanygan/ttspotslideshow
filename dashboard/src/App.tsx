import { useState, useEffect } from 'react';

interface Candidate {
  track_key: string;
  track_id: string;
  title: string;
  artist: string;
  album_art_url: string;
  play_count: number;
  last_played_unix: number;
  primary_bucket: string;
  popularity: number;
  last_featured: string | null;
}

function App() {
  const [apiBase, setApiBase] = useState<string>(() => {
    return localStorage.getItem('api_base') || 'http://localhost:8000';
  });
  const [days, setDays] = useState<number>(7);
  const [sortBy, setSortBy] = useState<'plays' | 'underrated'>('plays');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successSummary, setSuccessSummary] = useState<any>(null);
  const [slideUrls, setSlideUrls] = useState<string[]>([]);

  useEffect(() => {
    fetchCandidates();
    // Re-fetch when the window OR the backend URL changes (fixes a stale-closure
    // bug where editing the API base didn't trigger a refetch).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, apiBase]);

  const fetchCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/candidates?days=${days}`);
      if (!resp.ok) throw new Error(`HTTP error ${resp.status}`);
      const data = await resp.json();
      setCandidates(data.candidates || []);
      // Reset selection when changing candidates window
      setSelectedKeys(new Set());
      setSuccessSummary(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch candidates.');
    } finally {
      setLoading(false);
    }
  };

  const getSortedCandidates = () => {
    const list = [...candidates];
    if (sortBy === 'plays') {
      return list.sort(
        (a, b) =>
          b.play_count - a.play_count ||
          b.last_played_unix - a.last_played_unix
      );
    } else {
      // Calculate underrated score: plays / popularity (popularity clamped to min 1 to avoid division by zero)
      const getUnderratedScore = (c: Candidate) =>
        c.play_count / (c.popularity || 1);
      return list.sort(
        (a, b) =>
          getUnderratedScore(b) - getUnderratedScore(a) ||
          b.last_played_unix - a.last_played_unix
      );
    }
  };

  const sortedList = getSortedCandidates();

  const handleToggleSelect = (key: string) => {
    const next = new Set(selectedKeys);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    setSelectedKeys(next);
    setSuccessSummary(null);
  };

  const handleQuickSelect = (count: number) => {
    const next = new Set<string>();
    const limit = Math.min(count, sortedList.length);
    for (let i = 0; i < limit; i++) {
      next.add(sortedList[i].track_key);
    }
    setSelectedKeys(next);
    setSuccessSummary(null);
  };

  const handleClearSelection = () => {
    setSelectedKeys(new Set());
    setSuccessSummary(null);
  };

  const handleGenerateRecap = async () => {
    if (selectedKeys.size === 0) return;
    setGenerating(true);
    setError(null);
    setSuccessSummary(null);
    setSlideUrls([]);

    // Map selected keys to the original track objects in selection order
    const selectedTracks = sortedList.filter(c => selectedKeys.has(c.track_key));

    try {
      const resp = await fetch(`${apiBase}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tracks: selectedTracks }),
      });
      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.error || `HTTP error ${resp.status}`);
      }
      const data = await resp.json();
      setSuccessSummary(data.summary);
      setSlideUrls(data.slides || []);
    } catch (err: any) {
      setError(err.message || 'Failed to generate slideshow.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0f1115] text-gray-100 flex flex-col selection:bg-purple-500 selection:text-white">
      {/* Header */}
      <header className="border-b border-gray-800 bg-[#161920]/80 backdrop-blur sticky top-0 z-10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/20">
            <svg
              className="w-6 h-6 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
              />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-red-400 bg-clip-text text-transparent">
              Weekly Recap Picker
            </h1>
            <p className="text-xs text-gray-400 font-medium">
              Phase 5 Dashboard
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-xl px-3 py-1.5 text-xs">
            <span className="text-gray-500 font-bold uppercase tracking-wider">Backend API:</span>
            <input
              type="text"
              value={apiBase}
              onChange={(e) => {
                setApiBase(e.target.value);
                localStorage.setItem('api_base', e.target.value);
              }}
              className="bg-transparent text-gray-200 focus:outline-none w-56 font-mono text-[11px]"
              placeholder="http://localhost:8000"
            />
          </div>
          <a
            href="https://github.com/bryanygan/ttspotslideshow"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
              <path
                fillRule="evenodd"
                d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                clipRule="evenodd"
              />
            </svg>
          </a>
        </div>
      </header>

      {/* Main layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left column (controls / statistics / recap generation) */}
        <section className="lg:col-span-1 flex flex-col gap-6">
          <div className="bg-[#161920] border border-gray-800 rounded-2xl p-5 flex flex-col gap-5">
            <h2 className="text-md font-bold text-gray-200 uppercase tracking-wider">
              Recap Controls
            </h2>

            {/* Range Selection */}
            <div className="flex flex-col gap-2">
              <label className="text-sm text-gray-400 font-semibold">
                Time Window
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[7, 14, 30].map(d => (
                  <button
                    key={d}
                    onClick={() => setDays(d)}
                    className={`py-2 px-3 rounded-xl font-medium text-sm transition-all ${
                      days === d
                        ? 'bg-purple-600 text-white shadow-md shadow-purple-500/20'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                    }`}
                  >
                    {d} Days
                  </button>
                ))}
              </div>
            </div>

            {/* Sort Selection */}
            <div className="flex flex-col gap-2">
              <label className="text-sm text-gray-400 font-semibold">
                Sort Candidates By
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setSortBy('plays')}
                  className={`py-2 px-3 rounded-xl font-medium text-sm transition-all ${
                    sortBy === 'plays'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-500/20'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                  }`}
                >
                  Play Count
                </button>
                <button
                  onClick={() => setSortBy('underrated')}
                  className={`py-2 px-3 rounded-xl font-medium text-sm transition-all ${
                    sortBy === 'underrated'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-500/20'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                  }`}
                >
                  Underrated
                </button>
              </div>
            </div>

            {/* Quick Selection */}
            <div className="flex flex-col gap-2">
              <label className="text-sm text-gray-400 font-semibold">
                Quick Select
              </label>
              <div className="grid grid-cols-4 gap-2">
                {[4, 8, 12, 16].map(num => (
                  <button
                    key={num}
                    onClick={() => handleQuickSelect(num)}
                    className="py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium text-sm transition-colors"
                  >
                    Top {num}
                  </button>
                ))}
              </div>
              <button
                onClick={handleClearSelection}
                className="mt-1 py-2 w-full text-center rounded-xl border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 font-medium text-xs transition-colors"
              >
                Clear Selection
              </button>
            </div>
          </div>

          {/* Action box */}
          <div className="bg-[#161920] border border-gray-800 rounded-2xl p-5 flex flex-col gap-4">
            <h2 className="text-md font-bold text-gray-200 uppercase tracking-wider">
              Recap Summary
            </h2>

            <div className="flex justify-between items-center text-sm py-1 border-b border-gray-800">
              <span className="text-gray-400">Total Candidates</span>
              <span className="font-bold text-gray-200">
                {candidates.length}
              </span>
            </div>

            <div className="flex justify-between items-center text-sm py-1 border-b border-gray-800">
              <span className="text-gray-400">Tracks Selected</span>
              <span className="font-bold text-purple-400">
                {selectedKeys.size}
              </span>
            </div>

            <div className="flex justify-between items-center text-sm py-1 border-b border-gray-800">
              <span className="text-gray-400">Slide Count</span>
              <span className="font-bold text-pink-400">
                {Math.floor(selectedKeys.size / 4)} slide(s) ({selectedKeys.size % 4} leftover)
              </span>
            </div>

            {selectedKeys.size > 0 && selectedKeys.size % 4 !== 0 && (
              <div className="bg-amber-950/40 border border-amber-900/60 rounded-xl p-3 text-xs text-amber-300">
                Tip: Slides render 4-up. Add/remove tracks to reach a multiple of
                4 (e.g. 4, 8, 12, 16) to avoid waste!
              </div>
            )}

            <button
              onClick={handleGenerateRecap}
              disabled={selectedKeys.size === 0 || generating}
              className={`w-full py-3.5 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2 ${
                selectedKeys.size === 0 || generating
                  ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                  : 'bg-gradient-to-r from-purple-600 via-pink-600 to-red-500 text-white shadow-lg shadow-purple-500/20 hover:scale-[1.02]'
              }`}
            >
              {generating ? (
                <>
                  <svg
                    className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Generating...
                </>
              ) : (
                'Generate Recap Slides'
              )}
            </button>

            {successSummary && (
              <div className="bg-emerald-950/40 border border-emerald-900/60 rounded-xl p-4 flex flex-col gap-2">
                <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  Success!
                </div>
                <div className="text-xs text-emerald-300/90 leading-relaxed flex flex-col gap-1">
                  <div>
                    Rendered <strong>{successSummary.slide_count}</strong> slide(s)
                    — view & save them in <strong>Your Slides</strong> on the
                    right. (Also saved on the host at:)
                  </div>
                  <div className="font-mono bg-black/30 p-1.5 rounded select-all mt-1 break-all overflow-x-auto">
                    {successSummary.out_dir}
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Right column (candidates pool list, spans 3 grid cols) */}
        <section className="lg:col-span-3 flex flex-col gap-4">
          {slideUrls.length > 0 && (
            <div className="bg-[#161920] border border-emerald-900/40 rounded-2xl p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h2 className="text-md font-bold text-gray-200 uppercase tracking-wider">
                  Your Slides ({slideUrls.length})
                </h2>
                <span className="text-xs text-emerald-300/90 bg-emerald-950/40 border border-emerald-900/60 rounded-lg px-2.5 py-1">
                  📱 iPhone: long-press a slide → <strong>Add to Photos</strong>
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                {slideUrls.map((url, i) => (
                  <a
                    key={url}
                    href={`${apiBase}${url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex flex-col gap-1.5"
                  >
                    <img
                      src={`${apiBase}${url}`}
                      alt={`Slide ${i + 1}`}
                      className="w-full rounded-xl border border-gray-800 shadow-lg group-hover:border-purple-500/60 transition-colors"
                    />
                    <span className="text-[11px] text-gray-400 text-center font-medium">
                      Slide {i + 1}
                    </span>
                  </a>
                ))}
              </div>
              <p className="text-xs text-gray-500 leading-relaxed">
                Tap a slide to open it full-size, then long-press →{' '}
                <strong>Add to Photos</strong> to save it to your Camera Roll /
                iCloud Photos. On desktop, right-click → Save image.
              </p>
            </div>
          )}
          {error && (
            <div className="bg-red-950/40 border border-red-900/60 text-red-300 rounded-2xl p-4 text-sm flex items-start gap-3">
              <svg
                className="w-5 h-5 text-red-400 shrink-0 mt-0.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <div>{error}</div>
            </div>
          )}

          {loading ? (
            <div className="flex-1 bg-[#161920] border border-gray-800 rounded-2xl p-10 flex flex-col items-center justify-center gap-4 min-h-[400px]">
              <div className="w-12 h-12 rounded-full border-4 border-purple-500/20 border-t-purple-600 animate-spin" />
              <div className="text-gray-400 font-medium">
                Fetching candidate pool...
              </div>
            </div>
          ) : sortedList.length === 0 ? (
            <div className="flex-1 bg-[#161920] border border-gray-800 rounded-2xl p-10 flex flex-col items-center justify-center gap-4 text-center min-h-[400px]">
              <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center text-gray-500">
                <svg
                  className="w-8 h-8"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
                  />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-300">
                  No tracks found
                </h3>
                <p className="text-sm text-gray-500 mt-1 max-w-sm">
                  No songs were logged in the database during the selected {days}
                  -day time window.
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-[#161920] border border-gray-800 rounded-2xl overflow-hidden shadow-xl">
              {/* List Header */}
              <div className="px-6 py-4 bg-[#1e222b] border-b border-gray-800 text-xs font-bold text-gray-400 uppercase tracking-wider grid grid-cols-12 gap-4 items-center select-none">
                <div className="col-span-1 text-center">Select</div>
                <div className="col-span-6 flex gap-3">Track details</div>
                <div className="col-span-2 text-center">Genre Bucket</div>
                <div className="col-span-1 text-center">Plays</div>
                <div className="col-span-2 text-center">Popularity</div>
              </div>

              {/* Candidates list */}
              <div className="divide-y divide-gray-800 max-h-[70vh] overflow-y-auto">
                {sortedList.map((track, index) => {
                  const isSelected = selectedKeys.has(track.track_key);
                  const underratedScore = (
                    track.play_count / (track.popularity || 1)
                  ).toFixed(2);

                  return (
                    <div
                      key={track.track_key}
                      onClick={() => handleToggleSelect(track.track_key)}
                      className={`px-6 py-3.5 grid grid-cols-12 gap-4 items-center cursor-pointer transition-all hover:bg-[#1f2430] select-none ${
                        isSelected ? 'bg-purple-950/20' : ''
                      }`}
                    >
                      {/* Checkbox */}
                      <div
                        className="col-span-1 flex items-center justify-center"
                        onClick={e => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => handleToggleSelect(track.track_key)}
                          className="w-5 h-5 accent-purple-600 rounded-md border-gray-600 bg-gray-800 cursor-pointer focus:ring-purple-500"
                        />
                      </div>

                      {/* Cover & Details */}
                      <div className="col-span-6 flex gap-3.5 items-center min-w-0">
                        <span className="text-xs text-gray-500 font-mono w-4 shrink-0 text-right">
                          {index + 1}
                        </span>
                        {track.album_art_url ? (
                          <img
                            src={track.album_art_url}
                            alt={track.title}
                            className="w-12 h-12 rounded-lg object-cover shadow border border-gray-800 shrink-0"
                            onError={e => {
                              (e.target as HTMLElement).style.display = 'none';
                            }}
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-lg bg-gray-800 border border-gray-700 flex items-center justify-center text-gray-500 font-bold text-xs shrink-0 select-none">
                            🎵
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <div
                            className="font-bold text-sm text-white truncate pr-2"
                            title={track.title}
                          >
                            {track.title}
                          </div>
                          <div
                            className="text-xs text-gray-400 truncate mt-0.5"
                            title={track.artist}
                          >
                            {track.artist}
                          </div>
                          {track.last_featured && (
                            <div className="inline-flex items-center gap-1 mt-1 text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded px-1.5 py-0.5 font-medium">
                              Featured {track.last_featured}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Genre Bucket */}
                      <div className="col-span-2 text-center">
                        <span className="inline-block text-[11px] px-2.5 py-1 rounded-full font-bold uppercase tracking-wide bg-gray-800 text-gray-300 border border-gray-700">
                          {track.primary_bucket}
                        </span>
                      </div>

                      {/* Play Count */}
                      <div className="col-span-1 text-center font-bold text-sm text-gray-200">
                        {track.play_count}
                      </div>

                      {/* Popularity bar */}
                      <div className="col-span-2 flex flex-col gap-1 items-center justify-center pr-2">
                        <div className="flex items-center justify-between w-full text-[10px] text-gray-400">
                          <span>Pop: {track.popularity}</span>
                          {sortBy === 'underrated' && (
                            <span className="text-purple-400 font-bold">
                              Score: {underratedScore}
                            </span>
                          )}
                        </div>
                        <div className="w-full bg-gray-800 h-1.5 rounded-full overflow-hidden">
                          <div
                            className="bg-gradient-to-r from-purple-500 to-pink-500 h-full rounded-full"
                            style={{ width: `${track.popularity}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
