import config
import db
import pytest
import run_bidaily


def test_run_pipeline_orchestration(monkeypatch, tmp_path):
    # Mock config credentials assert
    monkeypatch.setattr(config, "assert_credentials", lambda: None)
    monkeypatch.setattr(config, "LASTFM_API_KEY", "fake_key")
    monkeypatch.setattr(config, "get_lastfm_user", lambda: "fake_user")

    # Mock log_recent_plays
    log_called = []

    def fake_log_recent_plays():
        log_called.append("spotify")
        return 2

    monkeypatch.setattr(run_bidaily, "log_recent_plays", fake_log_recent_plays)

    # Mock import_recent_from_api
    import_called = []

    def fake_import_recent_from_api(conn, api_key, username, since_unix):
        import_called.append((api_key, username, since_unix))
        return 3

    monkeypatch.setattr(
        run_bidaily, "import_recent_from_api", fake_import_recent_from_api
    )

    # Mock build_slideshow
    build_called = []

    def fake_build_slideshow(conn, out_path):
        build_called.append(out_path)
        return {
            "track_count": 4,
            "slide_count": 1,
            "genre_spread": {"hip-hop": 4},
            "out_dir": str(out_path / "2026-06-24"),
            "days_used": 2,
        }

    monkeypatch.setattr(run_bidaily, "build_slideshow", fake_build_slideshow)

    # Use a temporary DB path
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "plays.db")

    # Run the pipeline
    run_bidaily.run_pipeline(
        skip_spotify=False,
        skip_lastfm=False,
        out_root=str(tmp_path / "slides"),
    )

    assert log_called == ["spotify"]
    assert len(import_called) == 1
    assert import_called[0][0] == "fake_key"
    assert import_called[0][1] == "fake_user"
    assert build_called == [tmp_path / "slides"]


def test_run_pipeline_skips(monkeypatch, tmp_path):
    # Mock log_recent_plays
    log_called = []
    monkeypatch.setattr(
        run_bidaily, "log_recent_plays", lambda: log_called.append("spotify")
    )

    # Mock import_recent_from_api
    import_called = []
    monkeypatch.setattr(
        run_bidaily,
        "import_recent_from_api",
        lambda *a, **kw: import_called.append("lastfm"),
    )

    # Mock build_slideshow
    monkeypatch.setattr(
        run_bidaily,
        "build_slideshow",
        lambda conn, out_path: {
            "track_count": 0,
            "slide_count": 0,
            "genre_spread": {},
            "out_dir": str(out_path),
            "days_used": 2,
        },
    )

    # Use a temporary DB path
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "plays_skip.db")

    # Run with skips
    run_bidaily.run_pipeline(
        skip_spotify=True,
        skip_lastfm=True,
        out_root=str(tmp_path / "slides"),
    )

    assert not log_called
    assert not import_called
