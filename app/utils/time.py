from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def now_local() -> datetime:
    """설정된 로컬 타임존(APP_TIMEZONE)의 현재 벽시계 시각(naive)을 반환한다."""
    tz = ZoneInfo(get_settings().app_timezone)
    return datetime.now(tz).replace(tzinfo=None)
