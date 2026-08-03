import logging
import re
from email.message import EmailMessage
from pathlib import Path

from app.config import get_settings
from app.utils.time import now_local

logger = logging.getLogger(__name__)

# LOG_DIR 아래 이 이름의 디렉토리에 .eml을 떨군다.
MAIL_DIR_NAME = "mail"

# 파일명에 그대로 쓸 수 있는 문자만 남긴다.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def _build_message(to: str, subject: str, body: str) -> EmailMessage:
    """메일 1통을 조립한다.

    헤더를 손으로 만들지 않는다 — EmailMessage가 본문 UTF-8 인코딩과 제목의
    RFC 2047 인코딩을 처리한다. 한글 제목을 직접 조립하면 클라이언트에 따라 깨진다.
    """
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def _eml_path(to: str) -> Path:
    """LOG_DIR/mail/{시각}_{수신자}.eml

    밀리초까지 넣는 이유는 같은 초에 두 통이 나가도 덮어쓰지 않게 하기 위함이다.
    """
    stamp = now_local().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    safe = _UNSAFE_FILENAME.sub("_", to.replace("@", "_at_"))
    return Path(get_settings().log_dir) / MAIL_DIR_NAME / f"{stamp}_{safe}.eml"


def _save_to_file(message: EmailMessage) -> Path:
    path = _eml_path(message["To"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(message))
    return path


async def send_email(to: str, subject: str, body: str) -> None:
    """메일 1통을 보낸다.

    SMTP_HOST가 없으면 보내는 대신 LOG_DIR/mail/*.eml로 저장한다. 콘솔·서버 로그가
    아니라 파일인 이유는, 인증코드 같은 본문이 로그 수집기를 타고 나가지 않게 하기
    위함이다(log/는 .gitignore 대상이라 저장소에도 섞이지 않는다).

    이 함수는 누가 왜 보내는지 모른다 — 새 메일 종류가 생기면 이 위층에 함수를
    하나 더할 뿐 여기는 손대지 않는다.
    """
    message = _build_message(to, subject, body)
    path = _save_to_file(message)
    logger.info("SMTP 미설정 — 메일을 파일로 저장했습니다: %s", path)
