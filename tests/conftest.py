"""Pytest fixtures."""
from __future__ import annotations

import os
import tempfile

import pytest

from app import create_app


@pytest.fixture
def app():
    fd, db_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    app = create_app({"TESTING": True, "DATABASE": db_path, "SECRET_KEY": "test"})
    yield app
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def with_profile(app, client):
    """Create a profile and activate it via cookie. Returns its id."""
    client.post("/profiles/create", data={"name": "Default"})
    # The cookie is set by the response; the test client persists cookies.
    with app.app_context():
        from app.db import get_db
        row = get_db().execute("SELECT id FROM profiles WHERE name='Default'").fetchone()
        return row["id"]
