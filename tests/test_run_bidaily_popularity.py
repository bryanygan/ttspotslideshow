import run_bidaily


def test_pipeline_runs_popularity_enrichment(monkeypatch):
    calls = {"enriched": False, "built": False}

    monkeypatch.setattr(run_bidaily.db, "init_db", lambda: None)

    # Stub a connect() context manager.
    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield object()
    monkeypatch.setattr(run_bidaily.db, "connect", fake_connect)

    monkeypatch.setattr(
        run_bidaily, "enrich_all_popularity",
        lambda *a, **k: calls.__setitem__("enriched", True) or {
            "processed": 0, "lastfm": 0, "listenbrainz": 0, "none": 0},
    )
    monkeypatch.setattr(
        run_bidaily, "build_slideshow",
        lambda conn, out_path: calls.__setitem__("built", True) or {"slide_count": 0},
    )
    monkeypatch.setattr(run_bidaily, "format_summary", lambda s: "ok")

    run_bidaily.run_pipeline(skip_spotify=True, skip_lastfm=True)
    assert calls["enriched"] is True
    assert calls["built"] is True


def test_skip_popularity_flag(monkeypatch):
    calls = {"enriched": False}
    monkeypatch.setattr(run_bidaily.db, "init_db", lambda: None)
    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield object()
    monkeypatch.setattr(run_bidaily.db, "connect", fake_connect)
    monkeypatch.setattr(
        run_bidaily, "enrich_all_popularity",
        lambda *a, **k: calls.__setitem__("enriched", True),
    )
    monkeypatch.setattr(run_bidaily, "build_slideshow", lambda conn, out_path: {"slide_count": 0})
    monkeypatch.setattr(run_bidaily, "format_summary", lambda s: "ok")

    run_bidaily.run_pipeline(skip_spotify=True, skip_lastfm=True, skip_popularity=True)
    assert calls["enriched"] is False
