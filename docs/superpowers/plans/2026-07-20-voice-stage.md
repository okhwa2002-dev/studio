# voice 단계 (대본 → 음성) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 대본을 edge_tts로 읽어 mp3를 만드는 `voice` 단계를 추가하고, 그 과정에서 **Asset 모델**·**다단계 전이**·**단계 간 입력 전달**을 도입한다.

**Architecture:** provider는 "무엇을 만들지"만 알고(파일을 쓰고 경로·메타를 `StageResult.assets`로 반환), core(pipeline)가 "어떻게 기록할지"(Asset 행 생성·교체)를 맡는다. `approve_stage`는 `STAGE_ORDER`에서 다음 단계를 찾아 `PENDING`으로 등록하고, 없으면 프로젝트를 `DONE`으로 만든다. 산출물은 정적 마운트가 아니라 owner 격리를 태운 인증 엔드포인트로 서빙한다.

**Tech Stack:** Python 3.12 · FastAPI · SQLModel + Alembic · aiosql/asyncpg · edge-tts(무료 TTS) · pytest(가짜 클라이언트 주입, network 없음) · React/TS · uv.

## Global Constraints

- **Asset 테이블 도입.** `Asset(stage_id, kind, path, meta)` + BaseEntity 감사 컬럼. 마이그레이션 1개.
- **재생성 = 교체.** 새로 만들기 전 해당 stage의 기존 Asset 행·파일을 지운다. 파일이 없어도 실패하지 않는다(멱등).
- **길이(duration)는 저장하지 않는다.** captions 단계의 whisper가 계산한다(YAGNI).
- **`STAGE_ORDER = ["script", "voice"]`** — captions/render는 이번 범위 아님.
- **실행 트리거는 명시적 [실행] 버튼.** 승인은 다음 단계를 *등록*만 하고 실행하지 않는다.
- **기본 목소리 고정:** provider 모듈 상수 `_VOICE = "ko-KR-SunHiNeural"`. 목소리 선택 UI 없음.
- **기본 provider = 설정 `VOICE_PROVIDER`(기본 `edge_tts`).** 테스트는 `fake` 강제.
- **저장 경로:** `STORAGE_PATH/projects/{project_id}/{stage_name}/` 아래. `STORAGE_PATH`는 기존 설정(`./storage`).
- **서빙:** `GET /api/projects/{project_id}/stages/{name}/asset` — 소유자만 200, 남의 프로젝트·산출물 없음 모두 **404**(기존 `Errors.not_found()` 관례).
- **에러:** 새 규칙 없음. 외부/파일 오류는 기존 `run_stage`의 `except`가 흡수 → stage `FAILED` + 일반 안내(원문은 로그).
- **테스트 오프라인·무과금:** EdgeTTS는 가짜 클라이언트 주입, 통합 테스트는 `VOICE_PROVIDER=fake`. 파일을 만드는 테스트는 `tmp_path`로 저장소를 더럽히지 않는다.
- **커밋:** 각 태스크에 커밋 스텝이 있으나, 이 저장소는 **사용자가 직접 커밋**한다 — 구현자는 커밋하지 말고 변경을 working tree에 남긴다(디스패치 시 컨트롤러가 지시).
- **테스트 실행:** `uv run pytest ...` (bare `pytest`/`python`은 이 환경에서 막힐 수 있음). 프론트는 `npm run build` / `npm run lint`.
- **참조 스펙:** `docs/superpowers/specs/2026-07-20-voice-stage-design.md`

## File Structure

| 파일 | 책임 |
|---|---|
| `app/constants.py` (수정) | `AssetKind` 추가, `StageName.VOICE` 추가 |
| `app/models/asset.py` (신규) | Asset 테이블 스키마 |
| `alembic/versions/*_create_assets.py` (신규) | assets 테이블 마이그레이션 |
| `app/queries/assets.sql` (신규) | Asset 조회·삽입·삭제 쿼리 |
| `app/utils/storage.py` (신규) | STORAGE_PATH 기준 경로 해석·쓰기·삭제 |
| `app/providers/base.py` (수정) | `StageContext.workdir`, `StageResult.assets`, `REGISTRY["voice"]` |
| `app/providers/voice/text.py` (신규) | 대본 → 읽을 텍스트 변환 (voice provider 공용) |
| `app/providers/voice/fake.py` (신규) | 오프라인 결정적 음성 provider |
| `app/providers/voice/edge_tts.py` (신규) | 실제 TTS provider |
| `app/core/pipeline.py` (수정) | inputs 주입, Asset 기록·교체, 다단계 전이 |
| `app/api/projects.py` (수정) | 산출물 서빙 엔드포인트 |
| `web/src/pages/projects/ProjectDetail.tsx` (수정) | 전체 단계 렌더 + voice 카드·오디오 재생 |
| `web/src/lib/projects.ts` (수정) | asset URL 헬퍼 |

---

### Task 1: 상수 + Asset 모델 + 마이그레이션

**Files:**
- Modify: `app/constants.py`
- Create: `app/models/asset.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/<rev>_create_assets.py`
- Test: `tests/test_asset_model.py`

**Interfaces:**
- Produces: `app.constants.AssetKind`(StrEnum, `AUDIO="AUDIO"`), `StageName.VOICE = "voice"`,
  `app.models.asset.Asset`(테이블 `assets`: `stage_id`, `kind`, `path`, `meta` + BaseEntity 감사 컬럼)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_asset_model.py`

```python
from app.constants import AssetKind, StageName
from app.models.asset import Asset


def test_stage_name_has_voice():
    assert StageName.VOICE == "voice"


def test_asset_kind_audio():
    assert AssetKind.AUDIO == "AUDIO"


def test_asset_table_columns():
    cols = set(Asset.__table__.columns.keys())
    assert {"id", "stage_id", "kind", "path", "meta"} <= cols
    # 감사 컬럼도 상속돼 있어야 한다
    assert {"created_at", "created_by", "updated_at", "updated_by"} <= cols
    assert Asset.__tablename__ == "assets"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_asset_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'AssetKind'` (또는 `app.models.asset` 없음)

- [ ] **Step 3: 상수 추가** — `app/constants.py`

`StageName`에 `VOICE`를 추가하고(기존 `SCRIPT` 아래), 파일 끝에 `AssetKind`를 추가한다.

```python
class StageName(StrEnum):
    """stages.name 코드값. provider 레지스트리 키와 맞춰 소문자."""

    SCRIPT = "script"
    VOICE = "voice"
```

```python
class AssetKind(StrEnum):
    """assets.kind 코드값. DB에 대문자로 저장된다."""

    AUDIO = "AUDIO"
```

- [ ] **Step 4: Asset 모델 작성** — `app/models/asset.py`

기존 `app/models/stage.py`와 같은 관례(BigInteger FK, 컬럼 코멘트, 감사 컬럼 헬퍼)를 따른다.

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Asset(BaseEntity, table=True):
    __tablename__ = "assets"
    __table_args__ = {"comment": "단계 산출물 파일 (음성·자막·영상)"}

    stage_id: int = Field(
        sa_type=BigInteger,
        foreign_key="stages.id",
        index=True,
        sa_column_kwargs={"comment": "소속 단계 (FK: stages.id)"},
    )
    kind: str = Field(sa_column_kwargs={"comment": "산출물 종류: AUDIO (이후 SRT|VIDEO|IMAGE)"})
    path: str = Field(sa_column_kwargs={"comment": "STORAGE_PATH 기준 상대 경로"})
    meta: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "comment": "voice·size_bytes 등 부가정보 (JSONB)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
```

- [ ] **Step 5: 모델 등록** — `app/models/__init__.py`를 아래로 교체

```python
from app.models.asset import Asset
from app.models.base import BaseEntity
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.stage import Stage
from app.models.user import User

__all__ = ["Asset", "BaseEntity", "Project", "RefreshToken", "Stage", "User"]
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_asset_model.py -q`
Expected: PASS (3 passed)

- [ ] **Step 7: 마이그레이션 생성**

Run: `uv run alembic revision --autogenerate -m "create assets"`
Expected: `alembic/versions/<rev>_create_assets.py` 생성. 파일을 열어 `down_revision`이 **`'ac6e7626417d'`**(현재 head)인지 확인하고, `upgrade()`가 `assets` 테이블 **하나만** 만드는지 확인한다(다른 테이블 변경이 섞여 있으면 지운다).

생성된 `upgrade()`는 아래와 같아야 한다(자동 생성 결과가 이와 다르면 이 내용으로 맞춘다):

```python
def upgrade() -> None:
    op.create_table('assets',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='기본키, BIGINT 자동 증가'),
    sa.Column('stage_id', sa.BigInteger(), nullable=False, comment='소속 단계 (FK: stages.id)'),
    sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False, comment='산출물 종류: AUDIO (이후 SRT|VIDEO|IMAGE)'),
    sa.Column('path', sqlmodel.sql.sqltypes.AutoString(), nullable=False, comment='STORAGE_PATH 기준 상대 경로'),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='voice·size_bytes 등 부가정보 (JSONB)'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text("timezone('Asia/Seoul', now())"), nullable=False, comment='생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)'),
    sa.Column('created_by', sa.BigInteger(), nullable=True, comment='생성자'),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text("timezone('Asia/Seoul', now())"), nullable=False, comment='수정일시 (로컬 벽시계 시각, 수정 시 갱신)'),
    sa.Column('updated_by', sa.BigInteger(), nullable=True, comment='수정자'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['stage_id'], ['stages.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    comment='단계 산출물 파일 (음성·자막·영상)'
    )
    op.create_index(op.f('ix_assets_stage_id'), 'assets', ['stage_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_assets_stage_id'), table_name='assets')
    op.drop_table('assets')
```

- [ ] **Step 8: 마이그레이션 왕복 확인**

Run: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: 세 번 모두 오류 없이 완료. (`assets` 생성 → 삭제 → 재생성)

- [ ] **Step 9: 전체 스위트 회귀 확인**

Run: `uv run pytest -q`
Expected: 기존 139 + 신규 3 = 142 passed

- [ ] **Step 10: 커밋**

```bash
git add app/constants.py app/models/asset.py app/models/__init__.py alembic/versions/ tests/test_asset_model.py
git commit -m "기능: Asset 모델·assets 테이블 추가 (voice 단계 준비)"
```

---

### Task 2: assets.sql + 저장 유틸

**Files:**
- Create: `app/queries/assets.sql`
- Create: `app/utils/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `get_settings().storage_path`
- Produces:
  - 쿼리: `queries.insert_asset(conn, ...)`, `queries.list_assets_by_stage(conn, stage_id=...)`, `queries.delete_assets_by_stage(conn, stage_id=...)`
  - `app.utils.storage.resolve(rel: str) -> Path`, `write_bytes(rel: str, data: bytes) -> int`, `delete(rel: str) -> None`

> `app/queries/__init__.py`는 디렉토리의 모든 `*.sql`을 자동 로드하므로 `assets.sql`만 만들면 `queries.<이름>`으로 바로 쓸 수 있다(등록 코드 불필요).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_storage.py`

```python
from pathlib import Path

from app.utils import storage


def test_resolve_is_under_storage_root(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    p = storage.resolve("projects/1/voice/voice.mp3")
    assert p == tmp_path / "projects/1/voice/voice.mp3"


def test_write_bytes_creates_parents_and_returns_size(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    size = storage.write_bytes("projects/7/voice/voice.mp3", b"hello")
    assert size == 5
    assert (tmp_path / "projects/7/voice/voice.mp3").read_bytes() == b"hello"


def test_delete_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("a/b.mp3", b"x")
    storage.delete("a/b.mp3")
    assert not (tmp_path / "a/b.mp3").exists()
    storage.delete("a/b.mp3")  # 두 번째 호출도 예외 없이 통과해야 한다


def test_resolve_rejects_escaping_path(monkeypatch, tmp_path):
    # 상위 경로 탈출(../)은 거부한다 — 경로가 외부 입력에서 올 수 있다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    import pytest

    with pytest.raises(ValueError):
        storage.resolve("../secrets.txt")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_storage.py -q`
Expected: FAIL — `ModuleNotFoundError: app.utils.storage`

- [ ] **Step 3: 저장 유틸 작성** — `app/utils/storage.py`

```python
from pathlib import Path

from app.config import get_settings


def _root() -> Path:
    """STORAGE_PATH 루트. 테스트는 이 함수를 monkeypatch해 tmp_path로 바꾼다."""
    return Path(get_settings().storage_path).resolve()


def resolve(rel: str) -> Path:
    """저장소 루트 기준 상대 경로를 절대 경로로. 루트 밖으로 나가는 경로는 거부한다."""
    root = _root()
    path = (root / rel).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"저장소 밖 경로입니다: {rel}")
    return path


def write_bytes(rel: str, data: bytes) -> int:
    """부모 디렉토리를 만들고 파일을 쓴 뒤 바이트 크기를 돌려준다."""
    path = resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def delete(rel: str) -> None:
    """파일을 지운다. 이미 없어도 조용히 통과한다(멱등)."""
    resolve(rel).unlink(missing_ok=True)
```

- [ ] **Step 4: 쿼리 작성** — `app/queries/assets.sql`

```sql
-- name: insert_asset<!
INSERT INTO assets (stage_id, kind, path, meta,
                    created_at, updated_at, created_by, updated_by)
VALUES (:stage_id, :kind, :path, :meta::jsonb,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: list_assets_by_stage
SELECT id, stage_id, kind, path, meta, created_at, updated_at
FROM assets
WHERE stage_id = :stage_id
ORDER BY id ASC;

-- name: find_asset_by_stage^
SELECT id, stage_id, kind, path, meta, created_at, updated_at
FROM assets
WHERE stage_id = :stage_id
ORDER BY id DESC
LIMIT 1;

-- name: delete_assets_by_stage!
DELETE FROM assets WHERE stage_id = :stage_id;
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_storage.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: 쿼리 로드 확인**

Run: `uv run python -c "from app.queries import queries; print(all(hasattr(queries, n) for n in ['insert_asset','list_assets_by_stage','find_asset_by_stage','delete_assets_by_stage']))"`
Expected: `True`

- [ ] **Step 7: 커밋**

```bash
git add app/queries/assets.sql app/utils/storage.py tests/test_storage.py
git commit -m "기능: assets 쿼리와 저장소 유틸(경로 해석·쓰기·삭제) 추가"
```

---

### Task 3: provider 계약 확장 + FakeVoice + 레지스트리

**Files:**
- Modify: `app/providers/base.py`
- Create: `app/providers/voice/__init__.py` (빈 파일)
- Create: `app/providers/voice/text.py`
- Create: `app/providers/voice/fake.py`
- Test: `tests/test_provider_voice_fake.py`

**Interfaces:**
- Consumes: `AssetKind`(constants), `storage.write_bytes`
- Produces:
  - `StageContext.workdir: str` (저장소 기준 이 단계의 디렉토리, 기본 `""`)
  - `StageResult.assets: list[dict]` (각 `{"kind","path","meta"}`, 기본 `[]`)
  - `app.providers.voice.text.narration_text(inputs: dict) -> str` (voice provider 공용, Task 6도 사용)
  - `FakeVoice` — `stage="voice"`, `name="fake"`, `run(ctx)`가 결정적 더미 mp3 바이트를 저장하고 asset 1건 반환
  - `REGISTRY["voice"] = {"fake": FakeVoice}` (edge_tts는 Task 6에서 추가)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_voice_fake.py`

```python
import pytest

from app.constants import AssetKind
from app.providers.base import REGISTRY, StageContext, get_provider
from app.providers.voice.fake import FakeVoice
from app.utils import storage

_SCRIPT = {
    "title": "바다 거북",
    "hook": "훅",
    "scenes": [
        {"index": 1, "narration": "첫 문장.", "on_screen": "a"},
        {"index": 2, "narration": "둘째 문장.", "on_screen": "b"},
    ],
    "estimated_duration_sec": 30,
}


@pytest.mark.asyncio
async def test_run_writes_file_and_returns_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="바다 거북", inputs={"script": _SCRIPT}, workdir="projects/1/voice")
    result = await FakeVoice().run(ctx)

    assert len(result.assets) == 1
    asset = result.assets[0]
    assert asset["kind"] == AssetKind.AUDIO
    assert asset["path"] == "projects/1/voice/voice.mp3"
    # 실제 파일이 저장됐고 크기가 output/meta와 일치한다
    written = (tmp_path / "projects/1/voice/voice.mp3").read_bytes()
    assert len(written) > 0
    assert asset["meta"]["size_bytes"] == len(written)
    assert result.output["size_bytes"] == len(written)


@pytest.mark.asyncio
async def test_run_reads_narration_from_script_input(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, workdir="projects/2/voice")
    result = await FakeVoice().run(ctx)
    # 두 narration이 이어붙어 읽힌 글자수가 기록된다
    assert result.output["chars"] == len("첫 문장. 둘째 문장.")


def test_registry_has_voice_fake():
    assert REGISTRY["voice"]["fake"] is FakeVoice
    assert isinstance(get_provider("voice", "fake"), FakeVoice)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_provider_voice_fake.py -q`
Expected: FAIL — `ModuleNotFoundError: app.providers.voice.fake`

- [ ] **Step 3: 계약 확장** — `app/providers/base.py`의 `StageContext`/`StageResult`를 아래로 교체

```python
@dataclass
class StageContext:
    """단계 실행에 필요한 입력. (SSE on_progress는 해당 단계 도입 시 확장)"""

    topic: str
    settings: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)  # 이전 단계 산출물 (script엔 비어있음)
    attempt: int = 0  # 재생성 횟수 → provider 출력 변주 seed
    workdir: str = ""  # 저장소 기준 이 단계의 디렉토리 (파일을 만드는 단계만 사용)


@dataclass
class StageResult:
    output: dict  # Stage.output 에 저장될 산출 요약
    assets: list[dict] = field(default_factory=list)  # {kind, path, meta} — core가 Asset으로 기록
```

- [ ] **Step 4: 공용 나레이션 헬퍼 + FakeVoice 작성**

`app/providers/voice/__init__.py` — 빈 파일로 생성.

`app/providers/voice/text.py` — voice provider들이 공유한다. **fake·실제 provider 모두 여기서 가져온다**
(실제 provider가 fake 모듈에 의존하지 않도록 별도 모듈로 둔다).

```python
def narration_text(inputs: dict) -> str:
    """script 단계 산출물에서 나레이션만 순서대로 이어붙인다. voice provider 공용."""
    script = inputs.get("script") or {}
    return " ".join(scene["narration"] for scene in script.get("scenes", []))
```

`app/providers/voice/fake.py`:

```python
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.voice.text import narration_text
from app.utils import storage

_FILENAME = "voice.mp3"


class FakeVoice(Provider):
    """외부 호출 없이 결정적 더미 오디오를 만드는 개발/테스트용 provider."""

    stage = "voice"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        text = narration_text(ctx.inputs)
        # 실제 mp3는 아니지만 "글자수만큼의 결정적 바이트"라 크기·교체를 검증하기 충분하다.
        data = (f"FAKE-AUDIO[{ctx.attempt}]:{text}").encode("utf-8")
        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, data)
        meta = {"voice": "fake", "size_bytes": size}
        return StageResult(
            output={"voice": "fake", "size_bytes": size, "chars": len(text)},
            assets=[{"kind": AssetKind.AUDIO, "path": rel, "meta": meta}],
        )
```

- [ ] **Step 5: 레지스트리 등록** — `app/providers/base.py` 하단 import·REGISTRY를 아래로 교체

```python
# 새 도구 추가 = 클래스 1개 + 여기 1줄. core는 손대지 않는다.
from app.providers.script.claude import ClaudeScript  # noqa: E402
from app.providers.script.fake import FakeScript  # noqa: E402
from app.providers.script.openai import OpenAIScript  # noqa: E402
from app.providers.voice.fake import FakeVoice  # noqa: E402

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript, "openai": OpenAIScript, "claude": ClaudeScript},
    "voice": {"fake": FakeVoice},
}
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_provider_voice_fake.py -q`
Expected: PASS (3 passed)

- [ ] **Step 7: 기존 provider 회귀 확인**

Run: `uv run pytest tests/test_provider_registry.py tests/test_provider_script_fake.py tests/test_provider_base.py -q`
Expected: PASS (기존 그대로 — `StageResult`에 기본값 있는 필드만 추가했으므로 script provider는 영향 없음)

- [ ] **Step 8: 커밋**

```bash
git add app/providers/base.py app/providers/voice/ tests/test_provider_voice_fake.py
git commit -m "기능: provider 계약에 workdir·assets 추가, FakeVoice provider 등록"
```

---

### Task 4: pipeline — 이전 단계 입력 주입 + Asset 기록·교체

**Files:**
- Modify: `app/core/pipeline.py`
- Test: `tests/test_pipeline_voice_run.py`

**Interfaces:**
- Consumes: `queries.insert_asset`/`delete_assets_by_stage`/`list_assets_by_stage`, `storage.delete`, `StageResult.assets`
- Produces: `run_stage`가 (1) `ctx.inputs`에 **직전 단계들의 output**을 `{단계이름: output}`으로 채우고, (2) `ctx.workdir`을 `projects/{project_id}/{stage_name}`으로 주고, (3) 성공 시 **기존 Asset 행·파일을 지우고** 새 asset을 기록한다.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_pipeline_voice_run.py`

```python
import json

import pytest

from app.auth.security import hash_password
from app.constants import (
    AssetKind,
    ProjectStatus,
    StageName,
    StageStatus,
    UserRole,
    UserStatus,
)
from app.core import pipeline
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils import storage
from app.utils.time import now_local

_SCRIPT = {
    "title": "바다 거북",
    "hook": "훅",
    "scenes": [{"index": 1, "narration": "첫 문장.", "on_screen": "a"}],
    "estimated_duration_sec": 30,
}


async def _seed(session, email: str):
    """script(승인됨) + voice(대기) 단계를 가진 프로젝트를 만든다."""
    conn = await raw_connection(session)
    now = now_local()
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    project_id = await queries.insert_project(
        conn, owner_id=user.id, title="t", topic="주제",
        status=ProjectStatus.DRAFT, current_stage=StageName.VOICE, settings=json.dumps({}),
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider="fake",
        status=StageStatus.APPROVED, output=json.dumps(_SCRIPT), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.VOICE, provider="fake",
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await session.commit()
    project = pipeline.decode_stage(dict(await queries.find_project_by_id(conn, id=project_id)))
    voice = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project_id, name=StageName.VOICE))
    )
    return user.id, project, voice


@pytest.mark.asyncio
async def test_run_voice_records_asset_and_uses_script_input(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-run@example.com")

    updated = await pipeline.run_stage(db_session, project, voice, actor_id=actor)
    assert updated["status"] == StageStatus.NEEDS_REVIEW
    # script의 나레이션이 실제로 전달됐다
    assert updated["output"]["chars"] == len("첫 문장.")

    conn = await raw_connection(db_session)
    assets = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=voice["id"])]
    assert len(assets) == 1
    assert assets[0]["kind"] == AssetKind.AUDIO
    assert assets[0]["path"] == f"projects/{project['id']}/voice/voice.mp3"
    assert (tmp_path / assets[0]["path"]).exists()


@pytest.mark.asyncio
async def test_rerun_replaces_previous_asset(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-replace@example.com")

    await pipeline.run_stage(db_session, project, voice, actor_id=actor)
    conn = await raw_connection(db_session)
    first = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=voice["id"])]

    # 재생성 → 다시 실행 (attempt가 올라가고 asset은 교체돼야 한다)
    reloaded = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE))
    )
    await pipeline.regenerate_stage(db_session, project, reloaded, actor_id=actor)

    after = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=voice["id"])]
    assert len(after) == 1  # 누적되지 않고 교체
    assert after[0]["id"] != first[0]["id"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_pipeline_voice_run.py -q`
Expected: FAIL — `run_stage`가 아직 `inputs`를 채우지 않아 `chars`가 0이거나, asset이 기록되지 않아 `len(assets) == 1` 실패

- [ ] **Step 3: `run_stage`에 inputs·workdir·asset 기록 추가** — `app/core/pipeline.py`

파일 상단 import에 아래를 추가한다(기존 import 블록에 정렬해 삽입).

```python
from app.constants import AssetKind  # 기존 constants import 줄에 함께 추가해도 된다
from app.utils import storage
```

`run_stage` 위에 헬퍼 두 개를 추가한다.

```python
async def _previous_outputs(conn, project_id: int, upto: str) -> dict:
    """이 단계 앞의 단계들 output을 {단계이름: output}으로 모은다."""
    inputs: dict = {}
    for name in STAGE_ORDER:
        if name == upto:
            break
        row = await queries.find_stage(conn, project_id=project_id, name=name)
        if row is not None:
            inputs[name] = decode_stage(dict(row))["output"]
    return inputs


async def _replace_assets(conn, stage_id: int, assets: list[dict], actor_id: int) -> None:
    """이 단계의 기존 산출물(행+파일)을 지우고 새 것으로 교체한다."""
    for row in [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage_id)]:
        storage.delete(row["path"])
    await queries.delete_assets_by_stage(conn, stage_id=stage_id)
    now = now_local()
    for asset in assets:
        await queries.insert_asset(
            conn, stage_id=stage_id, kind=asset["kind"], path=asset["path"],
            meta=json.dumps(asset.get("meta", {})),
            created_at=now, updated_at=now, created_by=actor_id, updated_by=actor_id,
        )
```

`run_stage`의 `ctx` 생성과 성공 분기를 아래로 바꾼다.

```python
    ctx = StageContext(
        topic=project["topic"],
        settings=project.get("settings", {}),
        inputs=await _previous_outputs(conn, project["id"], stage["name"]),
        attempt=stage["attempt"],
        workdir=f"projects/{project['id']}/{stage['name']}",
    )
    try:
        provider = get_provider(stage["name"], stage["provider"])   # 잘못된 provider 이름도 FAILED로 흡수
        provider.validate(ctx.settings)          # 키 누락 등 조기 실패 → FAILED로 흡수
        result = await provider.run(ctx)
        await _replace_assets(conn, stage["id"], result.assets, actor_id)
        status, output, error = StageStatus.NEEDS_REVIEW, result.output, None
```

> `except` 두 분기(`AppError` / `Exception`)는 그대로 둔다. asset 기록 중 오류가 나도 같은 경로로 `FAILED`가 된다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_pipeline_voice_run.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: 기존 파이프라인 회귀 확인**

Run: `uv run pytest tests/test_pipeline_run_stage.py tests/test_pipeline_validate.py -q`
Expected: PASS (script는 `assets`가 빈 리스트라 `_replace_assets`가 아무것도 하지 않는다)

- [ ] **Step 6: 커밋**

```bash
git add app/core/pipeline.py tests/test_pipeline_voice_run.py
git commit -m "기능: run_stage가 이전 단계 output을 주입하고 산출물 Asset을 교체 기록"
```

---

### Task 5: pipeline — 다단계 전이 (approve_stage 일반화)

**Files:**
- Modify: `app/core/pipeline.py` (`STAGE_ORDER`, `approve_stage`)
- Test: `tests/test_pipeline_transition.py`

**Interfaces:**
- Consumes: `queries.insert_stage`, `queries.update_project_status`, `get_settings().voice_provider`(Task 6에서 추가되므로 **여기서는 `"fake"` 대신 설정을 쓰지 않고** 다음 단계 provider를 `_next_provider(name)` 헬퍼로 결정)
- Produces: `approve_stage`가 다음 단계가 있으면 그 단계를 `PENDING`으로 등록 + `current_stage` 갱신, 없으면 프로젝트 `DONE`

> **provider 결정:** 다음 단계의 provider 이름은 설정에서 온다. `VOICE_PROVIDER` 설정은 Task 6에서 추가하므로, 이 태스크에서는 `_next_provider()`가 `getattr(get_settings(), f"{name}_provider", "fake")`로 **있으면 쓰고 없으면 `fake`** 를 쓰게 한다. Task 6에서 설정이 생기면 자동으로 그 값을 따른다(추가 수정 불필요).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_pipeline_transition.py`

```python
import json

import pytest

from app.auth.security import hash_password
from app.constants import (
    ProjectStatus,
    StageName,
    StageStatus,
    UserRole,
    UserStatus,
)
from app.core import pipeline
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local


async def _seed_script_needs_review(session, email: str):
    conn = await raw_connection(session)
    now = now_local()
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    project_id = await queries.insert_project(
        conn, owner_id=user.id, title="t", topic="주제",
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT, settings=json.dumps({}),
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider="fake",
        status=StageStatus.NEEDS_REVIEW, output=json.dumps({"scenes": []}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await session.commit()
    project = pipeline.decode_stage(dict(await queries.find_project_by_id(conn, id=project_id)))
    stage = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project_id, name=StageName.SCRIPT))
    )
    return user.id, project, stage


@pytest.mark.asyncio
async def test_approving_script_registers_voice_pending(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans1@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    conn = await raw_connection(db_session)
    voice = await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE)
    assert voice is not None, "script 승인 시 voice 단계가 등록돼야 한다"
    assert voice["status"] == StageStatus.PENDING

    updated_project = dict(await queries.find_project_by_id(conn, id=project["id"]))
    assert updated_project["current_stage"] == StageName.VOICE
    # 아직 마지막 단계가 아니므로 DONE이 아니다
    assert updated_project["status"] != ProjectStatus.DONE


@pytest.mark.asyncio
async def test_approving_last_stage_marks_project_done(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans2@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    conn = await raw_connection(db_session)
    voice = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE))
    )
    # voice를 검토 상태로 만든 뒤 승인 → 마지막 구현 단계이므로 프로젝트 DONE
    await queries.update_stage_status(
        conn, id=voice["id"], status=StageStatus.NEEDS_REVIEW,
        updated_at=now_local(), updated_by=actor,
    )
    await db_session.commit()
    voice["status"] = StageStatus.NEEDS_REVIEW
    await pipeline.approve_stage(db_session, project, voice, actor_id=actor)

    updated_project = dict(await queries.find_project_by_id(conn, id=project["id"]))
    assert updated_project["status"] == ProjectStatus.DONE


@pytest.mark.asyncio
async def test_reapproving_does_not_duplicate_next_stage(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans3@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    conn = await raw_connection(db_session)
    # script를 다시 검토 상태로 되돌린 뒤 또 승인해도 voice가 중복 생성되면 안 된다
    await queries.update_stage_status(
        conn, id=script["id"], status=StageStatus.NEEDS_REVIEW,
        updated_at=now_local(), updated_by=actor,
    )
    await db_session.commit()
    script["status"] = StageStatus.NEEDS_REVIEW
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    stages = [dict(r) async for r in queries.list_stages_by_project(conn, project_id=project["id"])]
    assert [s["name"] for s in stages].count(StageName.VOICE) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_pipeline_transition.py -q`
Expected: FAIL — 현재 `approve_stage`는 다음 단계를 만들지 않고 무조건 프로젝트를 `DONE`으로 만든다

- [ ] **Step 3: `STAGE_ORDER`와 `approve_stage` 교체** — `app/core/pipeline.py`

`STAGE_ORDER`를 아래로 바꾼다.

```python
STAGE_ORDER: list[str] = ["script", "voice"]  # captions/render 미구현
```

상단 import에 `get_settings`를 추가한다.

```python
from app.config import get_settings
```

`approve_stage`를 아래로 교체한다(기존 함수 전체 대체).

```python
def _next_stage(name: str) -> str | None:
    """STAGE_ORDER에서 다음 단계 이름. 마지막이면 None."""
    idx = STAGE_ORDER.index(name)
    return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None


def _next_provider(name: str) -> str:
    """단계별 기본 provider는 설정에서 온다. 설정이 없으면 fake."""
    return getattr(get_settings(), f"{name}_provider", "fake")


async def approve_stage(session, project: dict, stage: dict, actor_id: int) -> None:
    if not can_transition(stage["status"], StageStatus.APPROVED):
        raise AppError(409, "STAGE_CONFLICT", "승인할 수 없는 상태입니다.")

    conn = await raw_connection(session)
    now = now_local()
    await queries.update_stage_status(
        conn, id=stage["id"], status=StageStatus.APPROVED, updated_at=now, updated_by=actor_id
    )

    nxt = _next_stage(stage["name"])
    if nxt is None:
        # 마지막 구현 단계를 승인하면 프로젝트 완료.
        await queries.update_project_status(
            conn, id=project["id"], status=ProjectStatus.DONE, current_stage=stage["name"],
            updated_at=now, updated_by=actor_id,
        )
    else:
        # 다음 단계를 PENDING으로 등록만 한다 — 실행은 사용자가 [실행]으로 시작한다.
        # 이미 있으면 만들지 않는다(재승인 멱등).
        if await queries.find_stage(conn, project_id=project["id"], name=nxt) is None:
            await queries.insert_stage(
                conn, project_id=project["id"], name=nxt, provider=_next_provider(nxt),
                status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
                started_at=None, finished_at=None,
                created_at=now, updated_at=now, created_by=actor_id, updated_by=actor_id,
            )
        await queries.update_project_status(
            conn, id=project["id"], status=ProjectStatus.REVIEW, current_stage=nxt,
            updated_at=now, updated_by=actor_id,
        )
    await session.commit()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_pipeline_transition.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 기존 API 회귀 확인**

Run: `uv run pytest tests/test_api_projects.py -q`
Expected: PASS. (script 승인 응답의 `stages`가 2개가 되므로, 승인 후 단계 수를 단언하던 기존 테스트가 있으면 **새 동작에 맞게** 고친다 — 승인 시 voice가 생기는 것이 이 태스크의 의도된 결과다.)

- [ ] **Step 6: 커밋**

```bash
git add app/core/pipeline.py tests/test_pipeline_transition.py tests/test_api_projects.py
git commit -m "기능: 승인 시 다음 단계 등록하는 다단계 전이 (마지막 단계 승인은 프로젝트 완료)"
```

---

### Task 6: EdgeTTS provider + VOICE_PROVIDER 설정

**Files:**
- Modify: `pyproject.toml` (deps), `.env.example`, `app/config.py`
- Create: `app/providers/voice/edge_tts.py`
- Modify: `app/providers/base.py` (레지스트리)
- Modify: `tests/conftest.py` (테스트 기본 `VOICE_PROVIDER=fake`)
- Test: `tests/test_provider_voice_edge_tts.py`

**Interfaces:**
- Produces: `Settings.voice_provider: str`(기본 `"edge_tts"`), `EdgeTTS` — `stage="voice"`, `name="edge_tts"`, `__init__(communicate_factory=None)`; `REGISTRY["voice"] = {"fake": FakeVoice, "edge_tts": EdgeTTS}`

> **SDK 확인(중요):** `edge-tts`의 표준 사용법은 `edge_tts.Communicate(text, voice)` 객체를 만들고 `async for chunk in communicate.stream()`로 `{"type": "audio", "data": bytes}` 청크를 받는 것이다. Step 3에서 설치된 버전의 실제 인터페이스를 확인하고, `run()`과 테스트의 가짜 객체를 **같은 형태로** 맞춘다.

- [ ] **Step 1: 의존성 추가**

Run: `uv add edge-tts`
Expected: `pyproject.toml`에 `edge-tts` 추가, `uv.lock` 갱신. (네트워크 필요)

확인:
Run: `uv run python -c "import edge_tts; print('ok')"`
Expected: `ok`

- [ ] **Step 2: 실패 테스트 작성** — `tests/test_provider_voice_edge_tts.py`

```python
import pytest

from app.constants import AssetKind
from app.providers.base import REGISTRY, StageContext
from app.providers.voice.edge_tts import EdgeTTS
from app.utils import storage

_SCRIPT = {
    "title": "t",
    "hook": "훅",
    "scenes": [{"index": 1, "narration": "첫 문장.", "on_screen": "a"}],
    "estimated_duration_sec": 30,
}


class _FakeCommunicate:
    """edge_tts.Communicate 흉내 — stream()이 audio 청크를 내놓는다."""

    created: list[dict] = []

    def __init__(self, text, voice, **kwargs):
        type(self).created.append({"text": text, "voice": voice})

    async def stream(self):
        yield {"type": "audio", "data": b"ID3-fake-"}
        yield {"type": "WordBoundary"}  # 오디오가 아닌 청크는 무시돼야 한다
        yield {"type": "audio", "data": b"audio"}


@pytest.fixture(autouse=True)
def _reset():
    _FakeCommunicate.created = []


@pytest.mark.asyncio
async def test_run_streams_audio_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, workdir="projects/3/voice")
    result = await EdgeTTS(communicate_factory=_FakeCommunicate).run(ctx)

    written = (tmp_path / "projects/3/voice/voice.mp3").read_bytes()
    assert written == b"ID3-fake-audio"  # audio 청크만 이어붙는다
    assert result.assets[0]["kind"] == AssetKind.AUDIO
    assert result.assets[0]["path"] == "projects/3/voice/voice.mp3"
    assert result.assets[0]["meta"]["size_bytes"] == len(written)


@pytest.mark.asyncio
async def test_run_passes_narration_and_korean_voice(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, workdir="projects/4/voice")
    await EdgeTTS(communicate_factory=_FakeCommunicate).run(ctx)

    call = _FakeCommunicate.created[0]
    assert call["text"] == "첫 문장."
    assert call["voice"] == "ko-KR-SunHiNeural"


def test_registry_has_edge_tts():
    assert REGISTRY["voice"]["edge_tts"] is EdgeTTS
```

- [ ] **Step 3: 설치된 edge-tts 인터페이스 확인**

Run: `uv run python -c "import edge_tts, inspect; print(hasattr(edge_tts,'Communicate'), hasattr(edge_tts.Communicate,'stream'))"`
Expected: `True True`. 다르면 실제 인터페이스에 맞춰 아래 `run()`과 위 가짜 객체를 **동일하게** 조정한다.

- [ ] **Step 4: provider 작성** — `app/providers/voice/edge_tts.py`

```python
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.voice.text import narration_text
from app.utils import storage

_MODEL_VOICE = "ko-KR-SunHiNeural"  # 한국어 기본 목소리 (선택 UI는 다음 슬라이스)
_FILENAME = "voice.mp3"


class EdgeTTS(Provider):
    """edge-tts(무료·API 키 불필요)로 대본을 읽어 mp3를 만드는 provider."""

    stage = "voice"
    name = "edge_tts"

    def __init__(self, communicate_factory=None):
        # 테스트는 가짜 factory를 주입해 네트워크 없이 검증한다.
        self._communicate_factory = communicate_factory

    def _factory(self):
        if self._communicate_factory is None:
            # 파일명이 edge_tts.py지만 절대 import라 설치된 edge_tts 패키지를 가져온다.
            from edge_tts import Communicate

            self._communicate_factory = Communicate
        return self._communicate_factory

    async def run(self, ctx: StageContext) -> StageResult:
        text = narration_text(ctx.inputs)
        communicate = self._factory()(text, _MODEL_VOICE)
        chunks = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks += chunk["data"]

        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, bytes(chunks))
        meta = {"voice": _MODEL_VOICE, "size_bytes": size}
        return StageResult(
            output={"voice": _MODEL_VOICE, "size_bytes": size, "chars": len(text)},
            assets=[{"kind": AssetKind.AUDIO, "path": rel, "meta": meta}],
        )
```

- [ ] **Step 5: 설정 추가** — `app/config.py`의 `Settings`에 아래 1줄 추가(`script_provider` 아래)

```python
    voice_provider: str = "edge_tts"
```

`.env.example` 파일 끝에 추가:

```
VOICE_PROVIDER=edge_tts
```

- [ ] **Step 6: 레지스트리 등록** — `app/providers/base.py` 하단을 아래로 교체

```python
# 새 도구 추가 = 클래스 1개 + 여기 1줄. core는 손대지 않는다.
from app.providers.script.claude import ClaudeScript  # noqa: E402
from app.providers.script.fake import FakeScript  # noqa: E402
from app.providers.script.openai import OpenAIScript  # noqa: E402
from app.providers.voice.edge_tts import EdgeTTS  # noqa: E402
from app.providers.voice.fake import FakeVoice  # noqa: E402

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript, "openai": OpenAIScript, "claude": ClaudeScript},
    "voice": {"fake": FakeVoice, "edge_tts": EdgeTTS},
}
```

- [ ] **Step 7: 테스트 기본 provider 강제** — `tests/conftest.py` 최상단 블록에 1줄 추가

기존 `os.environ["SCRIPT_PROVIDER"] = "fake"` 바로 아래에 추가한다(`get_settings.cache_clear()` 호출보다 위여야 한다).

```python
os.environ["VOICE_PROVIDER"] = "fake"  # 통합 테스트는 실제 TTS 호출 없이 fake로
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run pytest tests/test_provider_voice_edge_tts.py -q`
Expected: PASS (3 passed)

- [ ] **Step 9: 커밋**

```bash
git add pyproject.toml uv.lock .env.example app/config.py app/providers/voice/edge_tts.py app/providers/base.py tests/conftest.py tests/test_provider_voice_edge_tts.py
git commit -m "기능: edge-tts voice provider와 VOICE_PROVIDER 설정 추가(테스트는 fake 강제)"
```

---

### Task 7: 산출물 서빙 엔드포인트

**Files:**
- Modify: `app/api/projects.py`
- Test: `tests/test_api_asset.py`

**Interfaces:**
- Consumes: `queries.find_asset_by_stage`, `storage.resolve`, `_load_owned_project`/`_load_stage`(기존 헬퍼)
- Produces: `GET /api/projects/{project_id}/stages/{name}/asset` → `FileResponse`. 소유자 아님·단계 없음·산출물 없음·파일 없음 → 모두 404.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_api_asset.py`

```python
import pytest

_PW = "pw12345"


async def _register_login(client, db_session, email: str):
    """가입 → 승인 → 로그인. 기존 test_api_projects.py의 _login과 같은 흐름을 쓴다."""
    from app.auth.security import hash_password
    from app.constants import UserRole, UserStatus
    from app.models.user import User

    user = User(email=email, password_hash=hash_password(_PW),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    r = await client.post("/api/auth/login", json={"email": email, "password": _PW})
    assert r.status_code == 200
    return user


async def _project_with_voice_run(client):
    """프로젝트 생성 → script 실행·승인 → voice 실행. (conftest가 provider를 fake로 강제)"""
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")
    await client.post(f"/api/projects/{pid}/stages/script/approve")
    await client.post(f"/api/projects/{pid}/stages/voice/run")
    return pid


@pytest.mark.asyncio
async def test_owner_downloads_audio(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _register_login(client, db_session, "asset-owner@example.com")
    pid = await _project_with_voice_run(client)

    r = await client.get(f"/api/projects/{pid}/stages/voice/asset")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert len(r.content) > 0


@pytest.mark.asyncio
async def test_other_user_gets_404(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _register_login(client, db_session, "asset-a@example.com")
    pid = await _project_with_voice_run(client)

    # 다른 사용자로 로그인 → 남의 프로젝트 산출물은 존재 자체를 숨긴다
    await _register_login(client, db_session, "asset-b@example.com")
    r = await client.get(f"/api/projects/{pid}/stages/voice/asset")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_missing_asset_gets_404(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _register_login(client, db_session, "asset-none@example.com")
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    # script 단계는 파일 산출물이 없다
    r = await client.get(f"/api/projects/{pid}/stages/script/asset")
    assert r.status_code == 404
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_api_asset.py -q`
Expected: FAIL — 404 (엔드포인트 없음). `test_owner_downloads_audio`가 200을 기대하며 실패한다.

- [ ] **Step 3: 엔드포인트 추가** — `app/api/projects.py`

상단 import에 추가한다.

```python
from fastapi.responses import FileResponse

from app.constants import AssetKind  # 기존 constants import 줄에 함께 추가
from app.utils import storage
```

파일 끝에 아래 엔드포인트를 추가한다.

```python
# kind → 내려줄 MIME 타입. 새 산출물 종류가 생기면 여기 한 줄.
_MEDIA_TYPES = {AssetKind.AUDIO: "audio/mpeg"}


@router.get("/{project_id}/stages/{name}/asset")
async def get_stage_asset(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])  # 남의 프로젝트면 여기서 404
    stage = await _load_stage(conn, project_id, name)

    row = await queries.find_asset_by_stage(conn, stage_id=stage["id"])
    if row is None:
        raise Errors.not_found("산출물을 찾을 수 없습니다.")

    path = storage.resolve(row["path"])
    if not path.exists():
        # DB에는 있는데 파일이 없다 — 존재를 꾸며내지 않는다.
        raise Errors.not_found("산출물을 찾을 수 없습니다.")
    return FileResponse(path, media_type=_MEDIA_TYPES.get(row["kind"], "application/octet-stream"))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_api_asset.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 전체 스위트 회귀 확인**

Run: `uv run pytest -q`
Expected: 전체 PASS (network·과금 없음)

- [ ] **Step 6: 커밋**

```bash
git add app/api/projects.py tests/test_api_asset.py
git commit -m "기능: 단계 산출물 서빙 엔드포인트 추가(소유자만, 없으면 404)"
```

---

### Task 8: 프론트 — 전체 단계 렌더 + voice 카드·오디오 재생

**Files:**
- Modify: `web/src/lib/projects.ts`
- Modify: `web/src/pages/projects/ProjectDetail.tsx`

**Interfaces:**
- Consumes: `GET /api/projects/{id}/stages/{name}/asset`
- Produces: 상세 화면이 **모든 단계**를 카드로 렌더하고, voice 카드는 `<audio controls>`로 재생을 제공

> 현재 `ProjectDetail.tsx`는 `const stage = detail.stages[0]`로 **첫 단계만** 그린다. 단계가 2개가 됐으므로 전체를 순회하도록 바꾼다.

- [ ] **Step 1: lib에 타입·URL 헬퍼 추가** — `web/src/lib/projects.ts`

`ScriptOutput` 아래에 voice 산출 타입을 추가한다.

```typescript
export type VoiceOutput = { voice: string; size_bytes: number; chars: number }
```

`Stage`의 `output` 타입을 아래로 바꾼다.

```typescript
  output: ScriptOutput | VoiceOutput | Record<string, never>
```

`projects` 객체에 asset URL 헬퍼를 추가한다(`regenerate` 아래).

```typescript
  // 재생성 후 브라우저가 옛 음성을 캐시하지 않도록 attempt를 붙인다.
  assetUrl: (id: number, name: string, attempt: number) =>
    `/api/projects/${id}/stages/${name}/asset?v=${attempt}`,
```

파일 끝에 voice 판별 헬퍼를 추가한다(기존 `hasScript` 아래).

```typescript
export function hasVoice(output: Stage['output']): output is VoiceOutput {
  return 'voice' in output
}
```

- [ ] **Step 2: 단계 라벨과 voice 뷰 추가** — `web/src/pages/projects/ProjectDetail.tsx`

import에 `hasVoice`를 추가한다(기존 `hasScript, projects, STAGE_BADGE, ...` 목록에 함께).

`ScriptView` 아래에 단계 라벨 상수와 voice 뷰를 추가한다.

```tsx
const STAGE_LABEL: Record<string, string> = {
  script: '대본 (script)',
  voice: '음성 (voice)',
}

function VoiceView({ projectId, stage }: { projectId: number; stage: Stage }) {
  if (!hasVoice(stage.output)) return null
  return (
    <div className="mt-4 space-y-2 rounded-md border border-slate-200 p-4">
      <audio
        controls
        className="w-full"
        src={projects.assetUrl(projectId, stage.name, stage.attempt)}
      />
      <div className="text-xs text-slate-400">
        목소리 {stage.output.voice} · {stage.output.chars}자
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 단계 카드를 컴포넌트로 분리하고 전체 순회로 교체**

`ProjectDetail`의 `const stage = detail.stages[0]` 줄을 지우고, 카드 마크업을 아래 `StageCard`로 옮긴 뒤 전체 단계를 순회한다.

`VoiceView` 아래에 추가:

```tsx
function StageCard({
  projectId,
  stage,
  acting,
  act,
}: {
  projectId: number
  stage: Stage
  acting: boolean
  act: (fn: () => Promise<Detail>) => Promise<void>
}) {
  return (
    <div className="mt-4 rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium text-slate-800">{STAGE_LABEL[stage.name] ?? stage.name}</span>
          <StageBadge status={stage.status} />
        </div>
        <div className="flex gap-2">
          {(stage.status === 'PENDING' || stage.status === 'FAILED') && (
            <button
              onClick={() => act(() => projects.run(projectId, stage.name))}
              disabled={acting}
              className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              실행
            </button>
          )}
          {stage.status === 'NEEDS_REVIEW' && (
            <>
              <button
                onClick={() => act(() => projects.approve(projectId, stage.name))}
                disabled={acting}
                className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                승인
              </button>
              <button
                onClick={() => act(() => projects.regenerate(projectId, stage.name))}
                disabled={acting}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                재생성
              </button>
            </>
          )}
        </div>
      </div>

      {stage.status === 'FAILED' && stage.error && (
        <div className="mt-3 text-sm text-red-700">오류: {stage.error}</div>
      )}
      {(stage.status === 'NEEDS_REVIEW' || stage.status === 'APPROVED') && (
        <>
          <ScriptView stage={stage} />
          <VoiceView projectId={projectId} stage={stage} />
        </>
      )}
    </div>
  )
}
```

`ProjectDetail`의 반환 JSX에서 기존 단계 카드 `<div className="mt-6 rounded-lg border …">…</div>` 블록 전체를 아래로 교체한다.

```tsx
      <div className="mt-6">
        {detail.stages.map((s) => (
          <StageCard key={s.id} projectId={projectId} stage={s} acting={acting} act={act} />
        ))}
      </div>
```

- [ ] **Step 4: 타입체크·빌드 확인**

Run: `npm run build`
Expected: `tsc -b && vite build` 통과 (오류 없음)

- [ ] **Step 5: 린트 확인**

Run: `npm run lint`
Expected: 신규 경고 없음 (`src/lib/auth.tsx`의 기존 경고 1건만 남는다)

- [ ] **Step 6: 커밋**

```bash
git add web/src/lib/projects.ts web/src/pages/projects/ProjectDetail.tsx
git commit -m "기능: 상세 화면이 전체 단계를 렌더하고 voice는 오디오로 재생"
```

---

## 최종 검증

- [ ] 백엔드 전체: `uv run pytest -q` → 전체 PASS (오프라인·무과금)
- [ ] 프론트: `npm run build` · `npm run lint` 통과
- [ ] 마이그레이션: `uv run alembic upgrade head` 적용됨
- [ ] (선택, 네트워크 필요) 실제 흐름 스모크: `.env`에 `VOICE_PROVIDER=edge_tts`로 앱 기동 → 프로젝트 생성 → 대본 실행·승인 → **음성 실행** → 상세에서 재생되는지, 재생성 시 새 음성으로 바뀌는지 확인

## Self-Review 결과 (작성자 점검)

- **스펙 커버리지:** Asset 모델(§3)→T1, 저장·쿼리(§6)→T2, provider 계약·FakeVoice(§5)→T3, inputs 주입·Asset 교체(§4·§3)→T4, 다단계 전이(§4)→T5, edge_tts·VOICE_PROVIDER(§5)→T6, 서빙 엔드포인트(§6)→T7, 프론트(§7)→T8, 테스트 전략(§9)→각 태스크. 누락 없음.
- **플레이스홀더:** 모든 스텝에 실제 코드·명령·기대 출력을 담음. edge-tts 인터페이스 차이는 T6 Step 3의 확인 스텝으로 명시 처리.
- **타입 일관성:** `StageContext(workdir)`·`StageResult(assets)`가 T3에서 정의되고 T4·T6에서 동일하게 사용. `narration_text`는 T3에서 **`app/providers/voice/text.py`(공용 모듈)** 에 정의되어 fake·edge_tts가 모두 여기서 가져온다(실제 provider가 fake 모듈에 의존하지 않게 하기 위함). `AssetKind.AUDIO`가 T1 정의·T3/T4/T7 사용에서 일치. asset dict 키 `{kind, path, meta}`가 T3·T4·T6에서 동일. 파일명 `voice.mp3`가 FakeVoice·EdgeTTS 공통.
- **알려진 확인 지점:** T6의 `uv add edge-tts`는 네트워크 필요. T5 Step 5는 승인 후 단계 수가 2개로 늘어나 기존 API 테스트 수정이 필요할 수 있음(의도된 동작 변경).
