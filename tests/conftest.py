"""Shared pytest fixtures for the test suite."""

import sqlite3

import pytest

import db


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    # Real Ollama calls take ~15s each; tests use the deterministic caption.
    monkeypatch.setenv("CAPTION_AI", "0")


@pytest.fixture
def conn():
    """An in-memory SQLite connection, migrated to the current schema.

    Replaces the per-file ``_conn()`` helpers that several test modules defined.
    Each test gets a fresh, isolated database.
    """
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    yield c
    c.close()
