import logging
import secrets

from app.core.email import send_email
from app.core.error_log import SOURCE_EMAIL, record_error

logger = logging.getLogger(__name__)

RESET_CODE_TTL_MINUTES = 10
MAX_RESET_ATTEMPTS = 5


def generate_reset_code() -> str:
    """6자리 숫자 코드 문자열(000000~999999). secrets로 예측 불가하게 생성한다.

    VARCHAR에 문자열로 저장하므로 앞자리 0을 그대로 보존한다 — 전체 100만 개
    범위를 쓸 수 있고, 표현이 곧 사용자가 입력하는 6자리 그대로다.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


_RESET_SUBJECT = "[Studio] 비밀번호 재설정 인증코드"


async def deliver_reset_code(email: str, code: str) -> None:
    """생성된 코드를 사용자에게 이메일로 전달한다 — 이 기능의 유일한 전달 경계다.

    라우터가 이 함수를 BackgroundTasks로 예약한다(응답 이후에 실행된다). 동기로
    부르면 가입된 이메일일 때만 응답이 수 초 느려져, 응답 본문을 통일해 막아 둔
    계정 열거가 응답 시간으로 새어나간다.

    발송 실패는 삼킨다. 응답은 이미 나갔고, 실패를 알릴 방법이 있더라도 그 신호가
    곧 계정 존재를 알려준다. 실패한 코드는 10분 뒤 만료되고 정리 잡이 지우며,
    사용자가 다시 요청하면 새 코드가 나가므로 재시도할 이유도 없다.

    로그에 코드·본문을 남기지 않는다 — 수신자·예외만 남긴다.
    """
    body = (
        f"인증코드: {code}\n"
        "\n"
        f"이 코드는 {RESET_CODE_TTL_MINUTES}분 뒤에 만료됩니다.\n"
        "본인이 요청하지 않았다면 이 메일을 무시하세요.\n"
    )
    try:
        await send_email(to=email, subject=_RESET_SUBJECT, body=body)
    except Exception as exc:
        logger.warning("비밀번호 재설정 메일 발송 실패: to=%s", email, exc_info=True)
        # 사용자에게도 관리자에게도 알리지 않는 실패다(계정 열거 방지). 테이블이
        # 유일한 흔적이므로 여기 남긴다. 인증코드는 넘기지 않는다.
        await record_error(SOURCE_EMAIL, exc, context=f"to={email}")
