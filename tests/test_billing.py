def _setup(client):
    client.post("/profiles/create", data={"name": "P"})
    client.post("/clients/create", data={"name": "Alice", "rate": "100"})
    client.post("/clients/create", data={"name": "Bob", "rate": "200"})
    client.post("/calendar/day/2026-04-10/sessions",
                data={"client_id": "1", "hours": "2"})
    client.post("/calendar/day/2026-04-20/sessions",
                data={"client_id": "1", "hours": "1.5"})
    client.post("/calendar/day/2026-04-15/sessions",
                data={"client_id": "2", "hours": "3"})
    # An out-of-month session that must NOT be counted.
    client.post("/calendar/day/2026-05-01/sessions",
                data={"client_id": "1", "hours": "10"})


def test_billing_index(client):
    _setup(client)
    resp = client.get("/billing/?year=2026&month=4")
    body = resp.data.decode()
    assert "Alice" in body
    assert "Bob" in body
    # Alice: 2 + 1.5 = 3.5 hrs at 100 = 350. Bob: 3 hrs at 200 = 600. Grand 950.
    assert "350" in body
    assert "600" in body
    assert "950" in body
    assert "Meetings" in body
    assert "Fr(10),Mo(20)" in body
    assert "We(15)" in body


def test_csv_export(client):
    _setup(client)
    resp = client.get("/billing/export.csv?year=2026&month=4")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    body = resp.data.decode()
    assert "Alice" in body
    assert "Bob" in body
    assert "TOTAL" in body
    assert "950" in body


def test_invoice_status_toggle(client, app):
    _setup(client)
    # Mark Alice (client_id=1) invoice sent for 2026-04.
    resp = client.post(
        "/billing/status",
        data={"client_id": "1", "year": "2026", "month": "4",
              "field": "invoice_sent", "value": "1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        from app.db import get_db
        row = get_db().execute(
            "SELECT invoice_sent, invoice_paid FROM billing_status "
            "WHERE client_id=1 AND year=2026 AND month=4"
        ).fetchone()
        assert row["invoice_sent"] == 1
        assert row["invoice_paid"] == 0

    # Now mark paid; sent flag must be preserved.
    client.post(
        "/billing/status",
        data={"client_id": "1", "year": "2026", "month": "4",
              "field": "invoice_paid", "value": "1"},
    )
    with app.app_context():
        from app.db import get_db
        row = get_db().execute(
            "SELECT invoice_sent, invoice_paid FROM billing_status "
            "WHERE client_id=1 AND year=2026 AND month=4"
        ).fetchone()
        assert row["invoice_sent"] == 1
        assert row["invoice_paid"] == 1

    # Untoggle sent.
    client.post(
        "/billing/status",
        data={"client_id": "1", "year": "2026", "month": "4",
              "field": "invoice_sent", "value": "0"},
    )
    with app.app_context():
        from app.db import get_db
        row = get_db().execute(
            "SELECT invoice_sent, invoice_paid FROM billing_status "
            "WHERE client_id=1 AND year=2026 AND month=4"
        ).fetchone()
        assert row["invoice_sent"] == 0
        assert row["invoice_paid"] == 1


def test_billing_page_shows_checkboxes(client):
    _setup(client)
    resp = client.get("/billing/?year=2026&month=4")
    body = resp.data.decode()
    assert "Invoice sent" in body
    assert "Invoice paid" in body
    assert 'type="checkbox"' in body
