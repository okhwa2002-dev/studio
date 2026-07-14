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
