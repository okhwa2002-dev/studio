# Studio — Plan 1: 기반(Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI + PostgreSQL 기반 프로젝트 골격을 세우고, 공통 `BaseEntity`(정수 PK + 감사/타임스탬프 컬럼)와 중앙 에러 코드 카탈로그(디폴트 폴백)까지 동작하는 실행 가능한 첫 슬라이스를 만든다.

**Architecture:** 경량 모놀리식. `app/` 단일 패키지 안에서 3계층(core/providers/utils)으로 나누되, 이 계획은 그 토대(설정·DB·공통 모델·에러 처리·앱 부트스트랩)만 다룬다. 데이터는 PostgreSQL, 마이그레이션은 Alembic(async), 테스트는 pytest + testcontainers로 실제 Postgres에 대해 수행한다.

**Tech Stack:** Python 3.12, uv(패키지/venv), FastAPI, SQLModel(SQLAlchemy 2 async), asyncpg, Alembic, pydantic-settings, pytest + pytest-asyncio + testcontainers[postgres], httpx.

## Global Constraints

- Python 버전: **3.12 이상**.
- 패키지/가상환경 관리자: **uv** (`uv add`, `uv run`).
- DB: **PostgreSQL 16**. 모든 접속은 `postgresql+asyncpg://` 드라이버.
- 모든 테이블 PK: **정수(BIGINT) 자동 증가(IDENTITY)**.
- 모든 테이블은 `BaseEntity` 상속 → 공통 컬럼: `id`, `created_at`, `updated_at`, `created_by`, `updated_by`.
- 모든 일시 컬럼: `TIMESTAMPTZ`, **UTC 저장**. 표시(로컬 변환)는 프론트/응답 계층 책임(이 계획 범위 아님).
- `created_by`/`updated_by`: nullable `int`. **FK 제약은 Plan 2(users 생성 후)에서 추가** — 이 계획에서는 순수 nullable 정수 컬럼.
- API 에러 응답 포맷: 항상 `{"code": <str>, "message": <str>}`.
- 시크릿은 `.env`에서만 로드. `.env`는 git 미포함(`.env.example`만 커밋).
- 커밋은 각 Task 마지막 단계에서 수행(자주 커밋).

---

## File Structure

```
studio/
├─ pyproject.toml               # 프로젝트/의존성 (uv)
├─ .env.example                 # 설정 예시(커밋)
├─ docker-compose.yml           # 로컬 Postgres
├─ alembic.ini                  # Alembic 설정
├─ alembic/
│  ├─ env.py                    # async 마이그레이션 환경
│  └─ versions/                 # 마이그레이션 파일
├─ app/
│  ├─ __init__.py
│  ├─ config.py                 # Settings (pydantic-settings)
│  ├─ db.py                     # async 엔진/세션, get_db 의존성
│  ├─ main.py                   # FastAPI 앱, 예외 핸들러 등록
│  ├─ models/
│  │  ├─ __init__.py            # 모든 모델 재노출(Alembic 자동감지용)
│  │  ├─ base.py                # BaseEntity 믹스인 + 타임스탬프 이벤트
│  │  └─ error_code.py          # ErrorCode 테이블
│  ├─ utils/
│  │  ├─ __init__.py
│  │  └─ errors.py              # AppError 예외 + resolve_error() + 캐시
│  └─ api/
│     ├─ __init__.py
│     └─ health.py              # /health 라우터
└─ tests/
   ├─ __init__.py
   ├─ conftest.py               # testcontainers Postgres + async 세션/클라이언트 픽스처
   ├─ test_config.py
   ├─ test_db.py
   ├─ test_base_entity.py
   ├─ test_error_code_migration.py
   ├─ test_errors.py
   └─ test_health.py
```

각 파일은 하나의 책임만 진다: `config`(설정), `db`(연결), `models/*`(스키마), `utils/errors`(에러 규약), `api/*`(라우트), `main`(조립).

---

### Task 1: 프로젝트 스캐폴딩 & 설정

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py` (빈 파일)
- Create: `app/config.py`
- Create: `.env.example`
- Create: `tests/__init__.py` (빈 파일)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: (없음 — 첫 태스크)
- Produces: `app.config.Settings` (pydantic-settings), `app.config.get_settings() -> Settings` (lru_cache). 필드: `database_url: str`, `jwt_secret: str`, `app_timezone: str = "Asia/Seoul"`, `storage_backend: str = "local"`, `storage_path: str = "./storage"`, `cors_origins: list[str] = []`, `secure_cookies: bool = False`.

- [ ] **Step 1: pyproject.toml 작성**

```toml
[project]
name = "studio"
version = "0.1.0"
description = "Shorts auto-generation web app"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlmodel>=0.0.22",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic-settings>=2.6",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "testcontainers[postgres]>=4.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-v"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 2: 의존성 설치**

Run: `uv sync`
Expected: `.venv/` 생성, 위 패키지 설치 완료(에러 없음).

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_config.py`:
```python
import importlib
import app.config as config_module


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    s = config_module.get_settings()
    assert s.database_url == "postgresql+asyncpg://u:p@localhost:5432/studio"
    assert s.jwt_secret == "test-secret"
    assert s.app_timezone == "Asia/Seoul"      # 기본값
    assert s.storage_backend == "local"        # 기본값
    assert s.secure_cookies is False           # 기본값
```

- [ ] **Step 4: 테스트 실패 확인**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError` 또는 `AttributeError` (config가 아직 없음).

- [ ] **Step 5: app/config.py 구현**

`app/__init__.py`는 빈 파일로 생성. `app/config.py`:
```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    app_timezone: str = "Asia/Seoul"
    storage_backend: str = "local"
    storage_path: str = "./storage"
    cors_origins: list[str] = []
    secure_cookies: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: .env.example 작성**

```
DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:5432/studio
JWT_SECRET=change-me-to-a-long-random-string
APP_TIMEZONE=Asia/Seoul
STORAGE_BACKEND=local
STORAGE_PATH=./storage
CORS_ORIGINS=["http://localhost:5173"]
SECURE_COOKIES=false
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 8: 커밋**

```bash
git add pyproject.toml uv.lock app/__init__.py app/config.py .env.example tests/__init__.py tests/test_config.py
git commit -m "feat: scaffold project and settings"
```

---

### Task 2: 데이터베이스 세션 & 테스트 인프라

**Files:**
- Create: `app/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `app.config.get_settings`.
- Produces:
  - `app.db.make_engine(url: str) -> AsyncEngine`
  - `app.db.engine: AsyncEngine` (앱 기본 엔진, settings 기반)
  - `app.db.async_session_maker: async_sessionmaker[AsyncSession]`
  - `app.db.get_db() -> AsyncIterator[AsyncSession]` (FastAPI 의존성)
  - conftest 픽스처: `db_engine`(세션 전체 스코프, testcontainers Postgres), `db_session`(함수 스코프 AsyncSession, 각 테스트 후 롤백).

- [ ] **Step 1: app/db.py 구현 (선구현 — 인프라 코드)**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, echo=False, pool_pre_ping=True)


engine: AsyncEngine = make_engine(get_settings().database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session
```

- [ ] **Step 2: tests/conftest.py 구현**

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from testcontainers.postgres import PostgresContainer

import app.models  # noqa: F401  (모든 모델을 metadata에 등록)
from app.db import make_engine


@pytest.fixture(scope="session")
def pg_url() -> str:
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def db_engine(pg_url):
    engine = make_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
```

> 참고: 이 시점에 `app/models/__init__.py`가 존재해야 한다. Task 3에서 실제 모델을 만들지만, import 에러를 피하기 위해 지금 빈 패키지로 생성한다.

- [ ] **Step 3: app/models 패키지 최소 생성**

`app/models/__init__.py` (빈 파일), `app/models` 디렉토리 생성.

- [ ] **Step 4: 실패하는 테스트 작성**

`tests/test_db.py`:
```python
from sqlalchemy import text


async def test_session_connects(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
```

- [ ] **Step 5: 테스트 실행 (통과 확인)**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS. (Docker가 실행 중이어야 함 — testcontainers가 Postgres 컨테이너 기동.)
만약 실패하면: Docker 데몬 실행 여부 확인.

- [ ] **Step 6: 커밋**

```bash
git add app/db.py app/models/__init__.py tests/conftest.py tests/test_db.py
git commit -m "feat: add async db session and test infrastructure"
```

---

### Task 3: BaseEntity 믹스인 (정수 PK + 감사/타임스탬프 컬럼)

**Files:**
- Create: `app/models/base.py`
- Test: `tests/test_base_entity.py`

**Interfaces:**
- Consumes: (없음)
- Produces: `app.models.base.BaseEntity` — SQLModel 믹스인. 컬럼: `id: int|None`(PK, autoincrement), `created_at: datetime`(server_default now, tz-aware), `updated_at: datetime`(server_default now, onupdate now, tz-aware), `created_by: int|None`, `updated_by: int|None`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_base_entity.py`:
```python
from datetime import datetime, timezone

from sqlmodel import Field

from app.models.base import BaseEntity


class _Sample(BaseEntity, table=True):
    __tablename__ = "sample_task3"
    name: str = Field()


async def test_base_entity_defaults(db_session):
    row = _Sample(name="a")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert isinstance(row.id, int)                 # 정수 자동 증가 PK
    assert row.created_at is not None
    assert row.updated_at is not None
    assert row.created_at.tzinfo is not None        # tz-aware (UTC 저장)
    assert row.created_by is None                    # 기본 nullable
    assert row.updated_by is None
```

> `_Sample`은 테스트 전용 모델이며 conftest의 `create_all`에 포함되도록 이 테스트 파일이 conftest보다 먼저 import될 필요는 없다 — `db_engine`은 session 스코프에서 한 번 생성되므로, 이 테스트를 실행할 때 `SQLModel.metadata`에 `_Sample`이 등록되어 있어야 한다. 이를 보장하기 위해 conftest의 `create_all` 이전에 테스트 모듈이 로드되도록, 아래 Step 3에서 `_Sample`을 `app.models`에 두지 말고 테스트 파일에 정의한다(위와 같음). pytest 수집 단계에서 모듈이 import되어 metadata에 등록된다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_base_entity.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.base`.

- [ ] **Step 3: app/models/base.py 구현**

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, func
from sqlmodel import Field, SQLModel


class BaseEntity(SQLModel):
    id: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )
    created_by: Optional[int] = Field(default=None, nullable=True)
    updated_by: Optional[int] = Field(default=None, nullable=True)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_base_entity.py -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add app/models/base.py tests/test_base_entity.py
git commit -m "feat: add BaseEntity mixin with int PK and audit columns"
```

---

### Task 4: ErrorCode 모델 & Alembic 마이그레이션

**Files:**
- Create: `app/models/error_code.py`
- Modify: `app/models/__init__.py` (ErrorCode 재노출)
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/` (디렉토리; 마이그레이션 파일은 자동생성)
- Test: `tests/test_error_code_migration.py`

**Interfaces:**
- Consumes: `app.models.base.BaseEntity`, `app.config.get_settings`.
- Produces: `app.models.error_code.ErrorCode` (table=`error_codes`). 컬럼: `code: str`(unique, index), `message: str`, `http_status: int = 400`, `is_default: bool = False`, `is_active: bool = True` + BaseEntity 상속.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_error_code_migration.py`:
```python
from sqlalchemy import text


async def test_error_codes_table_exists(db_session):
    # 테이블에 행을 넣고 다시 읽을 수 있어야 한다
    await db_session.execute(
        text(
            "INSERT INTO error_codes (code, message, http_status, is_default, is_active, created_at, updated_at) "
            "VALUES (:c, :m, :s, :d, :a, now(), now())"
        ),
        {"c": "TEST_CODE", "m": "테스트", "s": 400, "d": False, "a": True},
    )
    row = (await db_session.execute(
        text("SELECT code, message, http_status FROM error_codes WHERE code = :c"),
        {"c": "TEST_CODE"},
    )).one()
    assert row.code == "TEST_CODE"
    assert row.http_status == 400
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_error_code_migration.py -v`
Expected: FAIL — `error_codes` 테이블 없음(UndefinedTable).

- [ ] **Step 3: ErrorCode 모델 구현**

`app/models/error_code.py`:
```python
from sqlmodel import Field

from app.models.base import BaseEntity


class ErrorCode(BaseEntity, table=True):
    __tablename__ = "error_codes"

    code: str = Field(unique=True, index=True)
    message: str
    http_status: int = 400
    is_default: bool = False
    is_active: bool = True
```

`app/models/__init__.py`:
```python
from app.models.base import BaseEntity
from app.models.error_code import ErrorCode

__all__ = ["BaseEntity", "ErrorCode"]
```

- [ ] **Step 4: 테스트 통과 확인 (conftest의 create_all이 테이블 생성)**

Run: `uv run pytest tests/test_error_code_migration.py -v`
Expected: PASS. (테스트는 `create_all`로 테이블을 만들지만, 운영 배포용 마이그레이션은 아래 Step에서 별도로 생성한다.)

- [ ] **Step 5: Alembic 초기화 & 설정**

Run: `uv run alembic init -t async alembic`
그 다음 `alembic.ini`에서 `sqlalchemy.url` 라인을 주석 처리(코드에서 주입).
`alembic/env.py`를 아래 핵심으로 수정:
```python
import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from alembic import context
from app.config import get_settings
import app.models  # noqa: F401  (metadata 등록)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 6: 첫 마이그레이션 생성 (로컬 DB 필요)**

먼저 로컬 Postgres 기동: `docker compose up -d db` (Task 7에서 compose 작성 — 순서상 Task 7을 먼저 하거나, 임시로 로컬 Postgres 사용). `.env`에 `DATABASE_URL` 설정 후:
Run: `uv run alembic revision --autogenerate -m "create error_codes"`
Expected: `alembic/versions/xxxx_create_error_codes.py` 생성, `error_codes` 테이블 create 포함.

- [ ] **Step 7: 마이그레이션 적용 확인**

Run: `uv run alembic upgrade head`
Expected: 에러 없이 적용. `uv run alembic current`가 head 리비전 출력.

- [ ] **Step 8: 커밋**

```bash
git add app/models/error_code.py app/models/__init__.py alembic.ini alembic/ tests/test_error_code_migration.py
git commit -m "feat: add ErrorCode model and alembic migration"
```

---

### Task 5: 에러 리졸버 (코드 조회 → 없으면 디폴트)

**Files:**
- Create: `app/utils/__init__.py` (빈 파일)
- Create: `app/utils/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: `app.models.error_code.ErrorCode`, `AsyncSession`.
- Produces:
  - `app.utils.errors.AppError(code: str, message: str | None = None)` — 도메인 예외.
  - `app.utils.errors.ResolvedError` — dataclass: `code: str`, `message: str`, `http_status: int`.
  - `async app.utils.errors.resolve_error(session: AsyncSession, code: str, message: str | None = None) -> ResolvedError` — 코드로 활성 ErrorCode 조회; 있으면 그 값(단, `message` 인자가 오면 우선), 없으면 `is_default=True` 레코드 반환. 디폴트도 없으면 하드코딩 폴백(`code="UNKNOWN_ERROR"`, `message="알 수 없는 오류가 발생했습니다."`, `http_status=500`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_errors.py`:
```python
import pytest

from app.models.error_code import ErrorCode
from app.utils.errors import ResolvedError, resolve_error


@pytest.fixture
async def seed_errors(db_session):
    db_session.add_all([
        ErrorCode(code="AUTH_INVALID", message="인증 실패", http_status=401, is_default=False, is_active=True),
        ErrorCode(code="DEFAULT", message="요청을 처리할 수 없습니다.", http_status=400, is_default=True, is_active=True),
    ])
    await db_session.commit()


async def test_resolve_known_code(db_session, seed_errors):
    r = await resolve_error(db_session, "AUTH_INVALID")
    assert r == ResolvedError(code="AUTH_INVALID", message="인증 실패", http_status=401)


async def test_resolve_unknown_returns_default(db_session, seed_errors):
    r = await resolve_error(db_session, "NOPE")
    assert r.code == "DEFAULT"
    assert r.http_status == 400


async def test_passed_message_overrides(db_session, seed_errors):
    r = await resolve_error(db_session, "AUTH_INVALID", message="커스텀")
    assert r.message == "커스텀"
    assert r.code == "AUTH_INVALID"


async def test_no_default_falls_back_hardcoded(db_session):
    r = await resolve_error(db_session, "NOPE")
    assert r.code == "UNKNOWN_ERROR"
    assert r.http_status == 500
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: app.utils.errors`.

- [ ] **Step 3: app/utils/errors.py 구현**

`app/utils/__init__.py`는 빈 파일. `app/utils/errors.py`:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_errors.py -v`
Expected: PASS (4개 테스트 모두).

- [ ] **Step 5: 커밋**

```bash
git add app/utils/__init__.py app/utils/errors.py tests/test_errors.py
git commit -m "feat: add error resolver with default fallback"
```

---

### Task 6: FastAPI 앱 + 전역 예외 핸들러 + /health

**Files:**
- Create: `app/api/__init__.py` (빈 파일)
- Create: `app/api/health.py`
- Create: `app/main.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: `app.db.get_db`, `app.utils.errors.AppError`, `app.utils.errors.resolve_error`, `app.config.get_settings`.
- Produces: `app.main.app` (FastAPI 인스턴스). 라우트: `GET /health -> {"status": "ok"}`. `AppError` 예외 핸들러: `resolve_error`로 해석해 `{"code","message"}` + 해석된 http_status로 응답.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_health.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.main import app
from app.models.error_code import ErrorCode
from app.utils.errors import AppError


@pytest_asyncio.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_app_error_uses_resolver(client, db_session):
    db_session.add(ErrorCode(code="DEFAULT", message="기본 오류", http_status=400, is_default=True, is_active=True))
    db_session.add(ErrorCode(code="BOOM", message="터짐", http_status=418, is_default=False, is_active=True))
    await db_session.commit()

    @app.get("/_boom")
    async def _boom():
        raise AppError("BOOM")

    resp = await client.get("/_boom")
    assert resp.status_code == 418
    assert resp.json() == {"code": "BOOM", "message": "터짐"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: app.main`.

- [ ] **Step 3: /health 라우터 구현**

`app/api/__init__.py`는 빈 파일. `app/api/health.py`:
```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: app/main.py 구현**

```python
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.health import router as health_router
from app.db import get_db
from app.utils.errors import AppError, resolve_error

app = FastAPI(title="Studio")
app.include_router(health_router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    # 요청 스코프의 DB 세션으로 에러 코드 해석
    async for session in get_db():  # type: AsyncSession
        resolved = await resolve_error(session, exc.code, exc.message)
        break
    return JSONResponse(
        status_code=resolved.http_status,
        content={"code": resolved.code, "message": resolved.message},
    )
```

> 참고: 테스트에서는 `get_db`가 `db_session`으로 오버라이드되지만, 예외 핸들러는 의존성 주입 밖이라 `get_db()`를 직접 순회한다. 테스트의 오버라이드는 라우트에만 적용되므로, 핸들러의 `resolve_error`가 테스트 세션을 쓰도록 아래 Step 5에서 핸들러를 오버라이드-친화적으로 바꾼다.

- [ ] **Step 5: 예외 핸들러를 오버라이드 세션과 호환되게 수정**

`app/main.py`의 핸들러를 다음으로 교체(테스트/운영 모두 `dependency_overrides` 반영):
```python
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    provider = app.dependency_overrides.get(get_db, get_db)
    agen = provider()
    session = await agen.__anext__()
    try:
        resolved = await resolve_error(session, exc.code, exc.message)
    finally:
        await agen.aclose()
    return JSONResponse(
        status_code=resolved.http_status,
        content={"code": resolved.code, "message": resolved.message},
    )
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS (2개 테스트).

- [ ] **Step 7: 전체 테스트 실행**

Run: `uv run pytest -v`
Expected: 모든 테스트 PASS.

- [ ] **Step 8: 커밋**

```bash
git add app/api/__init__.py app/api/health.py app/main.py tests/test_health.py
git commit -m "feat: add FastAPI app, health endpoint, and AppError handler"
```

---

### Task 7: docker-compose(Postgres) & 실행 문서

**Files:**
- Create: `docker-compose.yml`
- Create: `README.md` (실행 섹션)

**Interfaces:**
- Consumes: (없음)
- Produces: 로컬 개발 실행 절차. (코드 인터페이스 없음)

- [ ] **Step 1: docker-compose.yml 작성**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: studio
      POSTGRES_USER: studio
      POSTGRES_PASSWORD: studio
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U studio"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

- [ ] **Step 2: README.md 실행 섹션 작성**

```markdown
# Studio

쇼츠 자동 생성 웹앱. (설계: docs/superpowers/specs/2026-07-09-studio-design.md)

## 개발 실행

1. 의존성 설치: `uv sync`
2. 환경 파일: `cp .env.example .env` 후 값 확인
3. DB 기동: `docker compose up -d db`
4. 마이그레이션: `uv run alembic upgrade head`
5. 서버 실행: `uv run uvicorn app.main:app --reload`
6. 확인: http://localhost:8000/health → `{"status":"ok"}`

## 테스트

`uv run pytest` (Docker 데몬 실행 필요 — testcontainers가 임시 Postgres 기동)
```

- [ ] **Step 3: 수동 검증 — 서버 기동 & 헬스체크**

Run:
```bash
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 &
sleep 2
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok"}` 출력.

- [ ] **Step 4: 커밋**

```bash
git add docker-compose.yml README.md
git commit -m "chore: add docker-compose for postgres and run docs"
```

---

## Self-Review

**1. Spec coverage (이 계획의 범위 = 기반 슬라이스):**
- 3계층 디렉토리 토대(app/, utils/, api/) → Task 1·5·6 ✓ (core/providers는 후속 계획)
- PostgreSQL + async 세션 → Task 2 ✓
- 정수 자동증가 PK + 감사 컬럼(BaseEntity) → Task 3 ✓
- 일시 UTC(TIMESTAMPTZ) 저장 → Task 3 (DateTime(timezone=True)) ✓
- Alembic 마이그레이션 → Task 4 ✓
- 에러 코드 중앙 관리(디폴트 폴백) → Task 4·5 ✓ (관리자 CRUD 화면은 Plan 5 프론트 / API는 Plan 2 이후)
- 전역 예외 핸들러 → `{code,message}` → Task 6 ✓
- 12-factor 설정(.env) → Task 1 ✓
- 배포 독립(docker-compose) → Task 7 ✓
- **후속 계획으로 미룸(의도적):** 인증/사용자(Plan 2), created_by/updated_by FK(Plan 2), 파이프라인(Plan 3), 프로바이더(Plan 4), 프론트/관리자 페이지(Plan 5).

**2. Placeholder scan:** "TBD/적절히 처리" 등 없음. 모든 코드 스텝에 실제 코드 포함 ✓.

**3. Type consistency:** `get_db`(db.py) ↔ 오버라이드(conftest/test_health) 일치. `resolve_error(session, code, message)` 시그니처가 Task 5 정의 ↔ Task 6 사용 일치. `ResolvedError(code, message, http_status)` 필드명 일치. `ErrorCode` 필드(code/message/http_status/is_default/is_active) 전 태스크 일관 ✓.

**주의 노트(실행자용):**
- Task 4 Step 6~7(alembic autogenerate/upgrade)은 로컬 Postgres가 필요하므로, 실제로는 **Task 7의 docker-compose를 먼저 기동**해두면 순조롭다. 실행 시 Task 7 Step 1을 앞당겨 수행할 것.
- 테스트는 Docker 데몬 필요(testcontainers).
