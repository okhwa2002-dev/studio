async def test_register_creates_pending_user(client):
    resp = await client.post(
        "/auth/register", json={"email": "new@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert isinstance(body["id"], int)


async def test_register_rejects_duplicate_email(client):
    await client.post(
        "/auth/register", json={"email": "dup@example.com", "password": "pw12345"}
    )
    resp = await client.post(
        "/auth/register", json={"email": "dup@example.com", "password": "other-pw"}
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"
