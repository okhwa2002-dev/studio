from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.utils.time import now_local


def test_now_local_returns_naive_datetime_in_configured_timezone():
    tz = ZoneInfo(get_settings().app_timezone)
    expected = datetime.now(tz).replace(tzinfo=None)

    actual = now_local()

    assert actual.tzinfo is None
    assert abs((actual - expected).total_seconds()) < 5


def test_now_local_respects_app_timezone_setting(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    get_settings.cache_clear()
    try:
        utc_wall = now_local()
    finally:
        get_settings.cache_clear()

    seoul_wall = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    # 서울은 UTC보다 9시간 빠르므로, 같은 순간이라도 벽시계 값은 9시간 차이가 나야 한다.
    assert abs((seoul_wall - utc_wall).total_seconds() - 9 * 3600) < 5
