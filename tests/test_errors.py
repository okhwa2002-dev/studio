import pytest

from app.models.error_code import ErrorCode
from app.utils.errors import ResolvedError, resolve_error


@pytest.fixture
async def seed_errors(db_session):
    db_session.add_all([
        ErrorCode(code="AUTH_INVALID", message="인증 실패", http_status=401, is_default=False, is_active=True),
        ErrorCode(code="DEFAULT", message="요청을 처리할 수 없습니다.", http_status=400, is_default=True, is_active=True),
    ])
    await db_session.commit()


async def test_resolve_known_code(db_session, seed_errors):
    r = await resolve_error(db_session, "AUTH_INVALID")
    assert r == ResolvedError(code="AUTH_INVALID", message="인증 실패", http_status=401)


async def test_resolve_unknown_returns_default(db_session, seed_errors):
    r = await resolve_error(db_session, "NOPE")
    assert r.code == "DEFAULT"
    assert r.http_status == 400


async def test_passed_message_overrides(db_session, seed_errors):
    r = await resolve_error(db_session, "AUTH_INVALID", message="커스텀")
    assert r.message == "커스텀"
    assert r.code == "AUTH_INVALID"


async def test_no_default_falls_back_hardcoded(db_session):
    r = await resolve_error(db_session, "NOPE")
    assert r.code == "UNKNOWN_ERROR"
    assert r.http_status == 500
