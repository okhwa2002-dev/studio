import logging
import re
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.utils.logging import _local_time_converter, _rotated_namer, configure_logging


def _is_console_handler(handler: logging.Handler) -> bool:
    # TimedRotatingFileHandler도 StreamHandler의 하위 클래스이므로
    # 파일 핸들러를 명시적으로 제외해야 콘솔 핸들러만 골라낼 수 있다.
    return isinstance(handler, logging.StreamHandler) and not isinstance(
        handler, logging.FileHandler
    )


def test_rotated_namer_uses_filename_underscore_yyyymmdd():
    default_name = r"D:\workspace\ok2020\log\studio\studio.log.20260709"
    assert _rotated_namer(default_name) == r"D:\workspace\ok2020\log\studio\studio.log_20260709"


def test_local_time_converter_uses_configured_timezone():
    # 2026-01-01 00:00:00 UTC 시점의 epoch
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")).timestamp()
    tz = ZoneInfo(get_settings().app_timezone)
    expected = datetime.fromtimestamp(epoch, tz).timetuple()

    actual = _local_time_converter(epoch)

    assert actual == expected


def test_configure_logging_creates_log_dir_and_writes_local_time(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    logger = None
    try:
        logger = configure_logging()
        logger.info("hello test")
        for h in logger.handlers:
            h.flush()

        log_file = tmp_path / "studio.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "hello test" in content
    finally:
        if logger is not None:
            for h in list(logger.handlers):
                h.close()
            logger.handlers.clear()
        get_settings.cache_clear()


def test_configure_logging_reenables_a_disabled_logger(tmp_path, monkeypatch):
    # Alembic 등 다른 라이브러리가 logging.config.fileConfig()를
    # disable_existing_loggers=True(기본값)로 호출하면 우리 "app" 로거가
    # 통째로 비활성화될 수 있다. configure_logging()은 이를 되살려야 한다.
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    logger = None
    try:
        logging.getLogger("app").disabled = True

        logger = configure_logging()

        assert logger.disabled is False
        logger.info("still logs after re-enable")
        for h in logger.handlers:
            h.flush()
        content = (tmp_path / "studio.log").read_text(encoding="utf-8")
        assert "still logs after re-enable" in content
    finally:
        if logger is not None:
            for h in list(logger.handlers):
                h.close()
            logger.handlers.clear()
        get_settings.cache_clear()


def test_configure_logging_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    logger = None
    try:
        logger = configure_logging()
        configure_logging()

        # 파일 1개 + 콘솔 1개. 재설정해도 핸들러가 쌓이지 않아야 한다.
        assert len(logger.handlers) == 2
        assert sum(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers) == 1
        assert sum(_is_console_handler(h) for h in logger.handlers) == 1
    finally:
        if logger is not None:
            for h in list(logger.handlers):
                h.close()
            logger.handlers.clear()
        get_settings.cache_clear()


def test_console_handler_shares_formatter_and_writes_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    logger = None
    try:
        logger = configure_logging()

        console = next(h for h in logger.handlers if _is_console_handler(h))
        file_handler = next(h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler))

        # 형식이 갈라지지 않도록 두 핸들러가 같은 포매터 객체를 공유한다.
        assert console.formatter is file_handler.formatter

        record = logging.LogRecord(
            name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="콘솔 로그", args=(), exc_info=None,
        )
        formatted = console.format(record)

        # "2026-07-14 15:42:07 INFO app.test - 콘솔 로그" 형태
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} INFO app\.test - 콘솔 로그$", formatted)
    finally:
        if logger is not None:
            for h in list(logger.handlers):
                h.close()
            logger.handlers.clear()
        get_settings.cache_clear()
