def _setup_with_client(client, name="Alice", rate="200"):
    client.post("/profiles/create", data={"name": "P"})
    client.post("/clients/create", data={"name": name, "rate": rate})


def test_add_session_and_view_day(client):
    _setup_with_client(client)
    resp = client.post(
        "/calendar/day/2026-05-15/sessions",
        data={"client_id": "1", "hours": "2", "notes": "first session"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Alice" in resp.data
    assert b"first session" in resp.data


def test_session_rate_snapshot(client, app):
    _setup_with_client(client, rate="100")
    client.post(
        "/calendar/day/2026-05-15/sessions",
        data={"client_id": "1", "hours": "1"},
    )
    # Update client rate.
    client.post("/clients/1/edit", data={"name": "Alice", "rate": "999"})
    # Old session must keep snapshot of 100.
    with app.app_context():
        from app.db import get_db
        row = get_db().execute("SELECT rate FROM sessions WHERE id=1").fetchone()
        assert row["rate"] == 100


def test_invalid_hours_rejected(client):
    _setup_with_client(client)
    resp = client.post(
        "/calendar/day/2026-05-15/sessions",
        data={"client_id": "1", "hours": "0"},
        follow_redirects=True,
    )
    assert b"greater than 0" in resp.data


def test_archived_client_cannot_be_added_to_session(client):
    _setup_with_client(client)
    client.post("/clients/1/archive")
    resp = client.post(
        "/calendar/day/2026-05-15/sessions",
        data={"client_id": "1", "hours": "1"},
        follow_redirects=True,
    )
    assert b"not valid" in resp.data


def test_delete_session(client):
    _setup_with_client(client)
    client.post(
        "/calendar/day/2026-05-15/sessions",
        data={"client_id": "1", "hours": "1"},
    )
    resp = client.post("/calendar/sessions/1/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"No sessions logged" in resp.data


def test_month_view_shows_hours(client):
    _setup_with_client(client)
    client.post(
        "/calendar/day/2026-05-15/sessions",
        data={"client_id": "1", "hours": "2.5"},
    )
    resp = client.get("/calendar/?year=2026&month=5")
    assert b"2.5" in resp.data
