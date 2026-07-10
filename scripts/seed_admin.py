import asyncio

from app.auth.seed_admin import ensure_admin_seeded
from app.config import get_settings
from app.db import async_session_maker, raw_connection


async def main() -> None:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        print("ADMIN_EMAIL / ADMIN_PASSWORD가 .env에 설정되어 있지 않습니다.")
        return

    async with async_session_maker() as session:
        conn = await raw_connection(session)
        created = await ensure_admin_seeded(conn, settings.admin_email, settings.admin_password)
        await session.commit()

    if created:
        print(f"관리자 계정을 생성했습니다: {settings.admin_email}")
    else:
        print(f"이미 존재하는 계정입니다: {settings.admin_email}")


if __name__ == "__main__":
    asyncio.run(main())
