from pathlib import Path

import aiosql

QUERIES_DIR = Path(__file__).parent

# app/queries/*.sql 안의 이름 붙은 쿼리를 로드한다.
# 예: app/queries/users.sql에 "-- name: find_by_id" 쿼리를 정의하면 queries.find_by_id(conn, id=...)
# (하위 디렉토리를 만들면 그 디렉토리명으로 네임스페이스가 생긴다: queries.<dir>.<name>)
# mandatory_parameters=False: 설치된 aiosql(15.0)은 기본값(True)에서 ^/!/*! 연산자에
# "-- name: foo(param1, param2)^"처럼 괄호 안 파라미터 목록을 강제한다. 이 프로젝트의
# 쿼리는 SQL 본문의 :param 자리표시자만으로 파라미터를 추론하는 짧은 표기를 쓰므로,
# 이 옵션으로 그 요구를 끈다(파라미터 목록을 명시해도 여전히 유효한 문법이다).
queries = aiosql.from_path(
    QUERIES_DIR, "asyncpg", encoding="utf-8", mandatory_parameters=False
)
