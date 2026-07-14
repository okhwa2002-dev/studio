import asyncio

from app.auth.seed_sample_users import (
    SAMPLE_PASSWORD,
    SAMPLE_USERS,
    ensure_sample_users_seeded,
    is_local_database,
)
from app.config import get_settings
from app.db import async_session_maker, raw_connection


async def main() -> None:
    settings = get_settings()

    # 이 스크립트는 비밀번호가 소스에 적힌, 로그인 가능한 계정을 만든다.
    # 운영 DB에 붙은 채 실행되면 그대로 백도어가 되므로 로컬에서만 동작시킨다.
    if not is_local_database(settings.database_url):
        print("로컬 DB가 아닙니다. 샘플 데이터는 로컬에서만 생성할 수 있습니다.")
        return

    async with async_session_maker() as session:
        conn = await raw_connection(session)
        created = await ensure_sample_users_seeded(conn)
        await session.commit()

    if created == 0:
        print("이미 존재하는 샘플 사용자입니다. 새로 생성한 계정이 없습니다.")
        return

    print(f"샘플 사용자 {created}명을 생성했습니다. (전체 {len(SAMPLE_USERS)}명)")
    print(f"비밀번호는 모두 {SAMPLE_PASSWORD} 입니다.")


if __name__ == "__main__":
    asyncio.run(main())
