import logging
import sys
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

    - 파일: LOG_DIR/studio.log (당일 로그)
      자정마다 로테이션되어 전날 로그는 studio.log_YYYYMMDD로 이름이 바뀜
    - 콘솔: stdout
    - 타임스탬프는 APP_TIMEZONE 기준 로컬시간 (파일·콘솔 동일 형식)
    """
    settings = get_settings()
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 파일과 콘솔이 하나의 포매터를 공유한다. 따로 만들면 형식을 바꿀 때
    # 한쪽만 고치게 되고, 같은 로그가 두 곳에서 다르게 보이기 시작한다.
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    formatter.converter = _local_time_converter

    file_handler = TimedRotatingFileHandler(
        filename=str(log_dir / LOG_FILENAME),
        when="midnight",
        interval=1,
        backupCount=0,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y%m%d"
    file_handler.namer = _rotated_namer
    file_handler.setFormatter(formatter)

    # stderr(StreamHandler 기본값)가 아니라 stdout으로 보낸다. npm run dev의
    # concurrently가 출력을 묶을 때, 정상 로그가 에러 스트림으로 나가면
    # 도구에 따라 에러로 오인된다.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(LOGGER_NAME)
    for existing in list(logger.handlers):
        existing.close()
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    # Alembic 등 다른 라이브러리가 logging.config.fileConfig()를
    # disable_existing_loggers=True(기본값)로 호출하면 기존 로거가
    # 통째로 비활성화될 수 있다. 재설정 시 항상 되살린다.
    logger.disabled = False
    return logger
