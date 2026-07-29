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
