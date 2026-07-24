from app.constants import UserStatus


async def test_register_creates_pending_user(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": "pw12345", "name": "홍길동"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == UserStatus.PENDING
    assert isinstance(body["id"], int)


async def test_register_rejects_duplicate_email(client):
    await client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "pw12345", "name": "홍길동"},
    )
    resp = await client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "other-pw", "name": "홍길동"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"


async def test_register_rejects_duplicate_email_differing_in_case_and_whitespace(client):
    """이메일 정규화(strip/lower) + 중복 처리 회귀 테스트.

    대소문자/공백만 다른 이메일로 두 번 가입을 시도하면, 정규화 후 동일한
    값으로 취급되어 두 번째 요청은 500(유니크 제약 위반)이 아니라 409로
    처리되어야 한다.
    """
    resp1 = await client.post(
        "/api/auth/register",
        json={"email": "Race@Example.com", "password": "pw12345", "name": "홍길동"},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/auth/register",
        json={"email": " race@example.com ", "password": "other-pw", "name": "홍길동"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "CONFLICT"


async def test_register_stores_name(client, db_session):
    from sqlalchemy import text

    resp = await client.post(
        "/api/auth/register",
        json={"email": "named@example.com", "password": "pw12345", "name": "홍길동"},
    )
    assert resp.status_code == 201

    row = await db_session.execute(
        text("SELECT name FROM users WHERE email = 'named@example.com'")
    )
    assert row.scalar() == "홍길동"


async def test_register_trims_name(client, db_session):
    from sqlalchemy import text

    await client.post(
        "/api/auth/register",
        json={"email": "trim@example.com", "password": "pw12345", "name": "  김철수  "},
    )
    row = await db_session.execute(
        text("SELECT name FROM users WHERE email = 'trim@example.com'")
    )
    assert row.scalar() == "김철수"


async def test_register_rejects_blank_name(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "blank@example.com", "password": "pw12345", "name": "   "},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_NAME"


async def test_register_rejects_too_long_name(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "long@example.com", "password": "pw12345", "name": "가" * 51},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_NAME"


async def test_register_accepts_50_char_name(client):
    """경계값: 50자는 허용이다(51자부터 거부)."""
    resp = await client.post(
        "/api/auth/register",
        json={"email": "max@example.com", "password": "pw12345", "name": "가" * 50},
    )
    assert resp.status_code == 201
