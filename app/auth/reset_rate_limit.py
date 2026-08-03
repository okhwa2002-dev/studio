import logging
from datetime import datetime, timedelta

from app.config import get_settings
from app.queries import queries
from app.utils.errors import AppError

logger = logging.getLogger(__name__)

# 이메일·IP 시간당 한도의 창. 설정 키 이름(`..._HOURLY`)에 이미 들어 있어 .env로 빼지 않는다.
RESET_REQUEST_WINDOW_MINUTES = 60

# 어느 축에 걸렸는지 응답으로 구분하지 않는다 — 구분해 주면 공격자가 어느 축을
# 우회해야 하는지 알게 된다.
_TOO_MANY = AppError(
    429, "TOO_MANY_RESET_REQUESTS", "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."
)


async def check_and_record(conn, email: str, client_ip: str | None, now: datetime) -> None:
    """재설정 요청 한도를 보고, 통과하면 이번 요청을 기록한다.

    호출자는 **계정을 조회하기 전에** 이 함수를 불러야 한다. 발송이 일어날 때만
    제한하면 429를 받았다는 사실이 곧 "그 계정은 존재한다"가 되어, 응답 본문을
    통일해 지켜 온 계정 열거 방지가 깨진다.

    email은 **정규화된**(strip().lower()) 값이어야 한다. 아니면 대소문자만 바꿔
    제한을 무한히 우회할 수 있다.

    거부된 요청은 기록하지 않는다. 기록하면 공격자가 때리는 동안 창이 끝없이 밀려
    피해자가 영원히 재설정하지 못한다 — 보호 장치가 그대로 공격 도구가 된다.

    커밋하지 않는다. 호출자가 커밋 시점을 정한다.
    """
    settings = get_settings()
    row = await queries.count_recent_reset_requests(
        conn,
        email=email,
        client_ip=client_ip,
        cooldown_since=now - timedelta(seconds=settings.reset_request_cooldown_sec),
        window_since=now - timedelta(minutes=RESET_REQUEST_WINDOW_MINUTES),
    )

    # 판정은 셋 다 >= 다. 설정값은 "1시간에 허용하는 최대 통과 횟수"라,
    # EMAIL_HOURLY=5면 5건이 쌓인 시점의 6번째가 거부된다.
    if row["email_cooldown"] >= 1:
        axis = "cooldown"
    elif row["email_window"] >= settings.reset_request_email_hourly:
        axis = "email"
    elif row["ip_window"] >= settings.reset_request_ip_hourly:
        axis = "ip"
    else:
        axis = None

    if axis is not None:
        # 감사 로그에는 남기지 않는다 — 무차별 공격 시 로그가 넘치고, 그건 재설정
        # 설계 §2.4가 요청·실패를 기록하지 않기로 한 이유와 같다. 어느 축인지는
        # 운영자가 대응하려면 필요하므로 서버 로그에만 남긴다.
        logger.warning(
            "재설정 요청 한도 초과: axis=%s email=%s ip=%s", axis, email, client_ip
        )
        raise _TOO_MANY

    await queries.insert_reset_request(
        conn, email=email, client_ip=client_ip, created_at=now, updated_at=now
    )
