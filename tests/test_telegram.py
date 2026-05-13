from datetime import datetime, timedelta


def _setup(client):
    client.post("/profiles/create", data={"name": "P"})


class _FakeTelegramAPI:
    def __init__(self, updates):
        self._updates = updates

    def get_updates(self, limit=100):
        return self._updates


def test_telegram_tab_renders_chats_and_messages(client, monkeypatch):
    _setup(client)
    now_ts = int(datetime.now().timestamp())
    updates = [
        {
            "update_id": 1,
            "message": {
                "date": now_ts - 120,
                "text": "hello from alice",
                "chat": {"id": 101, "first_name": "Alice"},
                "from": {"first_name": "Alice"},
            },
        },
        {
            "update_id": 2,
            "message": {
                "date": now_ts - 60,
                "text": "hello from bob",
                "chat": {"id": 202, "first_name": "Bob"},
                "from": {"first_name": "Bob"},
            },
        },
    ]

    from app.routes import telegram as telegram_routes

    monkeypatch.setattr(
        telegram_routes,
        "_create_telegram_api",
        lambda: _FakeTelegramAPI(updates),
    )

    resp = client.get("/telegram/")
    assert resp.status_code == 200
    assert b"Alice" in resp.data
    assert b"Bob" in resp.data
    # Latest chat (Bob) is selected by default, so Bob's message is shown.
    assert b"hello from bob" in resp.data



def test_telegram_tab_poll_endpoint(client, monkeypatch):
    _setup(client)
    now_ts = int(datetime.now().timestamp())
    updates = [
        {
            "update_id": 3,
            "message": {
                "date": now_ts - 30,
                "text": "line one",
                "chat": {"id": 303, "first_name": "C"},
                "from": {"first_name": "C"},
            },
        }
    ]

    from app.routes import telegram as telegram_routes

    monkeypatch.setattr(
        telegram_routes,
        "_create_telegram_api",
        lambda: _FakeTelegramAPI(updates),
    )

    resp = client.get("/telegram/poll?chat_id=303")
    assert resp.status_code == 200
    assert b"telegram-live" in resp.data
    assert b"line one" in resp.data



def test_telegram_tab_does_not_mark_updates_processed(client, app, monkeypatch):
    _setup(client)
    now_ts = int(datetime.now().timestamp())
    updates = [
        {
            "update_id": 99,
            "message": {
                "date": now_ts - 10,
                "text": "not synced",
                "chat": {"id": 404, "first_name": "D"},
                "from": {"first_name": "D"},
            },
        }
    ]

    from app.routes import telegram as telegram_routes

    monkeypatch.setattr(
        telegram_routes,
        "_create_telegram_api",
        lambda: _FakeTelegramAPI(updates),
    )

    resp = client.get("/telegram/")
    assert resp.status_code == 200

    with app.app_context():
        from app.db import get_db

        row = get_db().execute(
            "SELECT COUNT(*) AS c FROM telegram_processed_updates"
        ).fetchone()
        assert row["c"] == 0


def test_telegram_tab_includes_last_month_messages(client, app, monkeypatch):
    _setup(client)
    now_ts = int(datetime.now().timestamp())
    ten_days_ago = now_ts - (10 * 24 * 60 * 60)

    updates = [
        {
            "update_id": 110,
            "message": {
                "date": ten_days_ago,
                "text": "message from ten days ago",
                "chat": {"id": 777, "first_name": "History"},
                "from": {"first_name": "History"},
            },
        }
    ]

    from app.routes import telegram as telegram_routes

    monkeypatch.setattr(
        telegram_routes,
        "_create_telegram_api",
        lambda: _FakeTelegramAPI(updates),
    )

    resp = client.get("/telegram/")
    assert resp.status_code == 200
    assert b"message from ten days ago" in resp.data

    # Ensure very old cached messages are not shown in the 30-day view.
    old_ts = int((datetime.now() - timedelta(days=45)).timestamp())
    with app.app_context():
        from app.db import get_db

        db = get_db()
        db.execute(
            "INSERT INTO telegram_messages_cache "
            "(profile_id, update_id, chat_id, chat_label, sender, message_text, message_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 9999, 777, "History", "History", "too old", old_ts),
        )
        db.commit()

    resp = client.get("/telegram/?chat_id=777")
    assert resp.status_code == 200
    assert b"too old" not in resp.data
