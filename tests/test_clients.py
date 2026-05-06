def _setup(client):
    client.post("/profiles/create", data={"name": "P"})


def test_create_client_requires_active_profile_set(client):
    _setup(client)
    resp = client.post("/clients/create", data={"name": "Alice", "rate": "200"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Alice" in resp.data


def test_client_unique_per_profile(client):
    _setup(client)
    client.post("/clients/create", data={"name": "Bob", "rate": "100"})
    resp = client.post("/clients/create", data={"name": "Bob", "rate": "150"}, follow_redirects=True)
    assert b"already exists" in resp.data


def test_negative_rate_rejected(client):
    _setup(client)
    resp = client.post("/clients/create", data={"name": "X", "rate": "-1"}, follow_redirects=True)
    assert b"non-negative" in resp.data


def test_archive_then_restore_client(client):
    _setup(client)
    client.post("/clients/create", data={"name": "C", "rate": "100"})
    # archive
    resp = client.post("/clients/1/archive", follow_redirects=True)
    assert b"archived" in resp.data
    # restore
    resp = client.post("/clients/1/restore", follow_redirects=True)
    assert resp.status_code == 200


def test_autocomplete(client):
    _setup(client)
    client.post("/clients/create", data={"name": "Alice", "rate": "100"})
    client.post("/clients/create", data={"name": "Albert", "rate": "150"})
    resp = client.get("/clients/autocomplete?q=Al")
    assert b"Alice" in resp.data
    assert b"Albert" in resp.data
