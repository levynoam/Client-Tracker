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
