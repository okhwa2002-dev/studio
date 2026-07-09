import logging
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import get_settings

LOG_FILENAME = "studio.log"
LOGGER_NAME = "app"


def _local_time_converter(seconds: float | None = None) -> time.struct_time:
    """로그 타임스탬프를 OS/서버 타임존이 아닌 APP_TIMEZONE 기준으로 변환한다."""
    if seconds is None:
        seconds = time.time()
    tz = ZoneInfo(get_settings().app_timezone)
    return datetime.fromtimestamp(seconds, tz).timetuple()


def _rotated_namer(default_name: str) -> str:
    """기본 '파일명.YYYYMMDD' 형식을 '파일명_YYYYMMDD'로 바꾼다."""
    base, _, date_part = default_name.rpartition(".")
    return f"{base}_{date_part}"


def configure_logging() -> logging.Logger:
    """앱 로거를 설정한다.

    - 위치: LOG_DIR/studio.log (당일 로그)
    - 자정마다 로테이션되어 전날 로그는 studio.log_YYYYMMDD로 이름이 바뀜
    - 타임스탬프는 APP_TIMEZONE 기준 로컬시간
    """
    settings = get_settings()
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = TimedRotatingFileHandler(
        filename=str(log_dir / LOG_FILENAME),
        when="midnight",
        interval=1,
        backupCount=0,
        encoding="utf-8",
    )
    handler.suffix = "%Y%m%d"
    handler.namer = _rotated_namer

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    formatter.converter = _local_time_converter
    handler.setFormatter(formatter)

    logger = logging.getLogger(LOGGER_NAME)
    for existing in list(logger.handlers):
        existing.close()
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Alembic 등 다른 라이브러리가 logging.config.fileConfig()를
    # disable_existing_loggers=True(기본값)로 호출하면 기존 로거가
    # 통째로 비활성화될 수 있다. 재설정 시 항상 되살린다.
    logger.disabled = False
    return logger
