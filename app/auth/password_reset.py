import secrets

RESET_CODE_TTL_MINUTES = 10
MAX_RESET_ATTEMPTS = 5


def generate_reset_code() -> str:
    """6자리 숫자 코드 문자열(000000~999999). secrets로 예측 불가하게 생성한다.

    VARCHAR에 문자열로 저장하므로 앞자리 0을 그대로 보존한다 — 전체 100만 개
    범위를 쓸 수 있고, 표현이 곧 사용자가 입력하는 6자리 그대로다.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def deliver_reset_code(email: str, code: str) -> None:
    """생성된 코드를 사용자에게 전달한다 — 이 함수가 이 기능의 유일한 전달 경계다.

    지금은 아무것도 하지 않는다. 코드는 이미 password_reset_codes 테이블에 저장돼
    있고(request 엔드포인트가 커밋한다), 개발 중에는 그 테이블을 직접 조회해 code를
    확인한다:

        SELECT code FROM password_reset_codes
        WHERE user_id = (SELECT id FROM users WHERE email = '...')
        ORDER BY id DESC LIMIT 1;

    ⚠️ 운영 배포 전 반드시 이 몸통을 '등록된 이메일함으로 코드를 보내는' 실제 이메일
    발송으로 채워야 한다. 그 전까지는 실사용자가 코드를 받을 방법이 없어(DB를 볼 수
    있는 사람만 재설정 가능) 자가 재설정 기능으로 동작하지 않는다.
    """
