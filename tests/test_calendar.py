from datetime import date


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


class _FakeTelegramAPI:
    def __init__(self, updates):
        self._updates = updates
        self.sent: list[tuple[int, str]] = []

    def get_updates(self, limit=100):
        return self._updates

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_telegram_sync_lists_unread_users(client, monkeypatch):
    _setup_with_client(client)
    updates = [
        {
            "update_id": 10,
            "message": {
                "date": 1773475200,
                "text": "Alice",
                "chat": {"id": 555, "first_name": "Noam"},
            },
        }
    ]
    fake = _FakeTelegramAPI(updates)

    from app.routes import calendar as calendar_routes

    monkeypatch.setattr(calendar_routes, "_create_telegram_api", lambda: fake)
    resp = client.get("/calendar/telegram-sync")
    assert resp.status_code == 200
    assert b"Noam" in resp.data
    assert b"555" in resp.data


def test_telegram_sync_run_creates_sessions_and_reports_errors(client, app, monkeypatch):
    _setup_with_client(client, name="\u05e0\u05e2\u05dd", rate="180")
    msg_ts = 1773475200
    expected_day = date.fromtimestamp(msg_ts).isoformat()
    updates = [
        {
            "update_id": 20,
            "message": {
                "date": msg_ts,
                "text": "\u05e0\u05d5\u05e2\u05dd\nUnknown",
                "chat": {"id": 777, "first_name": "Clinic"},
            },
        }
    ]
    fake = _FakeTelegramAPI(updates)

    from app.routes import calendar as calendar_routes

    monkeypatch.setattr(calendar_routes, "_create_telegram_api", lambda: fake)

    resp = client.post(
        "/calendar/telegram-sync/run",
        data={"chat_id": "777"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        from app.db import get_db

        db = get_db()
        session = db.execute(
            "SELECT date, hours, rate, notes FROM sessions WHERE profile_id = 1"
        ).fetchone()
        assert session is not None
        assert session["date"] == expected_day
        assert session["hours"] == 1
        assert session["rate"] == 180
        assert session["notes"] == "Telegram sync"

        processed = db.execute(
            "SELECT update_id, chat_id FROM telegram_processed_updates WHERE profile_id = 1"
        ).fetchall()
        assert len(processed) == 1
        assert processed[0]["update_id"] == 20
        assert processed[0]["chat_id"] == 777

    assert len(fake.sent) == 1
    sent_chat_id, sent_text = fake.sent[0]
    assert sent_chat_id == 777
    assert expected_day in sent_text
    assert "1 hours" in sent_text
    assert "Can't match Unknown on day" in sent_text
