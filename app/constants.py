from enum import StrEnum


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


class StageStatus(StrEnum):
    """stages.status 코드값. DB에 대문자로 저장된다."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
