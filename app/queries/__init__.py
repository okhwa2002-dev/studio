from pathlib import Path

import aiosql

QUERIES_DIR = Path(__file__).parent

# app/queries/*.sql 안의 이름 붙은 쿼리를 로드한다.
# 예: queries.find_active_by_code(conn, code=...)
# (하위 디렉토리를 만들면 그 디렉토리명으로 네임스페이스가 생긴다: queries.<dir>.<name>)
queries = aiosql.from_path(QUERIES_DIR, "asyncpg", encoding="utf-8")
