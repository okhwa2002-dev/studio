from enum import StrEnum


class YN(StrEnum):
    """참/거짓을 나타내는 *_yn 컬럼의 값. DB에 'Y'/'N' 한 글자로 저장된다."""

    Y = "Y"
    N = "N"


class UserRole(StrEnum):
    """users.role 코드값. DB에 대문자로 저장된다."""

    MEMBER = "MEMBER"
    ADMIN = "ADMIN"


class UserStatus(StrEnum):
    """users.status 코드값. DB에 대문자로 저장된다."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    REJECTED = "REJECTED"


class ProjectStatus(StrEnum):
    """projects.status 코드값. DB에 대문자로 저장된다."""

    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    DONE = "DONE"


class StageName(StrEnum):
    """stages.name 코드값. provider 레지스트리 키와 맞춰 소문자."""

    SCRIPT = "script"
    VOICE = "voice"
    CAPTIONS = "captions"
    RENDER = "render"


# 단계의 한국어 이름. 감사 로그 summary가 쓴다.
# 여기 둔 이유: 승인 경로가 두 개(HTTP 엔드포인트 app/api/projects.py, 워커의 자동 승인
# app/core/worker.py)라 어느 한쪽에 두면 다른 쪽이 복제해야 하고, 복제되는 순간
# "대본 단계 승인"과 "script 단계 자동 승인"처럼 같은 사건의 표기가 갈라진다.
# 프론트의 STAGE_LABEL(web/src/lib/projects.ts)과 같은 값이다.
STAGE_LABEL = {
    StageName.SCRIPT: "대본",
    StageName.VOICE: "음성",
    StageName.CAPTIONS: "자막",
    StageName.RENDER: "영상",
}


class StageStatus(StrEnum):
    """stages.status 코드값. DB에 대문자로 저장된다."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"  # 실행 요청됨 — 워커가 아직 집지 않은 상태
    RUNNING = "RUNNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    FAILED = "FAILED"


class AssetKind(StrEnum):
    """assets.kind 코드값. DB에 대문자로 저장된다."""

    AUDIO = "AUDIO"
    SRT = "SRT"
    VIDEO = "VIDEO"


class NoticeStatus(StrEnum):
    """notices.status 코드값. DB에 대문자로 저장된다."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class FaqCategory(StrEnum):
    """faqs.category 코드값. DB에 대문자로 저장된다."""

    ACCOUNT = "ACCOUNT"  # 계정
    PROJECT = "PROJECT"  # 프로젝트
    PRODUCTION = "PRODUCTION"  # 영상제작
    ETC = "ETC"  # 기타


class FaqStatus(StrEnum):
    """faqs.status 코드값. DB에 대문자로 저장된다.

    NoticeStatus와 값이 같지만 공유하지 않는다 — UserStatus·ProjectStatus·StageStatus가
    각자 자기 열거형을 갖는 규칙을 따르고, 한쪽에 상태를 추가할 때 다른 도메인이
    딸려 오지 않게 한다.
    """

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class AuditAction(StrEnum):
    """audit_logs.action 코드값. DB에 대문자로 저장된다.

    이 목록이 곧 관리자 화면 필터의 선택지다. 항목을 추가하면
    web/src/lib/auditLogs.ts의 AUDIT_ACTION_LABEL에도 라벨을 추가해야 화면에 뜬다.
    """

    # 인증
    REGISTER = "REGISTER"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    TOKEN_REUSE_DETECTED = "TOKEN_REUSE_DETECTED"

    # 사용자 관리
    USER_APPROVE = "USER_APPROVE"
    USER_REJECT = "USER_REJECT"
    USER_UNLOCK = "USER_UNLOCK"
    USER_RESET_PASSWORD = "USER_RESET_PASSWORD"
    USER_RESET_FAILURES = "USER_RESET_FAILURES"

    # 콘텐츠
    NOTICE_CREATE = "NOTICE_CREATE"
    NOTICE_UPDATE = "NOTICE_UPDATE"
    NOTICE_DELETE = "NOTICE_DELETE"
    FAQ_CREATE = "FAQ_CREATE"
    FAQ_UPDATE = "FAQ_UPDATE"
    FAQ_DELETE = "FAQ_DELETE"

    # 시스템
    SYSTEM_SETTINGS_UPDATE = "SYSTEM_SETTINGS_UPDATE"

    # 프로젝트
    PROJECT_CREATE = "PROJECT_CREATE"
    PROJECT_DELETE = "PROJECT_DELETE"
    # 보관 기간이 지난 소프트 삭제 프로젝트를 정리 잡이 되돌릴 수 없게 지운 사건.
    # 사람이 아니라 잡이 주체라 actor_id·http_*가 전부 NULL이다(2-4가 허용한 경우).
    PROJECT_PURGE = "PROJECT_PURGE"
    SCRIPT_UPDATE = "SCRIPT_UPDATE"
    STAGE_RUN = "STAGE_RUN"
    # 수동 승인과 auto_run 워커의 자동 승인이 같은 코드를 쓴다 — 둘을 가르는 것은
    # summary("… 단계 승인" / "… 단계 자동 승인")다. 자동 승인을 빼면 auto_run 프로젝트가
    # "아무도 승인하지 않았는데 완료된 프로젝트"로 보인다.
    STAGE_APPROVE = "STAGE_APPROVE"
    STAGE_REGENERATE = "STAGE_REGENERATE"


class AuditTarget(StrEnum):
    """audit_logs.target_type 코드값.

    STAGE가 없는 것은 의도적이다 — 단계는 프로젝트에 종속된 행이라 단독으로 의미가
    없고, 대상을 PROJECT로 통일해야 "이 프로젝트에 무슨 일이 있었나"가 한 값으로 모인다.
    단계 이름은 summary가 말해준다.
    """

    USER = "USER"
    PROJECT = "PROJECT"
    NOTICE = "NOTICE"
    FAQ = "FAQ"
    SYSTEM = "SYSTEM"
