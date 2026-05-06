def test_first_run_redirects_to_profiles(client):
    resp = client.get("/", follow_redirects=False)
    # / -> calendar.month_view -> redirected to profiles.index because no profile
    assert resp.status_code in (301, 302)
    # follow chain
    resp = client.get("/", follow_redirects=True)
    assert b"Profiles" in resp.data


def test_create_profile_and_activate(client):
    resp = client.post("/profiles/create", data={"name": "Clinic A"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Clinic A" in resp.data


def test_duplicate_profile_rejected(client):
    client.post("/profiles/create", data={"name": "X"})
    resp = client.post("/profiles/create", data={"name": "X"}, follow_redirects=True)
    assert b"already exists" in resp.data


def test_cannot_archive_active_profile(client):
    client.post("/profiles/create", data={"name": "Active"})
    # The created profile becomes active automatically.
    # Find its id.
    page = client.get("/profiles/").data.decode()
    # We don't parse HTML; instead, fetch via a follow-up. Use DB-free approach:
    # Try to archive id=1 (the only one created).
    resp = client.post("/profiles/1/archive", follow_redirects=True)
    assert b"cannot archive" in resp.data.lower()
