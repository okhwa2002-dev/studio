from datetime import timedelta

import pytest

from app.auth.reset_rate_limit import RESET_REQUEST_WINDOW_MINUTES, check_and_record
from app.config import get_settings
from app.db import raw_connection
from app.queries import queries
from app.utils.errors import AppError
from app.utils.time import now_local


@pytest.fixture
def limits(monkeypatch):
    """한도를 테스트가 다루기 쉬운 작은 값으로 못박는다(로컬 .env에 흔들리지 않게)."""
    monkeypatch.setenv("RESET_REQUEST_COOLDOWN_SEC", "60")
    monkeypatch.setenv("RESET_REQUEST_EMAIL_HOURLY", "5")
    monkeypatch.setenv("RESET_REQUEST_IP_HOURLY", "20")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _record_at(conn, email, client_ip, when):
    """과거 요청을 직접 심는다. sleep으로 기다리지 않는다."""
    await queries.insert_reset_request(
        conn, email=email, client_ip=client_ip, created_at=when, updated_at=when
    )


async def test_first_request_passes_and_is_recorded(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()

    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    row = await queries.count_recent_reset_requests(
        conn,
        email="a@example.com",
        client_ip="1.1.1.1",
        cooldown_since=now - timedelta(seconds=60),
        window_since=now - timedelta(minutes=RESET_REQUEST_WINDOW_MINUTES),
    )
    assert row["email_window"] == 1


async def test_second_request_within_cooldown_is_rejected(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    with pytest.raises(AppError) as exc:
        await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=30))

    assert exc.value.status_code == 429
    assert exc.value.code == "TOO_MANY_RESET_REQUESTS"


async def test_request_after_cooldown_passes(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=61))


async def test_email_hourly_limit(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    # 쿨다운에 걸리지 않도록 5분 간격으로 5건을 심는다.
    for i in range(5):
        await _record_at(conn, "a@example.com", "1.1.1.1", now - timedelta(minutes=5 * (i + 1)))

    with pytest.raises(AppError) as exc:
        await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    assert exc.value.status_code == 429


async def test_email_limit_ignores_requests_outside_the_window(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    # 창(1시간) 밖의 5건은 세지 않는다.
    for i in range(5):
        await _record_at(conn, "a@example.com", "1.1.1.1", now - timedelta(minutes=61 + i))

    await check_and_record(conn, "a@example.com", "1.1.1.1", now)


async def test_ip_hourly_limit_across_different_emails(db_session, limits):
    """이메일을 바꿔가며 때려도 IP 축에 걸린다 — 발신 계정 하루 한도를 지킨다."""
    conn = await raw_connection(db_session)
    now = now_local()
    for i in range(20):
        await _record_at(conn, f"user{i}@example.com", "9.9.9.9", now - timedelta(minutes=i + 1))

    with pytest.raises(AppError) as exc:
        await check_and_record(conn, "fresh@example.com", "9.9.9.9", now)

    assert exc.value.status_code == 429


async def test_unknown_ip_disables_the_ip_axis(db_session, limits):
    """IP를 알 수 없어도 이메일 축은 계속 동작해야 한다."""
    conn = await raw_connection(db_session)
    now = now_local()
    for i in range(20):
        await _record_at(conn, f"user{i}@example.com", None, now - timedelta(minutes=i + 1))

    # IP 축은 꺼지므로 새 이메일은 통과한다.
    await check_and_record(conn, "fresh@example.com", None, now)


async def test_rejected_request_is_not_recorded(db_session, limits):
    """거부까지 기록하면 공격이 이어지는 동안 창이 밀려 피해자가 영영 못 푼다."""
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    # 쿨다운 안에서 10번 두들긴다 — 전부 거부되고 아무것도 기록되지 않아야 한다.
    for i in range(10):
        with pytest.raises(AppError):
            await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=i + 1))

    # 쿨다운만 지나면 곧바로 통과한다(창이 밀리지 않았다).
    await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=61))


async def test_same_email_string_shares_one_bucket(db_session, limits):
    """같은 문자열은 같은 버킷이다.

    이 함수는 정규화하지 않는다 — 정규화는 호출자(라우터)의 책임이고, 대소문자가
    실제로 합쳐지는지는 tests/test_password_reset_request.py가 엔드포인트에서 본다.
    """
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    with pytest.raises(AppError):
        await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=10))


async def test_cooldown_zero_disables_cooldown(db_session, monkeypatch):
    monkeypatch.setenv("RESET_REQUEST_COOLDOWN_SEC", "0")
    monkeypatch.setenv("RESET_REQUEST_EMAIL_HOURLY", "5")
    monkeypatch.setenv("RESET_REQUEST_IP_HOURLY", "20")
    get_settings.cache_clear()
    try:
        conn = await raw_connection(db_session)
        now = now_local()
        await check_and_record(conn, "a@example.com", "1.1.1.1", now)
        # 쿨다운이 꺼졌으므로 같은 시각에 한 번 더 해도 통과한다(시간당 한도까지).
        await check_and_record(conn, "a@example.com", "1.1.1.1", now)
    finally:
        get_settings.cache_clear()


async def test_failure_log_names_the_axis_but_response_does_not(db_session, limits, caplog):
    """어느 축에 걸렸는지는 서버 로그에만 남긴다. 응답으로 구분해 주면 우회 경로를 알려주는 셈이다."""
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    with caplog.at_level("WARNING"):
        with pytest.raises(AppError) as exc:
            await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=1))

    assert "cooldown" in caplog.text
    assert "cooldown" not in exc.value.message
