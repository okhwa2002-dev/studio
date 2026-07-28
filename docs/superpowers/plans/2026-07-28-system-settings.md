# 시스템 설정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자가 `/admin/system` 화면에서 파이프라인 기본값과 계정 정책을 바꾸면 재시작 없이 반영되는 설정 계층을 만든다.

**Architecture:** `system_settings(key, value)` 테이블은 **관리자가 바꾼 값만** 담는다. `RuntimeSettings` Pydantic 모델이 화이트리스트·타입·범위를 전담하고 기본값은 `.env`(`get_settings()`)에서 채우므로, DB에 행이 없으면 `.env` 값이 그대로 유효값이 된다. provider는 DB 커넥션이 없으므로 파이프라인이 `StageContext.settings`에 실어 전달한다.

**Tech Stack:** FastAPI · SQLModel · aiosql(asyncpg) · Alembic · Pydantic v2 · React 19 · Tailwind 4 · pytest

**Spec:** `docs/superpowers/specs/2026-07-28-system-settings-design.md`

## Global Constraints

- 값 직렬화는 **JSON 문자열**로 통일한다. `value` 컬럼에 `json.dumps(value)`를 넣고 `json.loads`로 읽는다. bool·int·list·str을 한 규칙으로 다루기 위함이다.
- DB에 저장하는 것은 **기본값과 다른 값뿐**이다. 기본값과 같아지면 행을 삭제한다.
- 테이블 컬럼 순서는 `id` → 업무 컬럼 → 감사 컬럼. 감사 컬럼은 클래스 본문 맨 아래에서 `created_at_field()` 등 헬퍼로 명시 선언한다.
- 모든 컬럼에 한국어 `comment`를 단다.
- 에러는 `AppError`/`Errors`로 던진다. 응답은 `{code, message}`. Pydantic 범위 위반은 FastAPI가 422로 처리한다.
- 시각은 `now_local()`을 쓴다. SQL의 `now()`를 쓰지 않는다.
- `get_settings()`(부팅 필수값, `@lru_cache`)와 `get_runtime_settings()`(DB 설정)를 섞지 않는다.
- **프론트엔드에는 테스트 러너가 없다**(`npm test`는 pytest를 실행한다). 프론트 작업의 검증은 `npm run build`와 `npm run lint`다.
- 백엔드 테스트: `uv run pytest`. 린트: `npm run lint`(web 디렉토리).
- API 키(`openai_api_key`·`anthropic_api_key`·`pexels_api_key`·`pixabay_api_key`)는 `.env`에 남는다. 이번 범위가 아니다.

---

### Task 1: `system_settings` 테이블

**Files:**
- Create: `app/models/system_setting.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/<자동생성>_create_system_settings.py`
- Test: `tests/test_system_setting_model.py`

**Interfaces:**
- Consumes: `app/models/base.py`의 `BaseEntity`, `created_at_field`, `created_by_field`, `updated_at_field`, `updated_by_field`
- Produces: `SystemSetting` 모델 (`__tablename__ = "system_settings"`, 컬럼 `id`, `key`, `value` + 감사 4개). `key`에 UNIQUE 제약.

- [ ] **Step 1: Write the failing test**

`tests/test_system_setting_model.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.system_setting import SystemSetting


async def test_can_insert_and_read_setting(db_session):
    db_session.add(SystemSetting(key="render_font_size", value="42"))
    await db_session.commit()

    row = await db_session.execute(
        text("SELECT key, value FROM system_settings WHERE key = 'render_font_size'")
    )
    assert row.one() == ("render_font_size", "42")


async def test_key_is_unique(db_session):
    db_session.add(SystemSetting(key="whisper_model", value='"small"'))
    await db_session.commit()

    db_session.add(SystemSetting(key="whisper_model", value='"medium"'))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_audit_columns_are_filled_by_db_default(db_session):
    """created_at/updated_at은 서버 기본값으로 채워진다 — 앱이 안 넣어도 NOT NULL을 만족한다."""
    db_session.add(SystemSetting(key="stock_timeout_sec", value="60"))
    await db_session.commit()

    row = await db_session.execute(
        text("SELECT created_at, updated_at FROM system_settings WHERE key = 'stock_timeout_sec'")
    )
    created_at, updated_at = row.one()
    assert created_at is not None
    assert updated_at is not None


async def test_column_order_is_id_business_audit(db_session):
    """테이블 생성 규칙: id → 업무 컬럼 → 감사 컬럼."""
    row = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'system_settings' ORDER BY ordinal_position"
        )
    )
    assert [r[0] for r in row] == [
        "id", "key", "value", "created_at", "created_by", "updated_at", "updated_by",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_system_setting_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.system_setting'`

- [ ] **Step 3: Write the model**

`app/models/system_setting.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class SystemSetting(BaseEntity, table=True):
    __tablename__ = "system_settings"
    __table_args__ = {"comment": "시스템 설정 (관리자가 기본값에서 바꾼 항목만 저장)"}

    # RuntimeSettings의 필드명과 1:1로 맞춘다. 모델에 없는 키는 읽을 때 무시된다.
    key: str = Field(
        unique=True,
        sa_column_kwargs={"comment": "설정 키 (RuntimeSettings 필드명)"},
    )
    # 타입은 DB가 아니라 RuntimeSettings가 안다. 값은 JSON 문자열로 통일해
    # bool·int·list·str을 한 규칙으로 다룬다.
    value: str = Field(
        sa_type=Text,
        sa_column_kwargs={"comment": "설정값 (JSON 직렬화 문자열)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
```

- [ ] **Step 4: 모델을 metadata에 등록**

`app/models/__init__.py` — import와 `__all__` 양쪽에 알파벳 순서대로 추가한다:

```python
from app.models.asset import Asset
from app.models.base import BaseEntity
from app.models.notice import Notice
from app.models.notice_read import NoticeRead
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.stage import Stage
from app.models.system_setting import SystemSetting
from app.models.user import User

__all__ = [
    "Asset",
    "BaseEntity",
    "Notice",
    "NoticeRead",
    "Project",
    "RefreshToken",
    "Stage",
    "SystemSetting",
    "User",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_system_setting_model.py -v`
Expected: PASS (4 passed). `conftest.py`가 `SQLModel.metadata.create_all`로 테이블을 만들므로 마이그레이션 없이도 통과한다.

- [ ] **Step 6: 마이그레이션 생성**

Run: `uv run alembic revision -m "create system_settings"`

생성된 파일의 `upgrade`/`downgrade`를 아래로 채운다. `down_revision`은 alembic이 현재 head로 자동으로 채워 두므로 **손대지 않는다**.

```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False,
                  comment="기본키, BIGINT 자동 증가"),
        sa.Column("key", sa.String(), nullable=False,
                  comment="설정 키 (RuntimeSettings 필드명)"),
        sa.Column("value", sa.Text(), nullable=False,
                  comment="설정값 (JSON 직렬화 문자열)"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.timezone("Asia/Seoul", sa.func.now()),
                  comment="생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="생성자"),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.timezone("Asia/Seoul", sa.func.now()),
                  comment="수정일시 (로컬 벽시계 시각, 수정 시 갱신)"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="수정자"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("key"),
        comment="시스템 설정 (관리자가 기본값에서 바꾼 항목만 저장)",
    )


def downgrade() -> None:
    op.drop_table("system_settings")
```

**시드 데이터를 넣지 않는다.** 빈 테이블이 "전부 기본값"을 뜻한다.

- [ ] **Step 7: 마이그레이션 체인 검증**

Run: `uv run pytest tests/test_alembic_migration.py -v`
Expected: PASS — 신선한 DB에 `alembic upgrade head`가 끝까지 적용된다.

- [ ] **Step 8: Commit**

```bash
git add app/models/system_setting.py app/models/__init__.py alembic/versions tests/test_system_setting_model.py
git commit -m "feat: add system_settings table"
```

---

### Task 2: `RuntimeSettings` 스키마

**Files:**
- Create: `app/runtime_settings.py`
- Modify: `app/config.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_runtime_settings.py`

**Interfaces:**
- Consumes: `app/config.py`의 `get_settings()`, `app/providers/base.py`의 `REGISTRY`(**함수 안에서 지연 import** — Task 6이 provider → `runtime_settings` 방향 의존을 만들기 때문에 최상단 import는 순환이 된다)
- Produces:
  - `RuntimeSettings(BaseModel)` — 14개 필드. 인자 없이 생성하면 `.env` 기본값 인스턴스.
  - `RuntimeSettings.from_overrides(overrides: dict[str, str]) -> RuntimeSettings` — JSON 문자열 dict를 받아 파싱. 모르는 키와 깨진 값은 무시.
  - `stage_setting(settings: dict, key: str)` — `ctx.settings`에서 값을 읽고 없으면 `.env` 기본값.

- [ ] **Step 1: `.env` 기본값 두 개 추가**

`app/config.py`의 `Settings` 클래스에 `failed_login_limit` 아래로 두 줄을 추가한다. 기본값 출처를 `.env` 하나로 통일하기 위해 신규 항목도 여기에 둔다:

```python
    failed_login_limit: int = 5
    # 비밀번호 최소 길이. 관리자가 시스템 설정에서 올릴 수 있고, 8 밑으로는 못 내린다.
    password_min_len: int = 8
    # 참이면 가입 즉시 ACTIVE. 거짓이면 관리자 승인 대기(PENDING).
    signup_auto_approve: bool = False
```

- [ ] **Step 2: 테스트가 단언할 기본값을 conftest에 고정한다**

`tests/conftest.py`는 지금 provider 4개와 `WHISPER_MODEL`만 고정한다. 이후 테스트들이 `render_font_size == 30` 같은 기본값을 단언하므로, 개발자 로컬 `.env` 값에 테스트가 흔들리지 않도록 나머지도 고정한다. 기존 `os.environ[...]` 블록(3-8행) 바로 아래에 추가한다:

```python
# 아래 값들은 시스템 설정 테스트가 "기본값"으로 단언하는 값이다.
# 로컬 .env에 다른 값이 있어도 테스트가 흔들리지 않도록 여기서 못박는다.
os.environ["RENDER_BG_COLOR"] = "#0f172a"
os.environ["RENDER_FONT"] = "Malgun Gothic"
os.environ["RENDER_FONT_SIZE"] = "30"
os.environ["STOCK_SOURCES"] = '["pexels", "pixabay"]'   # 복합 타입은 JSON으로 준다
os.environ["STOCK_MAX_BYTES"] = "52428800"
os.environ["STOCK_TIMEOUT_SEC"] = "30"
os.environ["FAILED_LOGIN_LIMIT"] = "5"
os.environ["PASSWORD_MIN_LEN"] = "8"
os.environ["SIGNUP_AUTO_APPROVE"] = "false"
```

이 블록은 기존 `get_settings.cache_clear()` 호출(12행)보다 **위**에 있어야 한다.

- [ ] **Step 3: Write the failing test**

`tests/test_runtime_settings.py`:

```python
import pytest
from pydantic import ValidationError

from app.runtime_settings import RuntimeSettings, stage_setting


def test_defaults_come_from_env():
    """DB 오버라이드가 없으면 .env(conftest가 고정한 값)가 그대로 유효값이다."""
    rs = RuntimeSettings()
    assert rs.script_provider == "fake"      # conftest.py가 SCRIPT_PROVIDER=fake로 고정
    assert rs.whisper_model == "small"
    assert rs.failed_login_limit == 5
    assert rs.password_min_len == 8
    assert rs.signup_auto_approve is False


def test_override_beats_default():
    rs = RuntimeSettings.from_overrides({"render_font_size": "42"})
    assert rs.render_font_size == 42
    assert rs.whisper_model == "small"       # 안 건드린 키는 기본값 유지


def test_unknown_key_is_ignored():
    rs = RuntimeSettings.from_overrides({"legacy_removed_key": '"whatever"'})
    assert not hasattr(rs, "legacy_removed_key")
    assert rs.render_font_size == 30


def test_corrupt_value_falls_back_to_default():
    """JSON이 깨진 행 하나가 앱 전체를 멈추게 하지 않는다."""
    rs = RuntimeSettings.from_overrides({"render_font_size": "not-json{"})
    assert rs.render_font_size == 30


def test_bool_and_list_round_trip():
    rs = RuntimeSettings.from_overrides(
        {"signup_auto_approve": "true", "stock_sources": '["pixabay"]'}
    )
    assert rs.signup_auto_approve is True
    assert rs.stock_sources == ["pixabay"]


def test_password_min_len_cannot_go_below_8():
    """설정으로 열되 지금 수준 아래로는 못 내린다 — 보안이 후퇴하는 경로를 만들지 않는다."""
    with pytest.raises(ValidationError):
        RuntimeSettings(password_min_len=4)


def test_render_font_size_range_is_enforced():
    with pytest.raises(ValidationError):
        RuntimeSettings(render_font_size=0)
    with pytest.raises(ValidationError):
        RuntimeSettings(render_font_size=500)


def test_bg_color_must_be_hex():
    with pytest.raises(ValidationError):
        RuntimeSettings(render_bg_color="navy")
    assert RuntimeSettings(render_bg_color="#ABCDEF").render_bg_color == "#ABCDEF"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValidationError):
        RuntimeSettings(script_provider="gpt5-turbo-ultra")


def test_known_provider_is_accepted():
    assert RuntimeSettings(script_provider="claude").script_provider == "claude"


def test_stock_sources_rejects_empty_and_duplicates():
    with pytest.raises(ValidationError):
        RuntimeSettings(stock_sources=[])
    with pytest.raises(ValidationError):
        RuntimeSettings(stock_sources=["pexels", "pexels"])


def test_stage_setting_reads_from_dict():
    assert stage_setting({"render_font_size": 99}, "render_font_size") == 99


def test_stage_setting_falls_back_to_default_when_absent():
    """provider 단위 테스트가 ctx.settings를 비워둬도 동작한다."""
    assert stage_setting({}, "render_font_size") == 30
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.runtime_settings'`

- [ ] **Step 5: Write the schema**

`app/runtime_settings.py`:

```python
import json
import logging

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.config import get_settings

logger = logging.getLogger(__name__)

_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
_WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")
_STOCK_SOURCES = ("pexels", "pixabay")


class RuntimeSettings(BaseModel):
    """관리자가 화면에서 바꿀 수 있는 설정.

    필드 정의가 곧 화이트리스트·타입·범위다. 기본값은 default_factory로 .env에서
    읽는다 — 인스턴스를 만들 때 평가되므로 테스트가 env를 바꿔도 따라온다.
    """

    # --- 파이프라인 기본값 ---
    script_provider: str = Field(default_factory=lambda: get_settings().script_provider)
    voice_provider: str = Field(default_factory=lambda: get_settings().voice_provider)
    captions_provider: str = Field(default_factory=lambda: get_settings().captions_provider)
    render_provider: str = Field(default_factory=lambda: get_settings().render_provider)
    whisper_model: str = Field(default_factory=lambda: get_settings().whisper_model)
    render_bg_color: str = Field(
        default_factory=lambda: get_settings().render_bg_color, pattern=_HEX_COLOR
    )
    render_font: str = Field(
        default_factory=lambda: get_settings().render_font, min_length=1, max_length=100
    )
    render_font_size: int = Field(
        default_factory=lambda: get_settings().render_font_size, ge=8, le=200
    )
    stock_sources: list[str] = Field(default_factory=lambda: get_settings().stock_sources)
    stock_max_bytes: int = Field(
        default_factory=lambda: get_settings().stock_max_bytes,
        ge=1_048_576, le=524_288_000,          # 1MB ~ 500MB
    )
    stock_timeout_sec: int = Field(
        default_factory=lambda: get_settings().stock_timeout_sec, ge=5, le=300
    )

    # --- 계정 · 보안 ---
    failed_login_limit: int = Field(
        default_factory=lambda: get_settings().failed_login_limit, ge=1, le=100
    )
    # 하한 8은 협상 대상이 아니다. 관리자 실수로 보안이 후퇴하는 경로를 만들지 않는다.
    password_min_len: int = Field(
        default_factory=lambda: get_settings().password_min_len, ge=8, le=128
    )
    signup_auto_approve: bool = Field(
        default_factory=lambda: get_settings().signup_auto_approve
    )

    @field_validator("script_provider", "voice_provider", "captions_provider", "render_provider")
    @classmethod
    def _known_provider(cls, value: str, info: ValidationInfo) -> str:
        # 선택지를 손으로 적지 않고 REGISTRY에서 가져온다 — provider를 추가하면
        # 설정 선택지가 자동으로 따라온다.
        #
        # 이 import는 반드시 함수 안에 둔다. provider들이 stage_setting을 쓰려고 이
        # 모듈을 import하는데, app/providers/base.py는 파일 하단에서 그 provider들을
        # 다시 import한다. 모듈 최상단에서 REGISTRY를 가져오면 순환 import가 닫혀
        # "partially initialized module" ImportError가 난다.
        from app.providers.base import REGISTRY

        stage = info.field_name.removesuffix("_provider")
        allowed = REGISTRY.get(stage, {})
        if value not in allowed:
            raise ValueError(f"알 수 없는 provider입니다: {value} (가능: {', '.join(allowed)})")
        return value

    @field_validator("whisper_model")
    @classmethod
    def _known_whisper_model(cls, value: str) -> str:
        if value not in _WHISPER_MODELS:
            raise ValueError(f"알 수 없는 모델입니다: {value} (가능: {', '.join(_WHISPER_MODELS)})")
        return value

    @field_validator("stock_sources")
    @classmethod
    def _valid_stock_sources(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("스톡 소스를 하나 이상 선택해 주세요.")
        if len(set(value)) != len(value):
            raise ValueError("스톡 소스가 중복되었습니다.")
        unknown = [v for v in value if v not in _STOCK_SOURCES]
        if unknown:
            raise ValueError(f"알 수 없는 스톡 소스입니다: {', '.join(unknown)}")
        return value

    @classmethod
    def from_overrides(cls, overrides: dict[str, str]) -> "RuntimeSettings":
        """DB에서 읽은 {key: JSON 문자열}을 .env 기본값 위에 덮어쓴다.

        모르는 키는 무시하고(예전 설정이 남아 있어도 안전), 깨진 값은 경고만
        남기고 건너뛴다(행 하나가 앱 전체를 멈추게 하지 않는다).
        """
        parsed: dict = {}
        for key, raw in overrides.items():
            if key not in cls.model_fields:
                continue
            try:
                parsed[key] = json.loads(raw)
            except (TypeError, ValueError):
                logger.warning("시스템 설정 값을 해석할 수 없어 기본값을 씁니다: %s", key)
        try:
            return cls(**parsed)
        except Exception:
            # 범위를 벗어난 값이 어떤 경로로든 DB에 들어간 경우. 전부 기본값으로 후퇴한다.
            logger.warning("시스템 설정이 유효하지 않아 기본값을 씁니다.", exc_info=True)
            return cls()


def stage_setting(settings: dict, key: str):
    """ctx.settings에서 런타임 설정값을 읽는다.

    파이프라인이 항상 주입하지만, provider 단위 테스트는 ctx.settings를 비워둘 수
    있으므로 .env 기본값으로 폴백한다.
    """
    if key in settings:
        return settings[key]
    return getattr(RuntimeSettings(), key)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_settings.py -v`
Expected: PASS (13 passed)

- [ ] **Step 7: 기존 설정 테스트가 안 깨졌는지 확인**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/runtime_settings.py app/config.py tests/conftest.py tests/test_runtime_settings.py
git commit -m "feat: add RuntimeSettings schema with env fallback"
```

---

### Task 3: 설정 조회 · 캐시

**Files:**
- Create: `app/queries/system_settings.sql`
- Modify: `app/runtime_settings.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_runtime_settings_db.py`

**Interfaces:**
- Consumes: Task 2의 `RuntimeSettings.from_overrides`, `app/db.py`의 `raw_connection`
- Produces:
  - `async get_runtime_settings(conn) -> RuntimeSettings`
  - `invalidate_runtime_settings() -> None`
  - aiosql 쿼리 `queries.select_all_settings(conn)`, `queries.upsert_setting(conn, ...)`, `queries.delete_setting(conn, key=...)`

- [ ] **Step 1: Write the failing test**

`tests/test_runtime_settings_db.py`:

```python
from app.db import raw_connection
from app.queries import queries
from app.runtime_settings import (
    get_runtime_settings,
    invalidate_runtime_settings,
)
from app.utils.time import now_local


async def _put(db_session, key: str, value: str) -> None:
    conn = await raw_connection(db_session)
    now = now_local()
    await queries.upsert_setting(
        conn, key=key, value=value, now=now, actor_id=None
    )
    invalidate_runtime_settings()


async def test_empty_table_yields_env_defaults(db_session):
    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 30
    assert rs.script_provider == "fake"


async def test_override_row_wins(db_session):
    await _put(db_session, "render_font_size", "48")
    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 48


async def test_upsert_replaces_existing_value(db_session):
    await _put(db_session, "render_font_size", "48")
    await _put(db_session, "render_font_size", "64")

    conn = await raw_connection(db_session)
    rows = await queries.select_all_settings(conn)
    matching = [r for r in rows if r["key"] == "render_font_size"]
    assert len(matching) == 1
    assert (await get_runtime_settings(conn)).render_font_size == 64


async def test_delete_setting_restores_default(db_session):
    await _put(db_session, "render_font_size", "48")
    conn = await raw_connection(db_session)
    await queries.delete_setting(conn, key="render_font_size")
    invalidate_runtime_settings()

    assert (await get_runtime_settings(conn)).render_font_size == 30


async def test_cache_serves_repeated_reads(db_session):
    """두 번째 호출은 DB를 다시 읽지 않는다 — 무효화 전까지 같은 인스턴스다."""
    conn = await raw_connection(db_session)
    first = await get_runtime_settings(conn)
    second = await get_runtime_settings(conn)
    assert first is second


async def test_invalidate_forces_reload(db_session):
    conn = await raw_connection(db_session)
    first = await get_runtime_settings(conn)
    invalidate_runtime_settings()
    second = await get_runtime_settings(conn)
    assert first is not second


async def test_db_failure_falls_back_to_defaults_without_raising(db_session, monkeypatch):
    """설정 테이블 장애가 파이프라인 전체를 멈추게 하지 않는다."""
    async def _boom(*args, **kwargs):
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(queries, "select_all_settings", _boom)
    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_settings_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_runtime_settings'`

- [ ] **Step 3: Write the queries**

`app/queries/system_settings.sql`:

```sql
-- name: select_all_settings
-- 관리자가 기본값에서 바꾼 항목 전부. 행이 없으면 전부 .env 기본값이라는 뜻이다.
SELECT key, value
FROM system_settings;

-- name: upsert_setting!
-- 같은 키가 이미 있으면 값만 갱신한다(UNIQUE(key)).
INSERT INTO system_settings (key, value, created_at, updated_at, created_by, updated_by)
VALUES (:key, :value, :now, :now, :actor_id, :actor_id)
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = EXCLUDED.updated_at,
    updated_by = EXCLUDED.updated_by;

-- name: delete_setting!
-- 값이 기본값으로 돌아가면 행을 지운다. 그래야 이후 .env 변경이 그대로 반영된다.
DELETE FROM system_settings
WHERE key = :key;
```

- [ ] **Step 4: 조회 함수와 캐시 추가**

`app/runtime_settings.py` 맨 위 import에 `time`과 쿼리를 더한다:

```python
import json
import logging
import time

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.config import get_settings
from app.providers.base import REGISTRY
from app.queries import queries
```

그리고 파일 맨 아래(`stage_setting` 뒤)에 추가한다:

```python
# 캐시를 TTL과 명시적 무효화 둘 다로 관리한다. 무효화만 두면 다중 프로세스 배포에서
# 다른 프로세스에 변경이 영원히 닿지 않고, TTL만 두면 관리자가 저장 직후 화면에서
# 이전 값을 본다. 같이 두면 같은 프로세스는 즉시, 다른 프로세스는 최대 30초에 수렴한다.
_TTL_SEC = 30.0
_cache: RuntimeSettings | None = None
_cached_at: float = 0.0


async def get_runtime_settings(conn) -> RuntimeSettings:
    """현재 유효한 런타임 설정. conn은 raw_connection()이 준 asyncpg 커넥션이다."""
    global _cache, _cached_at

    now = time.monotonic()
    if _cache is not None and now - _cached_at < _TTL_SEC:
        return _cache

    try:
        rows = await queries.select_all_settings(conn)
    except Exception:
        # DB 장애 시 조용히 .env 기본값으로 진행한다. 캐시에는 남기지 않는다 —
        # 다음 호출이 다시 시도한다.
        logger.warning("시스템 설정 조회에 실패해 기본값으로 진행합니다.", exc_info=True)
        return RuntimeSettings()

    _cache = RuntimeSettings.from_overrides({row["key"]: row["value"] for row in rows})
    _cached_at = now
    return _cache


def invalidate_runtime_settings() -> None:
    """설정 저장 직후 호출한다. 같은 프로세스는 다음 조회에서 곧바로 새 값을 본다."""
    global _cache, _cached_at
    _cache = None
    _cached_at = 0.0
```

- [ ] **Step 5: 테스트 격리 픽스처 추가**

캐시는 프로세스 전역이라 테스트끼리 샌다. `tests/conftest.py`의 `reset_events` 픽스처 아래에 추가한다:

```python
@pytest.fixture(autouse=True)
def reset_runtime_settings():
    # 런타임 설정 캐시도 프로세스 전역이다. 앞 테스트가 넣은 오버라이드가
    # 롤백된 뒤에도 캐시에 남아 다음 테스트를 오염시키는 것을 막는다.
    from app.runtime_settings import invalidate_runtime_settings

    invalidate_runtime_settings()
    yield
    invalidate_runtime_settings()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_settings_db.py -v`
Expected: PASS (7 passed)

- [ ] **Step 7: 전체 테스트로 회귀 확인**

Run: `uv run pytest -q`
Expected: PASS — 새 픽스처가 기존 테스트를 깨지 않는다.

- [ ] **Step 8: Commit**

```bash
git add app/queries/system_settings.sql app/runtime_settings.py tests/conftest.py tests/test_runtime_settings_db.py
git commit -m "feat: load runtime settings from DB with TTL cache"
```

---

### Task 4: 관리자 API

**Files:**
- Create: `app/api/admin_system.py`
- Modify: `app/main.py`
- Test: `tests/test_admin_system.py`

**Interfaces:**
- Consumes: Task 3의 `get_runtime_settings`, `invalidate_runtime_settings`, `queries.upsert_setting`, `queries.delete_setting`; `app/auth/dependencies.py`의 `require_admin`
- Produces:
  - `GET /api/admin/system/settings` → `{"settings": {...}, "defaults": {...}, "overridden": [...]}`
  - `PUT /api/admin/system/settings` — 본문은 `RuntimeSettings` 전체. 응답은 GET과 같은 형태.

- [ ] **Step 1: Write the failing test**

`tests/test_admin_system.py`:

```python
from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User


async def _login(client, db_session, email: str, role: str = UserRole.ADMIN) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345678"),
        role=role,
        status=UserStatus.ACTIVE,
        name="관리자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "pw12345678"}
    )
    assert resp.status_code == 200
    return user


async def test_get_returns_defaults_when_nothing_overridden(client, db_session):
    await _login(client, db_session, "sys-get@example.com")

    resp = await client.get("/api/admin/system/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["settings"]["render_font_size"] == 30
    assert body["settings"] == body["defaults"]
    assert body["overridden"] == []


async def test_put_saves_changed_value_and_marks_it_overridden(client, db_session):
    await _login(client, db_session, "sys-put@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    resp = await client.put(
        "/api/admin/system/settings", json={**current, "render_font_size": 48}
    )
    assert resp.status_code == 200
    assert resp.json()["settings"]["render_font_size"] == 48
    assert resp.json()["overridden"] == ["render_font_size"]

    # 다시 읽어도 유지된다 (캐시 무효화가 걸렸다는 뜻이기도 하다)
    again = await client.get("/api/admin/system/settings")
    assert again.json()["settings"]["render_font_size"] == 48


async def test_put_back_to_default_removes_the_row(client, db_session):
    """기본값과 같아지면 행을 지운다 — 그래야 이후 .env 변경이 그대로 반영된다."""
    await _login(client, db_session, "sys-reset@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    await client.put("/api/admin/system/settings", json={**current, "render_font_size": 48})
    resp = await client.put(
        "/api/admin/system/settings", json={**current, "render_font_size": 30}
    )

    assert resp.status_code == 200
    assert resp.json()["overridden"] == []

    from sqlalchemy import text

    row = await db_session.execute(text("SELECT COUNT(*) FROM system_settings"))
    assert row.scalar() == 0


async def test_put_rejects_out_of_range_value(client, db_session):
    await _login(client, db_session, "sys-range@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    resp = await client.put(
        "/api/admin/system/settings", json={**current, "password_min_len": 4}
    )
    assert resp.status_code == 422


async def test_put_rejects_unknown_provider(client, db_session):
    await _login(client, db_session, "sys-provider@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    resp = await client.put(
        "/api/admin/system/settings", json={**current, "script_provider": "nope"}
    )
    assert resp.status_code == 422


async def test_put_records_who_changed_it(client, db_session):
    admin = await _login(client, db_session, "sys-actor@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]
    await client.put("/api/admin/system/settings", json={**current, "render_font_size": 48})

    from sqlalchemy import text

    row = await db_session.execute(
        text("SELECT updated_by FROM system_settings WHERE key = 'render_font_size'")
    )
    assert row.scalar() == admin.id


async def test_member_cannot_read_settings(client, db_session):
    await _login(client, db_session, "sys-member@example.com", role=UserRole.MEMBER)
    resp = await client.get("/api/admin/system/settings")
    assert resp.status_code == 403


async def test_member_cannot_write_settings(client, db_session):
    await _login(client, db_session, "sys-member-w@example.com", role=UserRole.MEMBER)
    resp = await client.put("/api/admin/system/settings", json={})
    assert resp.status_code == 403


async def test_anonymous_is_unauthorized(client):
    resp = await client.get("/api/admin/system/settings")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_admin_system.py -v`
Expected: FAIL — 404 (라우터가 아직 없다)

- [ ] **Step 3: Write the router**

`app/api/admin_system.py`:

```python
import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db import get_db, raw_connection
from app.queries import queries
from app.runtime_settings import (
    RuntimeSettings,
    get_runtime_settings,
    invalidate_runtime_settings,
)
from app.utils.time import now_local

router = APIRouter(prefix="/admin/system", tags=["admin"])


async def _snapshot(conn) -> dict:
    """화면이 필요로 하는 세 가지를 한 번에 준다.

    settings는 현재 유효값, defaults는 .env 기본값, overridden은 DB 행이 있는 키다.
    셋 다 있어야 화면이 "변경됨" 배지와 [기본값으로] 링크를 그릴 수 있다.
    """
    current = await get_runtime_settings(conn)
    defaults = RuntimeSettings().model_dump()
    settings = current.model_dump()
    return {
        "settings": settings,
        "defaults": defaults,
        "overridden": sorted(k for k, v in settings.items() if v != defaults[k]),
    }


@router.get("/settings")
async def read_settings(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    return await _snapshot(await raw_connection(db))


@router.put("/settings")
async def write_settings(
    body: RuntimeSettings,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """전체 폼을 받아 저장한다.

    부분 업데이트를 받지 않는 이유는 "안 보낸 필드"와 "비운 필드"를 구분해야 해서
    화면과 서버가 같이 복잡해지기 때문이다. 공지 관리 모달과 같은 방식이다.
    """
    conn = await raw_connection(db)
    defaults = RuntimeSettings().model_dump()
    incoming = body.model_dump()
    now = now_local()

    for key, value in incoming.items():
        if value == defaults[key]:
            # 기본값으로 되돌린 항목은 행을 지운다 (없는 행 삭제는 그냥 0건이다).
            await queries.delete_setting(conn, key=key)
        else:
            await queries.upsert_setting(
                conn, key=key, value=json.dumps(value), now=now, actor_id=admin["id"]
            )
    await db.commit()
    invalidate_runtime_settings()

    # 커밋이 raw 커넥션을 풀에 반납한다 — 재획득 후 읽는다.
    return await _snapshot(await raw_connection(db))
```

- [ ] **Step 4: 라우터 등록**

`app/main.py` — import를 알파벳 순서에 맞춰 `admin_projects` 아래에 넣고:

```python
from app.api.admin_projects import router as admin_projects_router
from app.api.admin_system import router as admin_system_router
```

`include_router` 호출도 `admin_projects_router` 아래에 추가한다:

```python
app.include_router(admin_projects_router, prefix="/api")
app.include_router(admin_system_router, prefix="/api")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_admin_system.py -v`
Expected: PASS (9 passed)

- [ ] **Step 6: Commit**

```bash
git add app/api/admin_system.py app/main.py tests/test_admin_system.py
git commit -m "feat: add admin system settings API"
```

---

### Task 5: 파이프라인 배선

**Files:**
- Modify: `app/core/pipeline.py:107-154` (`run_claimed_stage`, `_next_provider`), `app/core/pipeline.py:189`
- Modify: `app/api/projects.py:67-80`
- Test: `tests/test_pipeline_runtime_settings.py`

**Interfaces:**
- Consumes: Task 3의 `get_runtime_settings`
- Produces:
  - `async _next_provider(conn, name: str) -> str` (기존 동기 `_next_provider(name)`를 대체)
  - `StageContext.settings`가 `{**런타임 설정 전체, **프로젝트 설정}` 병합 dict가 된다

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline_runtime_settings.py`:

```python
import json

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local


async def _admin(client, db_session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345678"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        name="관리자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "pw12345678"}
    )
    assert resp.status_code == 200
    return user


async def _override(db_session, key: str, value) -> None:
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key=key, value=json.dumps(value), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()


async def test_new_project_uses_runtime_script_provider(client, db_session):
    await _admin(client, db_session, "pipe-new@example.com")
    await _override(db_session, "script_provider", "claude")

    resp = await client.post(
        "/api/projects", json={"title": "테스트", "topic": "주제", "auto_run": False}
    )
    assert resp.status_code == 201
    script = next(s for s in resp.json()["stages"] if s["name"] == "script")
    assert script["provider"] == "claude"


async def test_existing_stage_keeps_its_provider_when_setting_changes(client, db_session):
    """이미 만들어진 단계는 스냅샷이다 — 설정을 바꿔도 따라 바뀌지 않는다."""
    await _admin(client, db_session, "pipe-snap@example.com")

    created = await client.post(
        "/api/projects", json={"title": "테스트", "topic": "주제", "auto_run": False}
    )
    project_id = created.json()["id"]
    assert next(
        s for s in created.json()["stages"] if s["name"] == "script"
    )["provider"] == "fake"

    await _override(db_session, "script_provider", "claude")

    detail = await client.get(f"/api/projects/{project_id}")
    script = next(s for s in detail.json()["stages"] if s["name"] == "script")
    assert script["provider"] == "fake"


async def test_stage_context_receives_runtime_settings(client, db_session, monkeypatch):
    """provider는 DB를 읽지 않는다 — 파이프라인이 ctx.settings에 실어 보낸다.

    HTTP의 .../run은 워커에 큐잉만 하고 202를 돌려주므로 실행 완료를 기다릴 수 없다.
    tests/test_pipeline_run_stage.py와 같이 파이프라인을 직접 구동한다.
    """
    from app.core import pipeline
    from app.providers.base import StageResult
    from app.providers.script.fake import FakeScript

    seen: dict = {}

    async def _capture(self, ctx):
        seen.update(ctx.settings)
        return StageResult(output={"scenes": []})

    monkeypatch.setattr(FakeScript, "run", _capture)

    user = await _admin(client, db_session, "pipe-ctx@example.com")
    await _override(db_session, "render_font_size", 77)

    created = await client.post(
        "/api/projects", json={"title": "테스트", "topic": "주제", "auto_run": False}
    )
    project_id = created.json()["id"]

    conn = await raw_connection(db_session)
    project = pipeline.decode_stage(
        dict(await queries.find_project_by_id(conn, id=project_id))
    )
    stage = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project_id, name="script"))
    )

    assert await pipeline.queue_stage(db_session, stage["id"], actor_id=user.id)
    claimed = await pipeline.claim_stage(db_session, stage["id"], actor_id=user.id)
    assert claimed is not None
    await pipeline.run_claimed_stage(db_session, project, claimed, actor_id=user.id)

    assert seen["render_font_size"] == 77
    # 프로젝트 자체 설정도 그대로 남는다 (병합에서 프로젝트 쪽이 이긴다)
    assert seen["auto_run"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_runtime_settings.py -v`
Expected: FAIL — `test_new_project_uses_runtime_script_provider`에서 provider가 `fake`(=`.env` 값)로 나온다

- [ ] **Step 3: `_next_provider`를 런타임 설정 기반으로 바꾼다**

`app/core/pipeline.py` — import에 추가:

```python
from app.runtime_settings import get_runtime_settings
```

`_next_provider`(152-154행)를 교체:

```python
async def _next_provider(conn, name: str) -> str:
    """단계별 기본 provider는 런타임 설정에서 온다. 설정에 없으면 fake."""
    runtime = await get_runtime_settings(conn)
    return getattr(runtime, f"{name}_provider", "fake")
```

`approve_stage`의 호출부(189행 근처)를 `await`로 바꾼다:

```python
            await queries.insert_stage(
                conn, project_id=project["id"], name=nxt,
                provider=await _next_provider(conn, nxt),
                status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
                started_at=None, finished_at=None,
                created_at=now, updated_at=now, created_by=actor_id, updated_by=actor_id,
            )
```

- [ ] **Step 4: `ctx.settings`에 런타임 설정을 주입한다**

`app/core/pipeline.py`의 `run_claimed_stage`(114-122행) — `StageContext` 생성 부분을 교체:

```python
    # provider는 DB 커넥션이 없다. 런타임 설정을 여기서 읽어 ctx에 실어 보낸다.
    # 프로젝트 자체 설정(auto_run 등)이 뒤에 와서 이긴다 — 개별 프로젝트가
    # 전역 기본값을 덮어쓰는 방향이 자연스럽다.
    runtime = await get_runtime_settings(conn)
    ctx = StageContext(
        topic=project["topic"],
        settings={**runtime.model_dump(), **project.get("settings", {})},
        inputs=inputs,
        input_assets=input_assets,
        attempt=stage["attempt"],
        workdir=f"projects/{project['id']}/{stage['name']}",
        on_progress=on_progress,
    )
```

- [ ] **Step 5: 프로젝트 생성 시 script provider를 런타임 설정에서 읽는다**

`app/api/projects.py` — import에서 `get_settings`를 지우고(다른 곳에서 안 쓰면) 추가:

```python
from app.runtime_settings import get_runtime_settings
```

`create_project`(69-80행)의 `insert_stage` 호출을 교체:

```python
    runtime = await get_runtime_settings(conn)
    stage_id = await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT,
        provider=runtime.script_provider,
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user["id"], updated_by=user["id"],
    )
```

`get_settings` import가 파일 안에서 더 이상 쓰이지 않으면 지운다. Run: `npm run lint`가 아니라 `uv run ruff check app/api/projects.py`로 확인한다(ruff가 없다면 육안 확인).

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_runtime_settings.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: 파이프라인 회귀 확인**

Run: `uv run pytest tests/test_pipeline_run_stage.py tests/test_pipeline_transition.py tests/test_pipeline_validate.py tests/test_api_projects.py tests/test_core_worker.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/core/pipeline.py app/api/projects.py tests/test_pipeline_runtime_settings.py
git commit -m "feat: wire runtime settings into pipeline stage context"
```

---

### Task 6: provider가 `ctx.settings`를 읽게 전환

**Files:**
- Modify: `app/providers/render/slideshow.py:27-43`
- Modify: `app/providers/captions/whisper.py:55-61`
- Modify: `app/providers/render/stock.py:41-42,49-51,70-71`
- Modify: `app/providers/render/sources.py:19-37`
- Test: `tests/test_provider_settings_source.py` (신규 — sources)
- Test: `tests/test_provider_render_slideshow.py` (테스트 추가 — 기존 픽스처 재사용)
- Test: `tests/test_provider_captions_whisper.py` (테스트 추가 — 기존 픽스처 재사용)

**Interfaces:**
- Consumes: Task 2의 `stage_setting(settings, key)`
- Produces: `enabled_sources(stock_sources: list[str] | None = None) -> list` — 인자를 주면 그 순서를 쓰고, 없으면 `.env`의 `stock_sources`를 쓴다. API 키는 계속 `.env`에서 읽는다.

- [ ] **Step 1: Write the failing test**

`tests/test_provider_settings_source.py`:

```python
import pytest

from app.providers.base import StageContext
from app.providers.render.sources import enabled_sources
from app.utils.errors import AppError


def test_enabled_sources_uses_given_order(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "pexels_api_key", "k1", raising=False)
    monkeypatch.setattr(get_settings(), "pixabay_api_key", "k2", raising=False)

    names = [type(s).__name__ for s in enabled_sources(["pixabay", "pexels"])]
    assert names == ["PixabaySource", "PexelsSource"]


def test_enabled_sources_falls_back_to_env_when_none(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "pexels_api_key", "k1", raising=False)
    monkeypatch.setattr(get_settings(), "pixabay_api_key", "", raising=False)

    names = [type(s).__name__ for s in enabled_sources()]
    assert names == ["PexelsSource"]


def test_enabled_sources_still_requires_at_least_one_api_key(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "pexels_api_key", "", raising=False)
    monkeypatch.setattr(get_settings(), "pixabay_api_key", "", raising=False)

    with pytest.raises(AppError) as exc:
        enabled_sources(["pexels", "pixabay"])
    assert exc.value.code == "STOCK_API_KEY_MISSING"


def test_stock_max_bytes_and_timeout_come_from_ctx_settings():
    from app.runtime_settings import stage_setting

    ctx = StageContext(
        topic="주제",
        settings={"stock_max_bytes": 1_048_576, "stock_timeout_sec": 7},
        workdir="projects/1/render",
    )
    assert stage_setting(ctx.settings, "stock_max_bytes") == 1_048_576
    assert stage_setting(ctx.settings, "stock_timeout_sec") == 7
```

`tests/test_provider_render_slideshow.py` 맨 아래에 추가한다 (`_fake_runner`·`_calls`·`_ASSETS` 픽스처를 그대로 쓴다):

```python
@pytest.mark.asyncio
async def test_run_uses_render_options_from_ctx_settings(monkeypatch, tmp_path):
    """렌더 옵션이 .env가 아니라 ctx.settings에서 온다 — 파이프라인이 주입한 값이 쓰인다."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(
        topic="t", inputs=_INPUTS, input_assets=_ASSETS, workdir="projects/9/render",
        settings={
            "render_bg_color": "#123456",
            "render_font": "Nanum Gothic",
            "render_font_size": 55,
        },
    )
    await SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg").run(ctx)

    cmd = _calls[0]["cmd"]
    assert "color=c=#123456:s=1080x1920" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "Nanum Gothic" in vf
    assert "55" in vf


@pytest.mark.asyncio
async def test_run_falls_back_to_env_when_ctx_settings_empty(monkeypatch, tmp_path):
    """provider 단위 테스트가 ctx.settings를 비워둬도 동작한다 (stage_setting 폴백)."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg").run(_ctx())

    cmd = _calls[0]["cmd"]
    assert "color=c=#0f172a:s=1080x1920" in cmd
```

`tests/test_provider_captions_whisper.py` 맨 아래에 추가한다. 이 파일은 `transcribe`를 주입해 모델·네트워크 없이 검증하므로, 주입한 가짜가 받은 `model_size`를 확인한다:

```python
@pytest.mark.asyncio
async def test_model_size_comes_from_ctx_settings(monkeypatch, tmp_path):
    """Whisper 모델이 .env가 아니라 ctx.settings에서 온다."""
    from app.providers.base import StageContext
    from app.providers.captions.whisper import WhisperCaptions
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    seen: list[str] = []

    def _transcribe(path, model_size, on_progress):
        seen.append(model_size)
        return [], "ko", 1.0

    ctx = StageContext(
        topic="t",
        input_assets={
            "voice": [{"kind": "AUDIO", "path": "projects/9/voice/voice.mp3", "meta": {}}]
        },
        workdir="projects/9/captions",
        settings={"whisper_model": "medium"},
    )
    storage.write_bytes("projects/9/voice/voice.mp3", b"mp3")
    await WhisperCaptions(transcribe=_transcribe).run(ctx)

    assert seen == ["medium"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provider_settings_source.py tests/test_provider_render_slideshow.py tests/test_provider_captions_whisper.py -v`
Expected: FAIL — `enabled_sources()`가 인자를 받지 않고(`TypeError`), slideshow·whisper는 `ctx.settings`를 무시하고 `.env` 값을 쓴다

- [ ] **Step 3: `enabled_sources`가 순서를 인자로 받게 한다**

`app/providers/render/sources.py:19-37`을 교체:

```python
def enabled_sources(stock_sources: list[str] | None = None) -> list:
    """주어진 순서대로, API 키가 실제로 있는 소스만 만든다.

    순서는 런타임 설정에서 오고 API 키는 .env에서 온다 — 비밀값은 DB로 옮기지 않는다.
    인자가 없으면 .env의 STOCK_SOURCES를 쓴다(단위 테스트·직접 호출용).
    키가 하나만 있어도 그 소스로 동작한다. 하나도 없을 때만 실패한다.
    """
    settings = get_settings()
    names = stock_sources if stock_sources is not None else settings.stock_sources
    sources = []
    for name in names:
        entry = _FACTORIES.get(name)
        if entry is None:
            logger.warning("알 수 없는 스톡 소스라 건너뜁니다: %s", name)
            continue
        factory, key_field = entry
        if getattr(settings, key_field, ""):
            sources.append(factory())
    if not sources:
        raise AppError(400, "STOCK_API_KEY_MISSING",
                       "스톡 API 키가 없습니다. PEXELS_API_KEY 또는 PIXABAY_API_KEY를 설정해 주세요.")
    return sources
```

- [ ] **Step 4: slideshow가 `ctx.settings`를 읽게 한다**

`app/providers/render/slideshow.py` — import에서 `from app.config import get_settings`를 지우고 추가:

```python
from app.runtime_settings import stage_setting
```

`run` 메서드(27-43행)의 앞부분을 교체:

```python
    async def run(self, ctx: StageContext) -> StageResult:
        audio_abs = str(storage.resolve(input_audio_path(ctx)))
        srt_rel = input_srt_path(ctx)
        out_rel = f"{ctx.workdir}/{_FILENAME}"

        cmd = ffmpeg.build_slideshow_cmd(
            exe=self._exe_path(),
            bg_color=stage_setting(ctx.settings, "render_bg_color"),
            audio_abs=audio_abs,
            srt_rel=srt_rel,
            out_rel=out_rel,
            width=_WIDTH,
            height=_HEIGHT,
            font=stage_setting(ctx.settings, "render_font"),
            font_size=stage_setting(ctx.settings, "render_font_size"),
        )
```

- [ ] **Step 5: whisper가 `ctx.settings`를 읽게 한다**

`app/providers/captions/whisper.py:57` — `from app.config import get_settings` import를 지우고(파일 안 다른 사용처가 없을 때) `from app.runtime_settings import stage_setting`를 추가한 뒤:

```python
        model_size = stage_setting(ctx.settings, "whisper_model")
```

- [ ] **Step 6: stock이 `ctx.settings`를 읽게 한다**

`app/providers/render/stock.py`:

`validate`(41-42행) — 설정에서 순서를 꺼내 넘긴다:

```python
    def validate(self, settings: dict) -> None:
        # 키가 하나도 없으면 여기서 STOCK_API_KEY_MISSING → 실행 전 조기 실패
        enabled_sources(settings.get("stock_sources"))
```

`_prepare_scene`(51행) — `settings = get_settings()`를 지우고 `self._download` 호출을 교체:

```python
                await self._download(
                    clip.url,
                    rel,
                    stage_setting(ctx.settings, "stock_max_bytes"),
                    stage_setting(ctx.settings, "stock_timeout_sec"),
                )
```

`run`(71행) — `settings = get_settings()` 줄을 지우고 `sources` 결정부를 교체:

```python
        sources = self._sources or enabled_sources(
            stage_setting(ctx.settings, "stock_sources")
        )
```

import에서 `get_settings`가 더 이상 쓰이지 않으면 지우고 `from app.runtime_settings import stage_setting`를 추가한다.

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_provider_settings_source.py tests/test_provider_render_slideshow.py tests/test_provider_captions_whisper.py -v`
Expected: PASS — `test_provider_settings_source.py` 4건 + 각 provider 파일의 기존 테스트 + 새로 추가한 3건

- [ ] **Step 8: provider 회귀 · 순환 import 확인**

먼저 provider 모듈을 단독으로 import해 순환이 없는지 본다. `app/runtime_settings.py`가 `REGISTRY`를 최상단에서 가져오면 여기서 `ImportError: cannot import name 'SlideshowRender' from partially initialized module`이 난다.

Run: `uv run python -c "import app.providers.render.slideshow; import app.providers.captions.whisper; import app.providers.render.stock; print('ok')"`
Expected: `ok`

Run: `uv run pytest tests/test_provider_render_slideshow.py tests/test_provider_captions_whisper.py tests/test_provider_render_stock.py tests/test_render_sources.py tests/test_render_smoke.py tests/test_stock_smoke.py -v`
Expected: PASS — `stage_setting`이 빈 `ctx.settings`에 대해 `.env` 기본값으로 폴백하므로 기존 테스트는 그대로 통과한다. 실패하는 테스트가 있으면 그 테스트가 `get_settings`를 monkeypatch하고 있는 경우다. 해당 테스트를 `ctx.settings`에 값을 넣는 방식으로 바꾼다.

- [ ] **Step 9: Commit**

```bash
git add app/providers tests/test_provider_settings_source.py
git commit -m "refactor: read stage options from ctx.settings instead of env"
```

---

### Task 7: 로그인 잠금 · 비밀번호 변경 최소 길이 런타임화

**Files:**
- Modify: `app/auth/router.py:120`, `app/auth/router.py:221,241-242`
- Test: `tests/test_auth_runtime_policy.py`

**Interfaces:**
- Consumes: Task 3의 `get_runtime_settings`
- Produces: `_PASSWORD_MIN_LEN` 상수 제거. 잠금 임계치와 비밀번호 최소 길이가 런타임 설정에서 온다.

- [ ] **Step 1: Write the failing test**

`tests/test_auth_runtime_policy.py`:

```python
import json

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local

PASSWORD = "pw12345678"


async def _override(db_session, key: str, value) -> None:
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key=key, value=json.dumps(value), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()


async def _user(db_session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        name="사용자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_lockout_threshold_follows_runtime_setting(client, db_session):
    """잠금 횟수를 2로 낮추면 두 번째 실패에서 잠긴다."""
    user = await _user(db_session, "lock-runtime@example.com")
    await _override(db_session, "failed_login_limit", 2)

    for _ in range(2):
        resp = await client.post(
            "/api/auth/login", json={"email": user.email, "password": "wrong-password"}
        )
        assert resp.status_code == 401

    # 이제 올바른 비밀번호를 넣어도 잠김이다
    resp = await client.post(
        "/api/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert resp.status_code == 423
    assert resp.json()["code"] == "ACCOUNT_LOCKED"


async def test_change_password_min_length_follows_runtime_setting(client, db_session):
    user = await _user(db_session, "minlen-runtime@example.com")
    await client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    await _override(db_session, "password_min_len", 12)

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short12345"},   # 10자
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "longenough123"},  # 13자
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_runtime_policy.py -v`
Expected: FAIL — 설정을 바꿔도 하드코딩된 5·8이 쓰인다

- [ ] **Step 3: 잠금 임계치를 런타임 설정에서 읽는다**

`app/auth/router.py` — import에 추가:

```python
from app.runtime_settings import get_runtime_settings
```

120행을 교체 (`login` 함수 안, 이미 `conn`이 있다):

```python
        elif new_count >= (await get_runtime_settings(conn)).failed_login_limit:
```

- [ ] **Step 4: 비밀번호 최소 길이를 런타임 설정에서 읽는다**

221행의 `_PASSWORD_MIN_LEN = 8` 상수를 **지운다**.

241-242행을 교체한다. `change_password`는 236행에서 이미 `conn`을 얻어 두었으므로 그대로 쓴다:

```python
    min_len = (await get_runtime_settings(conn)).password_min_len
    if len(body.new_password) < min_len:
        raise AppError(400, "WEAK_PASSWORD", f"새 비밀번호는 {min_len}자 이상이어야 합니다.")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_runtime_policy.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: 계정 회귀 확인**

Run: `uv run pytest tests/test_account_lockout.py tests/test_auth_change_password.py tests/test_auth_login.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/auth/router.py tests/test_auth_runtime_policy.py
git commit -m "feat: read lockout limit and password min length from runtime settings"
```

---

### Task 8: 회원가입 비밀번호 검증 · `GET /auth/policy`

**Files:**
- Modify: `app/auth/router.py:39-75`
- Modify: `tests/test_auth_register.py` (기존 7자 비밀번호 수정)
- Test: `tests/test_auth_policy.py`

**Interfaces:**
- Consumes: Task 3의 `get_runtime_settings`
- Produces: `GET /api/auth/policy` → `{"password_min_len": 8}` (비인증)

**주의:** `tests/test_auth_register.py`는 `"pw12345"`(**7자**)로 가입한다. 검증을 추가하면 이 파일의 테스트가 전부 깨진다. 같은 커밋에서 8자 이상으로 고친다. 다른 테스트 파일들도 `pw12345`를 쓰지만 대부분 `hash_password()`로 직접 사용자를 만들어 register를 거치지 않으므로 영향이 없다 — `/api/auth/register`를 POST하는 파일은 `tests/test_auth_register.py` 하나뿐이다.

- [ ] **Step 1: Write the failing test**

`tests/test_auth_policy.py`:

```python
import json

from app.db import raw_connection
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local


async def test_policy_is_readable_without_login(client):
    """회원가입 화면은 로그인 전에 이 값을 필요로 한다."""
    resp = await client.get("/api/auth/policy")
    assert resp.status_code == 200
    assert resp.json() == {"password_min_len": 8}


async def test_policy_follows_runtime_setting(client, db_session):
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key="password_min_len", value=json.dumps(16), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()

    resp = await client.get("/api/auth/policy")
    assert resp.json() == {"password_min_len": 16}


async def test_register_rejects_password_shorter_than_minimum(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "short-pw@example.com", "password": "pw12345", "name": "홍길동"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"


async def test_register_accepts_password_at_the_minimum(client):
    """경계값: 8자는 허용이다."""
    resp = await client.post(
        "/api/auth/register",
        json={"email": "exact-pw@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 201


async def test_register_minimum_follows_runtime_setting(client, db_session):
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key="password_min_len", value=json.dumps(12), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()

    resp = await client.post(
        "/api/auth/register",
        json={"email": "raised-min@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_policy.py -v`
Expected: FAIL — `/api/auth/policy`가 404, register가 7자를 201로 받는다

- [ ] **Step 3: register에 검증을 추가한다**

`app/auth/router.py`의 `register`(45-75행) — 이름 검증 뒤, 이메일 중복 확인 앞에 넣는다:

```python
@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    # 이름은 표시용이라 lower()하지 않는다(email과 다르다). 공백만 입력은 거부.
    name = body.name.strip()
    if not name or len(name) > _NAME_MAX_LEN:
        raise AppError(400, "INVALID_NAME", "이름은 1~50자로 입력해 주세요.")
    conn = await raw_connection(db)

    # 비밀번호 변경과 같은 규칙·같은 에러 코드를 쓴다. 가입 경로에만 검증이 없어서
    # 1자 비밀번호로도 계정이 만들어지던 구멍을 막는다.
    min_len = (await get_runtime_settings(conn)).password_min_len
    if len(body.password) < min_len:
        raise AppError(400, "WEAK_PASSWORD", f"비밀번호는 {min_len}자 이상이어야 합니다.")

    existing = await queries.find_by_email(conn, email=email)
    if existing is not None:
        raise Errors.conflict("이미 등록된 이메일입니다.")
```

이하 `now = now_local()`부터는 그대로 둔다.

- [ ] **Step 4: `GET /auth/policy` 추가**

`app/auth/router.py`의 `register` 바로 위에 넣는다:

```python
@router.get("/policy")
async def policy(db: AsyncSession = Depends(get_db)):
    """회원가입·비밀번호 변경 화면이 쓰는 공개 정책값.

    회원가입은 로그인 전 화면이라 /auth/me로는 전달할 수 없고, 일반 사용자에게
    관리자 설정 API를 열 수도 없다. 최소 길이는 가입을 시도하면 어차피 드러나는
    값이라 공개해도 잃을 것이 없다.
    """
    conn = await raw_connection(db)
    return {"password_min_len": (await get_runtime_settings(conn)).password_min_len}
```

- [ ] **Step 5: 기존 register 테스트의 비밀번호를 8자 이상으로 고친다**

`tests/test_auth_register.py`에서 `"password": "pw12345"`를 전부 `"password": "pw123456"`으로, `"password": "other-pw"`를 `"password": "other-pw1"`로 바꾼다(둘 다 8자). 총 8곳이다.

Run: `uv run pytest tests/test_auth_register.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_policy.py -v`
Expected: PASS (5 passed)

- [ ] **Step 7: 전체 회귀 확인**

Run: `uv run pytest -q`
Expected: PASS — `/api/auth/register`를 POST하는 테스트는 `test_auth_register.py`뿐이므로 다른 파일은 영향받지 않는다.

- [ ] **Step 8: Commit**

```bash
git add app/auth/router.py tests/test_auth_policy.py tests/test_auth_register.py
git commit -m "feat: enforce password minimum on register and expose auth policy"
```

---

### Task 9: 가입 자동 승인

**Files:**
- Modify: `app/auth/router.py:57-75`
- Test: `tests/test_auth_auto_approve.py`

**Interfaces:**
- Consumes: Task 3의 `get_runtime_settings`
- Produces: `signup_auto_approve`가 참이면 가입 결과가 `UserStatus.ACTIVE`

- [ ] **Step 1: Write the failing test**

`tests/test_auth_auto_approve.py`:

```python
import json

from app.constants import UserStatus
from app.db import raw_connection
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local


async def _enable_auto_approve(db_session) -> None:
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key="signup_auto_approve", value=json.dumps(True),
        now=now_local(), actor_id=None,
    )
    invalidate_runtime_settings()


async def test_register_is_pending_by_default(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "default-pending@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == UserStatus.PENDING


async def test_register_is_active_when_auto_approve_is_on(client, db_session):
    await _enable_auto_approve(db_session)

    resp = await client.post(
        "/api/auth/register",
        json={"email": "auto-active@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == UserStatus.ACTIVE


async def test_auto_approved_user_can_log_in_immediately(client, db_session):
    await _enable_auto_approve(db_session)
    await client.post(
        "/api/auth/register",
        json={"email": "auto-login@example.com", "password": "pw123456", "name": "홍길동"},
    )

    resp = await client.post(
        "/api/auth/login",
        json={"email": "auto-login@example.com", "password": "pw123456"},
    )
    assert resp.status_code == 200


async def test_existing_pending_user_is_not_auto_approved(client, db_session):
    """설정은 이후 가입에만 적용된다. 대기 중인 사용자는 관리자가 처리한다."""
    await client.post(
        "/api/auth/register",
        json={"email": "already-pending@example.com", "password": "pw123456", "name": "홍길동"},
    )
    await _enable_auto_approve(db_session)

    from sqlalchemy import text

    row = await db_session.execute(
        text("SELECT status FROM users WHERE email = 'already-pending@example.com'")
    )
    assert row.scalar() == UserStatus.PENDING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_auto_approve.py -v`
Expected: FAIL — 자동 승인을 켜도 `PENDING`이 나온다

- [ ] **Step 3: 가입 상태를 설정에 따라 결정한다**

`app/auth/router.py`의 `register` — Task 8에서 이미 읽은 런타임 설정을 재사용하도록 `min_len` 줄을 바꾸고, 상태 분기를 추가한다:

```python
    runtime = await get_runtime_settings(conn)
    min_len = runtime.password_min_len
    if len(body.password) < min_len:
        raise AppError(400, "WEAK_PASSWORD", f"비밀번호는 {min_len}자 이상이어야 합니다.")

    existing = await queries.find_by_email(conn, email=email)
    if existing is not None:
        raise Errors.conflict("이미 등록된 이메일입니다.")

    # 자동 승인이 켜져 있으면 승인 대기를 건너뛴다. 이미 PENDING인 사용자에게는
    # 소급되지 않는다 — 설정은 이후 가입에만 적용된다.
    status = UserStatus.ACTIVE if runtime.signup_auto_approve else UserStatus.PENDING

    now = now_local()
    try:
        user_id = await queries.insert_user(
            conn,
            email=email,
            name=name,
            password_hash=hash_password(body.password),
            role=UserRole.MEMBER,
            status=status,
            created_at=now,
            updated_at=now,
        )
    except asyncpg.exceptions.UniqueViolationError:
        # find_by_email 확인 이후, insert 사이의 경합으로 동시에 같은 이메일이
        # 등록된 경우(동시 요청/빠른 중복 제출). DB 유니크 제약이 잡아준 것을
        # 500이 아닌 409 CONFLICT로 변환한다.
        raise Errors.conflict("이미 등록된 이메일입니다.")
    await db.commit()
    return {"id": user_id, "status": status}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_auto_approve.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 전체 회귀 확인**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/auth/router.py tests/test_auth_auto_approve.py
git commit -m "feat: add signup auto approve setting"
```

---

### Task 10: `SettingRow` 공통 컴포넌트 추출

**Files:**
- Create: `web/src/components/SettingRow.tsx`
- Modify: `web/src/pages/Settings.tsx:12-31,161-176`

**Interfaces:**
- Produces: `SettingRow({ label, description, children })` — 개인 설정과 시스템 설정이 공유하는 설정 한 줄

- [ ] **Step 1: 컴포넌트 파일 생성**

`web/src/components/SettingRow.tsx`:

```tsx
import type { ReactNode } from 'react'

// 설정 항목 한 줄: 왼쪽에 라벨·설명, 오른쪽에 조작 요소.
// 개인 설정(Settings)과 시스템 설정(AdminSystem)이 같은 모양을 공유한다.
// label이 ReactNode인 것은 시스템 설정이 라벨 옆에 "변경됨" 배지를 붙이기 때문이다.
export function SettingRow({
  label,
  description,
  children,
}: {
  label: ReactNode
  description: string
  children: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-4">
      <div>
        <div className="text-sm font-medium text-fg">{label}</div>
        <div className="mt-0.5 text-xs text-fg-muted">{description}</div>
      </div>
      {children}
    </div>
  )
}
```

- [ ] **Step 2: `Settings.tsx`에서 사적 정의를 제거하고 import로 바꾼다**

`web/src/pages/Settings.tsx`:

- 12-31행의 `SettingRow` 함수 정의와 그 위 주석을 삭제한다
- 1행의 import에서 `type ReactNode`를 뺀다 → `import { useState } from 'react'`
- import 목록에 추가한다 (알파벳 순서상 `Modal` 앞):

```tsx
import { SettingRow } from '../components/SettingRow'
```

나머지(`ThemeControl`, `ChangePasswordModal`, `Settings`)는 그대로 둔다. `SettingRow` 사용부(161-176행)는 수정할 필요가 없다.

- [ ] **Step 3: 타입 검사와 린트**

Run: `cd web && npm run build`
Expected: 성공 (`tsc -b`가 통과하고 vite 빌드가 끝난다)

Run: `cd web && npm run lint`
Expected: 경고·에러 없음

- [ ] **Step 4: Commit**

```bash
git add web/src/components/SettingRow.tsx web/src/pages/Settings.tsx
git commit -m "refactor: extract SettingRow into a shared component"
```

---

### Task 11: 시스템 설정 화면

**Files:**
- Create: `web/src/lib/systemSettings.ts`
- Modify: `web/src/pages/admin/AdminSystem.tsx`

**Interfaces:**
- Consumes: Task 4의 `GET`/`PUT /admin/system/settings`, Task 10의 `SettingRow`
- Produces: `systemSettings.read()` / `systemSettings.save(settings)`, `RuntimeSettings` 타입

- [ ] **Step 1: API 모듈 생성**

`web/src/lib/systemSettings.ts`:

```ts
import { api } from './api'

export type RuntimeSettings = {
  script_provider: string
  voice_provider: string
  captions_provider: string
  render_provider: string
  whisper_model: string
  render_bg_color: string
  render_font: string
  render_font_size: number
  stock_sources: string[]
  stock_max_bytes: number
  stock_timeout_sec: number
  failed_login_limit: number
  password_min_len: number
  signup_auto_approve: boolean
}

// 화면이 "변경됨" 배지와 [기본값으로] 링크를 그리려면 셋 다 필요하다.
export type SettingsSnapshot = {
  settings: RuntimeSettings
  defaults: RuntimeSettings
  overridden: string[]
}

export const systemSettings = {
  read: () => api.get<SettingsSnapshot>('/admin/system/settings'),
  save: (settings: RuntimeSettings) =>
    api.put<SettingsSnapshot>('/admin/system/settings', settings),
}
```

- [ ] **Step 2: `api`에 `put` 추가**

`web/src/lib/api.ts`의 `api` 객체에 `patch` 아래로 추가한다:

```ts
  put: <T,>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
```

- [ ] **Step 3: 화면 작성**

`web/src/pages/admin/AdminSystem.tsx` 전체를 교체:

```tsx
import { useEffect, useState } from 'react'
import { FormError } from '../../components/FormError'
import { SettingRow } from '../../components/SettingRow'
import { ApiError } from '../../lib/api'
import {
  systemSettings,
  type RuntimeSettings,
  type SettingsSnapshot,
} from '../../lib/systemSettings'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'
const MB = 1024 * 1024

const SCRIPT_PROVIDERS = ['fake', 'openai', 'claude']
const VOICE_PROVIDERS = ['fake', 'edge_tts']
const CAPTIONS_PROVIDERS = ['fake', 'whisper']
const RENDER_PROVIDERS = ['fake', 'slideshow', 'stock']
const WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v3']
const STOCK_ORDERS: { value: string[]; label: string }[] = [
  { value: ['pexels', 'pixabay'], label: 'Pexels 먼저' },
  { value: ['pixabay', 'pexels'], label: 'Pixabay 먼저' },
  { value: ['pexels'], label: 'Pexels만' },
  { value: ['pixabay'], label: 'Pixabay만' },
]

const selectClass =
  'shrink-0 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm text-fg'
const inputClass =
  'w-32 shrink-0 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm text-fg'

function Select({
  value,
  options,
  onChange,
}: {
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <select className={selectClass} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  )
}

function NumberInput({
  value,
  onChange,
}: {
  value: number
  onChange: (v: number) => void
}) {
  return (
    <input
      type="number"
      className={inputClass}
      value={value}
      // 빈 문자열은 NaN이 되어 서버 422를 부르므로 0으로 눌러둔다 — 범위 검증이 잡는다.
      onChange={(e) => onChange(Number(e.target.value) || 0)}
    />
  )
}

// 기본값과 다른 항목에만 붙는다. 눌러서 곧바로 되돌릴 수 있다.
function Overridden({ onReset }: { onReset: () => void }) {
  return (
    <span className="ml-2 inline-flex items-center gap-1 align-middle">
      <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
        변경됨
      </span>
      <button
        type="button"
        onClick={onReset}
        className="text-[11px] text-fg-muted underline hover:text-fg"
      >
        기본값으로
      </button>
    </span>
  )
}

export function AdminSystem() {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null)
  const [draft, setDraft] = useState<RuntimeSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    systemSettings
      .read()
      .then((s) => {
        if (!alive) return
        setSnapshot(s)
        setDraft(s.settings)
      })
      .catch((e) => {
        if (!alive) return
        setError(e instanceof ApiError ? e.message : UNKNOWN)
      })
    return () => {
      alive = false
    }
  }, [])

  if (error && !draft) return <FormError message={error} />
  if (!snapshot || !draft) return <p className="text-sm text-fg-muted">불러오는 중…</p>

  const set = <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => {
    setSaved(false)
    setDraft({ ...draft, [key]: value })
  }
  const reset = (key: keyof RuntimeSettings) => set(key, snapshot.defaults[key])
  const changed = (key: keyof RuntimeSettings) =>
    JSON.stringify(draft[key]) !== JSON.stringify(snapshot.defaults[key])
  const dirty = JSON.stringify(draft) !== JSON.stringify(snapshot.settings)

  const badge = (key: keyof RuntimeSettings) =>
    changed(key) ? <Overridden onReset={() => reset(key)} /> : null

  const save = async () => {
    setError(null)
    setSaving(true)
    try {
      const next = await systemSettings.save(draft)
      setSnapshot(next)
      setDraft(next.settings)
      setSaved(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-4 pb-20">
      {saved && (
        <p className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700 dark:bg-green-500/10 dark:text-green-300">
          시스템 설정을 저장했습니다.
        </p>
      )}
      {error && <FormError message={error} />}

      <section className="divide-y divide-line-subtle rounded-lg border border-line bg-surface px-6">
        <h2 className="pt-5 pb-1 text-sm font-semibold text-fg">파이프라인 기본값</h2>

        <SettingRow
          label={<>스크립트 provider{badge('script_provider')}</>}
          description="대본 생성 도구입니다. 새로 만드는 프로젝트부터 적용됩니다."
        >
          <Select
            value={draft.script_provider}
            options={SCRIPT_PROVIDERS}
            onChange={(v) => set('script_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>음성 provider{badge('voice_provider')}</>}
          description="음성 합성 도구입니다. 새로 만들어지는 단계부터 적용됩니다."
        >
          <Select
            value={draft.voice_provider}
            options={VOICE_PROVIDERS}
            onChange={(v) => set('voice_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>자막 provider{badge('captions_provider')}</>}
          description="자막 생성 도구입니다. 새로 만들어지는 단계부터 적용됩니다."
        >
          <Select
            value={draft.captions_provider}
            options={CAPTIONS_PROVIDERS}
            onChange={(v) => set('captions_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>렌더 provider{badge('render_provider')}</>}
          description="영상 합성 도구입니다. 새로 만들어지는 단계부터 적용됩니다."
        >
          <Select
            value={draft.render_provider}
            options={RENDER_PROVIDERS}
            onChange={(v) => set('render_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>Whisper 모델{badge('whisper_model')}</>}
          description="클수록 자막이 정확하지만 느립니다. 다음 실행부터 적용됩니다."
        >
          <Select
            value={draft.whisper_model}
            options={WHISPER_MODELS}
            onChange={(v) => set('whisper_model', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>렌더 배경색{badge('render_bg_color')}</>}
          description="영상 배경으로 쓰는 단색입니다. 다음 실행부터 적용됩니다."
        >
          <span className="flex shrink-0 items-center gap-2">
            <input
              type="color"
              className="h-8 w-10 rounded border border-line-strong"
              value={draft.render_bg_color}
              onChange={(e) => set('render_bg_color', e.target.value)}
            />
            <input
              className="w-28 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm text-fg"
              value={draft.render_bg_color}
              onChange={(e) => set('render_bg_color', e.target.value)}
            />
          </span>
        </SettingRow>

        <SettingRow
          label={<>렌더 폰트{badge('render_font')}</>}
          description="자막에 쓰는 글꼴 이름입니다. 서버에 설치된 글꼴이어야 합니다."
        >
          <input
            className={inputClass}
            value={draft.render_font}
            onChange={(e) => set('render_font', e.target.value)}
          />
        </SettingRow>

        <SettingRow
          label={<>렌더 폰트 크기{badge('render_font_size')}</>}
          description="자막 글자 크기입니다 (8~200). 다음 실행부터 적용됩니다."
        >
          <NumberInput
            value={draft.render_font_size}
            onChange={(v) => set('render_font_size', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>스톡 소스 우선순위{badge('stock_sources')}</>}
          description="배경 소재를 찾을 순서입니다. 앞의 소스에서 못 찾으면 다음으로 넘어갑니다."
        >
          <select
            className={selectClass}
            value={draft.stock_sources.join(',')}
            onChange={(e) => set('stock_sources', e.target.value.split(','))}
          >
            {STOCK_ORDERS.map((o) => (
              <option key={o.value.join(',')} value={o.value.join(',')}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>

        <SettingRow
          label={<>씬당 다운로드 상한{badge('stock_max_bytes')}</>}
          description="배경 소재 하나의 최대 크기(MB)입니다 (1~500)."
        >
          <NumberInput
            value={Math.round(draft.stock_max_bytes / MB)}
            onChange={(v) => set('stock_max_bytes', v * MB)}
          />
        </SettingRow>

        <SettingRow
          label={<>스톡 타임아웃{badge('stock_timeout_sec')}</>}
          description="소재를 내려받을 때 기다리는 최대 시간(초)입니다 (5~300)."
        >
          <NumberInput
            value={draft.stock_timeout_sec}
            onChange={(v) => set('stock_timeout_sec', v)}
          />
        </SettingRow>
      </section>

      <section className="divide-y divide-line-subtle rounded-lg border border-line bg-surface px-6">
        <h2 className="pt-5 pb-1 text-sm font-semibold text-fg">계정 · 보안</h2>

        <SettingRow
          label={<>로그인 실패 잠금 횟수{badge('failed_login_limit')}</>}
          description="이 횟수만큼 연속 실패하면 계정이 잠깁니다 (1~100)."
        >
          <NumberInput
            value={draft.failed_login_limit}
            onChange={(v) => set('failed_login_limit', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>비밀번호 최소 길이{badge('password_min_len')}</>}
          description="회원가입과 비밀번호 변경에 함께 적용됩니다 (8~128). 기존 비밀번호는 그대로 쓸 수 있습니다."
        >
          <NumberInput
            value={draft.password_min_len}
            onChange={(v) => set('password_min_len', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>가입 자동 승인{badge('signup_auto_approve')}</>}
          description="켜면 가입 즉시 로그인할 수 있습니다. 이미 대기 중인 사용자에게는 적용되지 않습니다."
        >
          <input
            type="checkbox"
            className="h-5 w-5 shrink-0 accent-primary"
            checked={draft.signup_auto_approve}
            onChange={(e) => set('signup_auto_approve', e.target.checked)}
          />
        </SettingRow>
      </section>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={() => {
            setDraft(snapshot.settings)
            setSaved(false)
          }}
          disabled={!dirty || saving}
          className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
        >
          되돌리기
        </button>
        <button
          type="button"
          onClick={save}
          disabled={!dirty || saving}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          {saving ? '저장 중…' : '저장'}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 타입 검사와 린트**

Run: `cd web && npm run build`
Expected: 성공 (Task 10에서 `SettingRow.label`을 이미 `ReactNode`로 선언했으므로 배지를 넘겨도 통과한다)

Run: `cd web && npm run lint`
Expected: 경고·에러 없음

- [ ] **Step 5: 화면 확인**

Run: `cd web && npm run dev`

브라우저에서 관리자로 로그인해 `/admin/system`을 연다. 확인할 것:

1. 두 섹션이 보이고 값이 채워져 있다
2. 폰트 크기를 바꾸면 라벨 옆에 "변경됨"이 뜨고 [저장]이 활성화된다
3. [저장] 후 초록 배너가 뜨고, 새로고침해도 값이 유지된다
4. [기본값으로]를 누르고 저장하면 "변경됨"이 사라진다
5. 비밀번호 최소 길이를 4로 넣고 저장하면 에러 메시지가 뜬다(422)

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/systemSettings.ts web/src/lib/api.ts web/src/pages/admin/AdminSystem.tsx
git commit -m "feat: add admin system settings screen"
```

---

### Task 12: 프론트 비밀번호 최소 길이 배선

**Files:**
- Create: `web/src/lib/policy.ts`
- Modify: `web/src/pages/Register.tsx:17-34,36-46`
- Modify: `web/src/pages/Settings.tsx:10,76,114`

**Interfaces:**
- Consumes: Task 8의 `GET /auth/policy`
- Produces: `usePasswordMinLen(): number` — 정책을 불러오기 전에는 8을 반환한다

- [ ] **Step 1: 정책 훅 생성**

`web/src/lib/policy.ts`:

```ts
import { useEffect, useState } from 'react'
import { api } from './api'

// 서버가 최종 권한이다. 이 값은 화면이 즉각적인 피드백을 주기 위한 힌트일 뿐이다.
// 불러오기 전/실패 시에는 서버의 하한과 같은 8을 쓴다.
const FALLBACK_MIN_LEN = 8

export function usePasswordMinLen(): number {
  const [minLen, setMinLen] = useState(FALLBACK_MIN_LEN)

  useEffect(() => {
    let alive = true
    api
      .get<{ password_min_len: number }>('/auth/policy')
      .then((p) => {
        if (alive) setMinLen(p.password_min_len)
      })
      .catch(() => {
        // 정책 조회 실패로 가입·변경 화면을 막지 않는다. 서버가 어차피 다시 검증한다.
      })
    return () => {
      alive = false
    }
  }, [])

  return minLen
}
```

- [ ] **Step 2: `Register.tsx`가 서버 값을 쓰게 한다**

`web/src/pages/Register.tsx`:

import에 추가한다:

```tsx
import { usePasswordMinLen } from '../lib/policy'
```

`validate` 함수(17-34행)가 최소 길이를 인자로 받게 바꾼다:

```tsx
// 클라이언트 검증은 UX 보조일 뿐 신뢰 경계가 아니다. 진짜 검증은 서버가 한다.
function validate(
  name: string,
  email: string,
  password: string,
  confirm: string,
  minLen: number,
): FieldErrors {
  const errors: FieldErrors = {}
  const trimmed = name.trim()
  if (trimmed.length < 1 || trimmed.length > 50) {
    errors.name = '이름은 1~50자로 입력해 주세요.'
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = '올바른 이메일 형식이 아닙니다.'
  }
  if (password.length < minLen) {
    errors.password = `비밀번호는 ${minLen}자 이상이어야 합니다.`
  }
  if (password !== confirm) {
    errors.confirm = '비밀번호가 일치하지 않습니다.'
  }
  return errors
}
```

컴포넌트 안에서 훅을 부르고(37행 `const { register } = useAuth()` 아래) 호출부를 고친다:

```tsx
  const passwordMinLen = usePasswordMinLen()
```

```tsx
    const errors = validate(name, email, password, confirm, passwordMinLen)
```

- [ ] **Step 3: `Settings.tsx`가 서버 값을 쓰게 한다**

`web/src/pages/Settings.tsx`:

- 10행의 `const PASSWORD_MIN_LEN = 8`을 삭제한다
- import에 추가한다:

```tsx
import { usePasswordMinLen } from '../lib/policy'
```

`ChangePasswordModal` 안에서 훅을 부르고 상수 사용처를 바꾼다. `const [current, setCurrent] = useState('')` 위에:

```tsx
  const passwordMinLen = usePasswordMinLen()
```

76행과 79행의 `PASSWORD_MIN_LEN`을 `passwordMinLen`으로 바꾼다:

```tsx
  const tooShort = next.length > 0 && next.length < passwordMinLen
  const mismatch = confirm.length > 0 && next !== confirm
  const canSubmit =
    !submitting && current.length > 0 && next.length >= passwordMinLen && next === confirm
```

114행의 에러 메시지도 바꾼다:

```tsx
          error={tooShort ? `${passwordMinLen}자 이상 입력해 주세요.` : undefined}
```

- [ ] **Step 4: 타입 검사와 린트**

Run: `cd web && npm run build`
Expected: 성공

Run: `cd web && npm run lint`
Expected: 경고·에러 없음

- [ ] **Step 5: 하드코딩이 남지 않았는지 확인**

PowerShell에서 Run: `Select-String -Path web/src -Include *.tsx,*.ts -Recurse -Pattern "PASSWORD_MIN_LEN|length < 8"`
Expected: 결과 없음 — 최소 길이가 프론트에 더 이상 박혀 있지 않다

- [ ] **Step 6: 화면 확인**

Run: `cd web && npm run dev`

1. 관리자로 `/admin/system`에서 비밀번호 최소 길이를 12로 바꾸고 저장한다
2. 로그아웃 후 `/register`에서 9자 비밀번호로 가입을 시도하면 "비밀번호는 12자 이상이어야 합니다."가 뜬다
3. 다시 관리자로 로그인해 `/settings`의 비밀번호 변경에서도 12자 규칙이 적용된다
4. 설정을 8로 되돌린다

- [ ] **Step 7: 전체 테스트**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/policy.ts web/src/pages/Register.tsx web/src/pages/Settings.tsx
git commit -m "feat: read password minimum length from server policy"
```

---

## 완료 확인

모든 태스크를 끝낸 뒤:

- [ ] Run: `uv run pytest -q` — 전부 통과
- [ ] Run: `cd web && npm run build` — 성공
- [ ] Run: `cd web && npm run lint` — 경고 없음
- [ ] Run: `uv run pytest tests/test_alembic_migration.py -v` — 신선한 DB에 마이그레이션 체인이 적용된다
- [ ] `.env`의 `RENDER_FONT_SIZE`를 바꾸고 앱을 재시작하면, 관리자가 그 항목을 건드린 적이 없는 한 화면에 새 값이 보인다 (폴백이 살아 있다는 확인)
