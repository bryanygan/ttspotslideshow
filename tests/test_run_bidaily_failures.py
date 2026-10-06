from contextlib import contextmanager

import pytest

import run_bidaily
from slideshow.builder import MissingCoverError


@pytest.fixture
def stub_pipeline(monkeypatch):
    monkeypatch.setattr(run_bidaily.db, "init_db", lambda: None)

    @contextmanager
    def fake_connect():
        yield object()

    monkeypatch.setattr(run_bidaily.db, "connect", fake_connect)
    monkeypatch.setattr(run_bidaily, "format_summary", lambda s: "ok")
    alerts = []
    monkeypatch.setattr(run_bidaily, "send_alert", lambda title, details="": alerts.append(title))
    return alerts


def test_missing_cover_tracks_are_dropped_and_build_retried(monkeypatch, stub_pipeline):
    seen_excludes = []

    def fake_build(conn, out_path, allow_itunes_covers=False, exclude_keys=None):
        seen_excludes.append(set(exclude_keys or ()))
        if len(seen_excludes) == 1:
            raise MissingCoverError([{"track_key": "bad\tsong", "artist": "bad", "title": "song"}])
        return {"slide_count": 4}

    monkeypatch.setattr(run_bidaily, "build_slideshow", fake_build)
    run_bidaily.run_pipeline(skip_spotify=True, skip_lastfm=True, skip_popularity=True)

    assert seen_excludes == [set(), {"bad\tsong"}]


def test_zero_slides_is_a_failure(monkeypatch, stub_pipeline):
    monkeypatch.setattr(run_bidaily, "build_slideshow", lambda *a, **k: {"slide_count": 0})
    with pytest.raises(RuntimeError, match="zero slides"):
        run_bidaily.run_pipeline(skip_spotify=True, skip_lastfm=True, skip_popularity=True)


def test_main_exits_1_and_alerts_on_unexpected_error(monkeypatch, stub_pipeline):
    monkeypatch.setattr(run_bidaily, "setup_logging", lambda name: None)
    monkeypatch.setattr(run_bidaily, "run_pipeline", lambda **k: (_ for _ in ()).throw(ValueError("boom")))
    monkeypatch.setattr("sys.argv", ["run_bidaily.py"])

    with pytest.raises(SystemExit) as exc:
        run_bidaily.main()
    assert exc.value.code == 1
    assert stub_pipeline == ["Bi-daily slideshow FAILED"]


def test_main_exits_2_when_cover_retries_exhausted(monkeypatch, stub_pipeline):
    monkeypatch.setattr(run_bidaily, "setup_logging", lambda name: None)

    def always_missing(*a, **k):
        raise MissingCoverError([{"track_key": "k", "artist": "a", "title": "t"}])

    monkeypatch.setattr(run_bidaily, "run_pipeline", always_missing)
    monkeypatch.setattr("sys.argv", ["run_bidaily.py"])

    with pytest.raises(SystemExit) as exc:
        run_bidaily.main()
    assert exc.value.code == 2
    assert stub_pipeline == ["Bi-daily slideshow not built: cover art problem"]
