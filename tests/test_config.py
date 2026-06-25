import pytest

import config


def test_get_lastfm_user_explicit(monkeypatch):
    monkeypatch.setattr(config, "LASTFM_USER", "explicituser")
    assert config.get_lastfm_user() == "explicituser"


def test_get_lastfm_user_autodetect_from_filename(monkeypatch, tmp_path):
    (tmp_path / "scrobbles-Priinplup-1782268878.xml").write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "LASTFM_USER", None)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.get_lastfm_user() == "Priinplup"


def test_get_lastfm_user_returns_empty_when_unresolvable(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LASTFM_USER", None)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)  # no export file present
    assert config.get_lastfm_user() == ""


def test_resolve_export_path_picks_newest(monkeypatch, tmp_path):
    (tmp_path / "scrobbles-a-1.xml").write_text("x", encoding="utf-8")
    (tmp_path / "scrobbles-b-2.xml").write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "LASTFM_EXPORT_PATH", None)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.resolve_export_path().name == "scrobbles-b-2.xml"  # sorted()[-1]


def test_resolve_export_path_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom.xml"
    monkeypatch.setattr(config, "LASTFM_EXPORT_PATH", str(custom))
    assert config.resolve_export_path() == custom


def test_resolve_export_path_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LASTFM_EXPORT_PATH", None)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with pytest.raises(SystemExit):
        config.resolve_export_path()


def test_assert_credentials_ok(monkeypatch):
    monkeypatch.setattr(config, "CLIENT_ID", "id")
    monkeypatch.setattr(config, "CLIENT_SECRET", "secret")
    config.assert_credentials()  # should not raise


def test_assert_credentials_missing_raises(monkeypatch):
    monkeypatch.setattr(config, "CLIENT_ID", None)
    monkeypatch.setattr(config, "CLIENT_SECRET", None)
    with pytest.raises(SystemExit):
        config.assert_credentials()
