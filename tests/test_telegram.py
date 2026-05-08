def _setup(client):
    client.post("/profiles/create", data={"name": "P"})


class _FakeTelegramAPI:
    def __init__(self, updates):
        self._updates = updates

    def get_updates(self, limit=100):
        return self._updates


def test_telegram_tab_renders_chats_and_messages(client, monkeypatch):
    _setup(client)
    updates = [
        {
            "update_id": 1,
            "message": {
                "date": 1773475200,
                "text": "hello from alice",
                "chat": {"id": 101, "first_name": "Alice"},
                "from": {"first_name": "Alice"},
            },
        },
        {
            "update_id": 2,
            "message": {
                "date": 1773475300,
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
    updates = [
        {
            "update_id": 3,
            "message": {
                "date": 1773475400,
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
    updates = [
        {
            "update_id": 99,
            "message": {
                "date": 1773475500,
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
