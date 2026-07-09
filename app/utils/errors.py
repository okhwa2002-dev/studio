from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.error_code import ErrorCode


class AppError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedError:
    code: str
    message: str
    http_status: int


_HARDCODED_FALLBACK = ResolvedError(
    code="UNKNOWN_ERROR",
    message="알 수 없는 오류가 발생했습니다.",
    http_status=500,
)


async def resolve_error(
    session: AsyncSession, code: str, message: str | None = None
) -> ResolvedError:
    row = (
        await session.execute(
            select(ErrorCode).where(ErrorCode.code == code, ErrorCode.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if row is not None:
        return ResolvedError(row.code, message or row.message, row.http_status)

    default = (
        await session.execute(
            select(ErrorCode).where(ErrorCode.is_default == True, ErrorCode.is_active == True)  # noqa: E712
        )
    ).scalars().first()
    if default is not None:
        return ResolvedError(default.code, message or default.message, default.http_status)

    return _HARDCODED_FALLBACK
