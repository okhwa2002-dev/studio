from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw_connection
from app.queries import queries


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


HARDCODED_FALLBACK = ResolvedError(
    code="UNKNOWN_ERROR",
    message="알 수 없는 오류가 발생했습니다.",
    http_status=500,
)


async def resolve_error(
    session: AsyncSession, code: str, message: str | None = None
) -> ResolvedError:
    conn = await raw_connection(session)

    row = await queries.find_active_by_code(conn, code=code)
    if row is not None:
        return ResolvedError(row["code"], message or row["message"], row["http_status"])

    default = await queries.find_default(conn)
    if default is not None:
        return ResolvedError(default["code"], message or default["message"], default["http_status"])

    return HARDCODED_FALLBACK
