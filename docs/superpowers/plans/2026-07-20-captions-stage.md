# captions 단계 (음성 → 단어별 자막) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** voice가 만든 mp3를 로컬 whisper로 받아써 단어별 srt를 만드는 `captions` 단계를 추가한다.

**Architecture:** 기존 provider 레지스트리·Asset·다단계 전이 토대 위에 세 번째 단계를 얹는다. core 변경은 단 하나 — `StageContext`에 `input_assets`를 추가해 앞 단계가 만든 **파일**을 뒤 단계에 넘기는 일반형을 만든다(render도 이걸 쓴다). whisper는 CPU 블로킹이므로 `asyncio.to_thread`로 감싸 이벤트 루프를 비켜준다.

**Tech Stack:** Python 3.12 · FastAPI · faster-whisper(CTranslate2) · aiosql/asyncpg · React 19 + TypeScript

**설계 문서:** [2026-07-20-captions-stage-design.md](../specs/2026-07-20-captions-stage-design.md)

## Global Constraints

- **마이그레이션 없음** — `assets.kind`에 CHECK 제약이 없어 새 코드값 `SRT`를 그대로 넣을 수 있다.
- **`approve_stage`를 수정하지 않는다** — `STAGE_ORDER`에 한 줄 추가하면 기존 일반화 코드가 그대로 동작한다.
- srt 큐 1개 = **단어 1개**. 타임코드는 `HH:MM:SS,mmm`.
- whisper 실행 옵션은 모듈 상수로 고정: `device="cpu"`, `compute_type="int8"`, `language="ko"`, `word_timestamps=True`.
- **`initial_prompt`를 쓰지 않는다** (환각 위험).
- 설정 기본값: `CAPTIONS_PROVIDER=whisper`, `WHISPER_MODEL=small`. **테스트는 `fake` 강제.**
- 파일 경로: `projects/{project_id}/captions/captions.srt`. media type `application/x-subrip`.
- 파일을 만드는 테스트는 `monkeypatch.setattr(storage, "_root", lambda: tmp_path)`로 격리한다(기존 관례).
- 테스트 실행은 항상 `npm test` (= `uv run pytest`). 프론트 타입 검사는 `npm run build`.
- 커밋 메시지는 기존 한국어 관례를 따른다(`기능:`, `수정:`, `문서:`).

---

## Task 1: srt 직렬화 (순수 함수)

DB도 파일도 없는 순수 함수부터 만든다. 이후 두 provider가 공유한다.

**Files:**
- Create: `app/providers/captions/__init__.py` (빈 파일)
- Create: `app/providers/captions/srt.py`
- Test: `tests/test_captions_srt.py`

**Interfaces:**
- Consumes: 없음
- Produces: `to_srt(words: list[dict]) -> str` — `words`는 `[{"w": str, "s": float, "e": float}, ...]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_captions_srt.py`:

```python
from app.providers.captions.srt import to_srt


def test_single_word_block():
    assert to_srt([{"w": "안녕", "s": 0.0, "e": 0.5}]) == (
        "1\n00:00:00,000 --> 00:00:00,500\n안녕\n"
    )


def test_blocks_are_numbered_and_blank_line_separated():
    out = to_srt([{"w": "가", "s": 0.0, "e": 0.4}, {"w": "나", "s": 0.4, "e": 0.9}])
    assert out == (
        "1\n00:00:00,000 --> 00:00:00,400\n가\n"
        "\n"
        "2\n00:00:00,400 --> 00:00:00,900\n나\n"
    )


def test_hour_boundary_formats_correctly():
    out = to_srt([{"w": "끝", "s": 3661.5, "e": 3662.0}])
    assert "01:01:01,500 --> 01:01:02,000" in out


def test_zero_length_word_is_clamped_to_minimum():
    # whisper가 end <= start인 단어를 내놓으면 재생기가 거부하는 srt가 된다.
    out = to_srt([{"w": "짧", "s": 1.0, "e": 1.0}])
    assert "00:00:01,000 --> 00:00:01,050" in out


def test_negative_start_is_clamped_to_zero():
    out = to_srt([{"w": "앞", "s": -0.2, "e": 0.3}])
    assert out.startswith("1\n00:00:00,000 --> 00:00:00,300\n")


def test_empty_words_yields_empty_string():
    assert to_srt([]) == ""
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `npm test -- tests/test_captions_srt.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.captions'`

- [ ] **Step 3: 최소 구현을 쓴다**

`app/providers/captions/__init__.py` — 빈 파일로 만든다.

`app/providers/captions/srt.py`:

```python
_MIN_DURATION = 0.05  # 길이 0인 큐는 재생기가 거부한다 — 최소 50ms를 보장한다


def _timecode(seconds: float) -> str:
    """초 → SRT 타임코드 HH:MM:SS,mmm."""
    ms = max(int(round(seconds * 1000)), 0)
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def to_srt(words: list[dict]) -> str:
    """단어별 타임스탬프를 SRT로 직렬화한다. 큐 1개 = 단어 1개.

    words: [{"w": 단어, "s": 시작초, "e": 종료초}, ...]
    단어 사이의 빈틈은 메우지 않는다(무음은 무음 그대로).
    """
    blocks = []
    for number, word in enumerate(words, start=1):
        start = max(word["s"], 0.0)
        end = max(word["e"], start + _MIN_DURATION)
        blocks.append(f"{number}\n{_timecode(start)} --> {_timecode(end)}\n{word['w']}\n")
    return "\n".join(blocks)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `npm test -- tests/test_captions_srt.py`
Expected: PASS — 6 passed

- [ ] **Step 5: 커밋**

```bash
git add app/providers/captions/ tests/test_captions_srt.py
git commit -m "기능: 단어별 SRT 직렬화 함수 추가"
```

---

## Task 2: captions 단계를 파이프라인에 등록

`STAGE_ORDER`에 `captions`를 넣는다. 이 시점엔 provider가 없어 실행은 못 하지만, **승인 전이는 완성된다.** 기존 "voice 승인 → DONE" 테스트가 깨지므로 함께 고친다.

**Files:**
- Modify: `app/constants.py` (`StageName`, `AssetKind`)
- Modify: `app/config.py:22` (설정 2줄 추가)
- Modify: `app/core/pipeline.py:15` (`STAGE_ORDER`)
- Modify: `.env.example`
- Modify: `tests/conftest.py:4`
- Test: `tests/test_pipeline_transition.py` (기존 테스트 1개 교체 + 헬퍼 추가)

**Interfaces:**
- Consumes: 없음
- Produces: `StageName.CAPTIONS == "captions"`, `AssetKind.SRT == "SRT"`, `Settings.captions_provider`, `Settings.whisper_model`, `STAGE_ORDER == ["script", "voice", "captions"]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_pipeline_transition.py`에서 **기존 `test_approving_last_stage_marks_project_done`(65~83행)을 아래 세 덩어리로 교체**한다. 헬퍼는 `_seed_script_needs_review` 바로 아래에 둔다.

```python
async def _approve_via_needs_review(session, project, name: str, actor: int):
    """PENDING으로 등록된 단계를 NEEDS_REVIEW로 올린 뒤 승인한다(실행은 건너뛴다)."""
    conn = await raw_connection(session)
    stage = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=name))
    )
    await queries.update_stage_status(
        conn, id=stage["id"], status=StageStatus.NEEDS_REVIEW,
        updated_at=now_local(), updated_by=actor,
    )
    await session.commit()
    stage["status"] = StageStatus.NEEDS_REVIEW
    await pipeline.approve_stage(session, project, stage, actor_id=actor)
    return stage


@pytest.mark.asyncio
async def test_approving_voice_registers_captions_pending(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans2@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)
    await _approve_via_needs_review(db_session, project, StageName.VOICE, actor)

    conn = await raw_connection(db_session)
    captions = await queries.find_stage(conn, project_id=project["id"], name=StageName.CAPTIONS)
    assert captions is not None, "voice 승인 시 captions 단계가 등록돼야 한다"
    assert captions["status"] == StageStatus.PENDING

    updated_project = dict(await queries.find_project_by_id(conn, id=project["id"]))
    assert updated_project["current_stage"] == StageName.CAPTIONS
    # 아직 마지막 단계가 아니므로 DONE이 아니다
    assert updated_project["status"] != ProjectStatus.DONE


@pytest.mark.asyncio
async def test_approving_captions_marks_project_done(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans5@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)
    await _approve_via_needs_review(db_session, project, StageName.VOICE, actor)
    await _approve_via_needs_review(db_session, project, StageName.CAPTIONS, actor)

    conn = await raw_connection(db_session)
    updated_project = dict(await queries.find_project_by_id(conn, id=project["id"]))
    assert updated_project["status"] == ProjectStatus.DONE
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `npm test -- tests/test_pipeline_transition.py`
Expected: FAIL — `AttributeError: CAPTIONS` (`StageName`에 아직 없다)

- [ ] **Step 3: 상수·설정·STAGE_ORDER를 추가한다**

`app/constants.py` — `StageName`에 한 줄, `AssetKind`에 한 줄:

```python
class StageName(StrEnum):
    """stages.name 코드값. provider 레지스트리 키와 맞춰 소문자."""

    SCRIPT = "script"
    VOICE = "voice"
    CAPTIONS = "captions"
```

```python
class AssetKind(StrEnum):
    """assets.kind 코드값. DB에 대문자로 저장된다."""

    AUDIO = "AUDIO"
    SRT = "SRT"
```

`app/config.py` — `voice_provider` 아래에 두 줄:

```python
    voice_provider: str = "edge_tts"
    captions_provider: str = "whisper"
    whisper_model: str = "small"
```

`app/core/pipeline.py:15`:

```python
STAGE_ORDER: list[str] = ["script", "voice", "captions"]  # render 미구현
```

`.env.example` — 마지막 줄 아래에 추가:

```
VOICE_PROVIDER=edge_tts
CAPTIONS_PROVIDER=whisper
# whisper 모델 크기: tiny|base|small|medium (클수록 정확하고 느리다)
WHISPER_MODEL=small
```

`tests/conftest.py` — 3~4행 아래에 한 줄 추가:

```python
os.environ["CAPTIONS_PROVIDER"] = "fake"  # 통합 테스트는 실제 whisper 모델 없이 fake로
os.environ["WHISPER_MODEL"] = "small"  # 로컬 .env 값에 테스트가 흔들리지 않게 고정
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `npm test -- tests/test_pipeline_transition.py`
Expected: PASS — 5 passed (기존 3건 + 교체로 생긴 2건)

- [ ] **Step 5: 전체 테스트로 회귀를 확인한다**

Run: `npm test`
Expected: PASS — 실패 0건.

"voice 승인 → DONE"을 기대하는 테스트는 위에서 교체한 `test_pipeline_transition.py` 하나뿐이다.
`test_api_projects.py:47`과 `test_pipeline_run_stage.py:64`는 **script** 승인만 다루므로 영향이 없다.

`STAGE_ORDER`의 리터럴 값을 고정한 테스트도 하나 있다 — `tests/test_pipeline_state_machine.py:6`.
같이 고친다:

```python
def test_stage_order():
    assert STAGE_ORDER == ["script", "voice", "captions"]
```

- [ ] **Step 6: 커밋**

```bash
git add app/constants.py app/config.py app/core/pipeline.py .env.example tests/conftest.py tests/test_pipeline_transition.py
git commit -m "기능: captions 단계를 파이프라인 STAGE_ORDER에 등록"
```

---

## Task 3: 단계 간 파일 전달 (`input_assets`)

captions는 앞 단계가 만든 **파일**이 입력이다. `_previous_outputs`를 output과 asset을 함께 모으는 `_previous_context`로 일반화한다.

**Files:**
- Modify: `app/providers/base.py:8-15` (`StageContext`)
- Modify: `app/core/pipeline.py:41-50` (`_previous_outputs` → `_previous_context`), `app/core/pipeline.py:83-89` (`run_stage`의 ctx 생성)
- Test: `tests/test_pipeline_transition.py` (기존 테스트 1개 교체), `tests/test_pipeline_voice_run.py` (테스트 1개 추가)

**Interfaces:**
- Consumes: Task 2의 `STAGE_ORDER`(captions 포함)
- Produces:
  - `StageContext.input_assets: dict` — `{단계이름: [{"kind": str, "path": str, "meta": dict}, ...]}`
  - `pipeline._previous_context(conn, project_id: int, upto: str) -> tuple[dict, dict]` — `(outputs, assets)`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_pipeline_transition.py`에서 **기존 `test_previous_outputs_excludes_current_and_later_stages`(105~119행)를 교체**한다:

```python
@pytest.mark.asyncio
async def test_previous_context_excludes_current_and_later_stages(db_session):
    """STAGE_ORDER를 순회하다 현재 단계에서 멈추는지 확인.

    script(첫 단계) 기준으로는 앞 단계가 없으므로 비어 있어야 하고,
    voice 기준으로는 script 것만 포함돼야 한다(자기 자신·이후 단계 제외).
    """
    actor, project, script = await _seed_script_needs_review(db_session, "trans4@example.com")
    conn = await raw_connection(db_session)

    inputs, assets = await pipeline._previous_context(conn, project["id"], StageName.SCRIPT)
    assert inputs == {}
    assert assets == {}

    inputs, assets = await pipeline._previous_context(conn, project["id"], StageName.VOICE)
    assert inputs == {"script": {"scenes": []}}
    assert assets == {"script": []}  # script는 파일 산출물이 없다
```

`tests/test_pipeline_voice_run.py` 맨 아래에 추가:

```python
@pytest.mark.asyncio
async def test_previous_context_carries_voice_audio_to_next_stage(db_session, monkeypatch, tmp_path):
    """voice가 만든 mp3가 다음 단계(captions)의 input_assets로 전달되는지."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-assets@example.com")
    await pipeline.run_stage(db_session, project, voice, actor_id=actor)

    conn = await raw_connection(db_session)
    _, assets = await pipeline._previous_context(conn, project["id"], StageName.CAPTIONS)
    audio = [a for a in assets["voice"] if a["kind"] == AssetKind.AUDIO]
    assert len(audio) == 1
    assert audio[0]["path"] == f"projects/{project['id']}/voice/voice.mp3"
    # meta는 jsonb라 asyncpg가 문자열로 준다 — dict로 디코드돼야 한다
    assert audio[0]["meta"]["size_bytes"] > 0
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `npm test -- tests/test_pipeline_transition.py tests/test_pipeline_voice_run.py`
Expected: FAIL — `AttributeError: module 'app.core.pipeline' has no attribute '_previous_context'`

- [ ] **Step 3: `StageContext`에 필드를 추가한다**

`app/providers/base.py` — `inputs` 바로 아래:

```python
@dataclass
class StageContext:
    """단계 실행에 필요한 입력. (SSE on_progress는 해당 단계 도입 시 확장)"""

    topic: str
    settings: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)  # 이전 단계 산출물 (script엔 비어있음)
    input_assets: dict = field(default_factory=dict)  # {단계이름: [{kind, path, meta}]} 파일 산출물
    attempt: int = 0  # 재생성 횟수 → provider 출력 변주 seed
    workdir: str = ""  # 저장소 기준 이 단계의 디렉토리 (파일을 만드는 단계만 사용)
```

- [ ] **Step 4: `_previous_outputs`를 `_previous_context`로 바꾼다**

`app/core/pipeline.py`의 `_previous_outputs`(41~50행)를 통째로 교체한다:

```python
def _decode_meta(value):
    """asyncpg가 문자열로 돌려준 assets.meta(jsonb)를 dict로 되돌린다."""
    return json.loads(value) if isinstance(value, str) else value


async def _previous_context(conn, project_id: int, upto: str) -> tuple[dict, dict]:
    """이 단계 앞 단계들의 (outputs, assets)를 한 번의 순회로 모은다.

    outputs: {단계이름: output}                       — 요약 JSON
    assets:  {단계이름: [{kind, path, meta}, ...]}    — 파일 산출물
    """
    outputs: dict = {}
    assets: dict = {}
    for name in STAGE_ORDER:
        if name == upto:
            break
        row = await queries.find_stage(conn, project_id=project_id, name=name)
        if row is None:
            continue
        outputs[name] = decode_stage(dict(row))["output"]
        assets[name] = [
            {"kind": r["kind"], "path": r["path"], "meta": _decode_meta(r["meta"])}
            async for r in queries.list_assets_by_stage(conn, stage_id=row["id"])
        ]
    return outputs, assets
```

- [ ] **Step 5: `run_stage`가 새 함수를 쓰게 한다**

`app/core/pipeline.py`의 `ctx = StageContext(...)` 블록(83~89행)을 교체한다:

```python
    inputs, input_assets = await _previous_context(conn, project["id"], stage["name"])
    ctx = StageContext(
        topic=project["topic"],
        settings=project.get("settings", {}),
        inputs=inputs,
        input_assets=input_assets,
        attempt=stage["attempt"],
        workdir=f"projects/{project['id']}/{stage['name']}",
    )
```

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `npm test`
Expected: PASS — 실패 0건

- [ ] **Step 7: 커밋**

```bash
git add app/providers/base.py app/core/pipeline.py tests/test_pipeline_transition.py tests/test_pipeline_voice_run.py
git commit -m "기능: 단계 간 파일 산출물 전달(input_assets) 일반화"
```

---

## Task 4: FakeCaptions provider + srt 서빙

whisper 없이 파이프라인 전 구간이 돌아가게 만든다. 여기까지 하면 **주제 → 대본 → 음성 → 자막 → 승인**이 API로 완주된다.

**Files:**
- Create: `app/providers/captions/audio.py`
- Create: `app/providers/captions/fake.py`
- Modify: `app/providers/base.py:36-46` (import + `REGISTRY`)
- Modify: `app/api/projects.py:156` (`_MEDIA_TYPES`)
- Test: `tests/test_provider_captions_fake.py`, `tests/test_api_captions.py`

**Interfaces:**
- Consumes: Task 1의 `to_srt`, Task 2의 `StageName.CAPTIONS`·`AssetKind.SRT`, Task 3의 `StageContext.input_assets`
- Produces:
  - `input_audio_path(ctx: StageContext) -> str` — voice 단계 AUDIO asset의 저장소 상대 경로. 없으면 `AppError(409, "VOICE_ASSET_MISSING", ...)`
  - `FakeCaptions` — `REGISTRY["captions"]["fake"]`
  - captions `Stage.output` 계약: `{"language": str, "duration_sec": float, "word_count": int, "words": [{"w","s","e"}]}`

- [ ] **Step 1: 실패하는 provider 테스트를 쓴다**

`tests/test_provider_captions_fake.py`:

```python
import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.captions.fake import FakeCaptions
from app.utils import storage
from app.utils.errors import AppError

_SCRIPT = {
    "title": "t",
    "hook": "훅",
    "scenes": [{"index": 1, "narration": "첫 문장 이다", "on_screen": "a"}],
    "estimated_duration_sec": 30,
}
_ASSETS = {StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/7/voice/voice.mp3", "meta": {}}]}


def _ctx() -> StageContext:
    return StageContext(
        topic="t", inputs={"script": _SCRIPT}, input_assets=_ASSETS, workdir="projects/7/captions"
    )


@pytest.mark.asyncio
async def test_run_writes_srt_with_one_cue_per_word(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await FakeCaptions().run(_ctx())

    written = (tmp_path / "projects/7/captions/captions.srt").read_text(encoding="utf-8")
    assert written.count("-->") == 3  # "첫 문장 이다" → 단어 3개
    assert result.assets[0]["kind"] == AssetKind.SRT
    assert result.assets[0]["path"] == "projects/7/captions/captions.srt"


@pytest.mark.asyncio
async def test_output_carries_words_for_the_frontend(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await FakeCaptions().run(_ctx())

    assert result.output["word_count"] == 3
    assert [w["w"] for w in result.output["words"]] == ["첫", "문장", "이다"]
    assert result.output["words"][0]["s"] == 0.0
    assert result.output["duration_sec"] > 0


@pytest.mark.asyncio
async def test_missing_voice_asset_raises_apperror(monkeypatch, tmp_path):
    """voice 산출물이 없으면 run_stage의 except가 FAILED로 흡수할 AppError를 던진다."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, input_assets={}, workdir="projects/8/captions")

    with pytest.raises(AppError) as exc:
        await FakeCaptions().run(ctx)
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_registry_has_fake_captions():
    assert REGISTRY["captions"]["fake"] is FakeCaptions
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `npm test -- tests/test_provider_captions_fake.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.captions.fake'`

- [ ] **Step 3: 입력 오디오 조회 헬퍼를 만든다**

`app/providers/captions/audio.py`:

```python
from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.utils.errors import AppError


def input_audio_path(ctx: StageContext) -> str:
    """captions의 입력인 voice 단계 mp3의 저장소 상대 경로.

    없으면 AppError — run_stage의 except가 FAILED + 이 메시지로 흡수한다.
    """
    for asset in ctx.input_assets.get(StageName.VOICE, []):
        if asset["kind"] == AssetKind.AUDIO:
            return asset["path"]
    raise AppError(
        409, "VOICE_ASSET_MISSING", "음성 파일이 없습니다. voice 단계를 먼저 실행해 주세요."
    )
```

- [ ] **Step 4: FakeCaptions를 만든다**

`app/providers/captions/fake.py`:

```python
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.captions.audio import input_audio_path
from app.providers.captions.srt import to_srt
from app.providers.voice.text import narration_text
from app.utils import storage

_FILENAME = "captions.srt"
_SEC_PER_WORD = 0.4  # 단어마다 균등 배분 — 결정적이라 테스트가 흔들리지 않는다


class FakeCaptions(Provider):
    """whisper 없이 대본을 단어로 쪼개 결정적 자막을 만드는 개발/테스트용 provider."""

    stage = "captions"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        # 오디오 바이트를 읽지는 않지만, 입력 계약은 진짜 provider와 똑같이 검증한다.
        input_audio_path(ctx)
        words = [
            {"w": word, "s": round(i * _SEC_PER_WORD, 3), "e": round((i + 1) * _SEC_PER_WORD, 3)}
            for i, word in enumerate(narration_text(ctx.inputs).split())
        ]
        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, to_srt(words).encode("utf-8"))
        return StageResult(
            output={
                "language": "ko",
                "duration_sec": round(len(words) * _SEC_PER_WORD, 3),
                "word_count": len(words),
                "words": words,
            },
            assets=[{"kind": AssetKind.SRT, "path": rel, "meta": {"model": "fake", "size_bytes": size}}],
        )
```

- [ ] **Step 5: 레지스트리에 등록한다**

`app/providers/base.py` — import 블록과 `REGISTRY`에 각각 한 줄:

```python
# 새 도구 추가 = 클래스 1개 + 여기 1줄. core는 손대지 않는다.
from app.providers.captions.fake import FakeCaptions  # noqa: E402
from app.providers.script.claude import ClaudeScript  # noqa: E402
from app.providers.script.fake import FakeScript  # noqa: E402
from app.providers.script.openai import OpenAIScript  # noqa: E402
from app.providers.voice.edge_tts import EdgeTTS  # noqa: E402
from app.providers.voice.fake import FakeVoice  # noqa: E402

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript, "openai": OpenAIScript, "claude": ClaudeScript},
    "voice": {"fake": FakeVoice, "edge_tts": EdgeTTS},
    "captions": {"fake": FakeCaptions},
}
```

- [ ] **Step 6: provider 테스트가 통과하는지 확인한다**

Run: `npm test -- tests/test_provider_captions_fake.py`
Expected: PASS — 4 passed

- [ ] **Step 7: 실패하는 API 통합 테스트를 쓴다**

`tests/test_api_captions.py`:

```python
from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User

_PW = "pw12345"


async def _login(client, db_session, email: str) -> User:
    user = User(email=email, password_hash=hash_password(_PW),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": _PW})
    assert resp.status_code == 200
    return user


async def _project_through_voice(client) -> int:
    """프로젝트 생성 → script 실행·승인 → voice 실행·승인. (conftest가 provider를 fake로 강제)"""
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")
    await client.post(f"/api/projects/{pid}/stages/script/approve")
    await client.post(f"/api/projects/{pid}/stages/voice/run")
    await client.post(f"/api/projects/{pid}/stages/voice/approve")
    return pid


async def test_running_captions_produces_words_and_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-run@example.com")
    pid = await _project_through_voice(client)

    detail = (await client.post(f"/api/projects/{pid}/stages/captions/run")).json()
    captions = next(s for s in detail["stages"] if s["name"] == "captions")
    assert captions["status"] == "NEEDS_REVIEW"
    assert captions["output"]["word_count"] > 0
    assert captions["output"]["words"][0]["w"]  # 프론트가 srt를 파싱하지 않게 하는 계약

    asset = await client.get(f"/api/projects/{pid}/stages/captions/asset")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "application/x-subrip"
    assert "-->" in asset.content.decode("utf-8")


async def test_approving_captions_completes_the_project(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-done@example.com")
    pid = await _project_through_voice(client)

    await client.post(f"/api/projects/{pid}/stages/captions/run")
    detail = (await client.post(f"/api/projects/{pid}/stages/captions/approve")).json()
    assert detail["project"]["status"] == "DONE"


async def test_other_user_cannot_download_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-a@example.com")
    pid = await _project_through_voice(client)
    await client.post(f"/api/projects/{pid}/stages/captions/run")

    await _login(client, db_session, "cap-b@example.com")
    r = await client.get(f"/api/projects/{pid}/stages/captions/asset")
    assert r.status_code == 404
    assert r.json()["code"] == "RESOURCE_NOT_FOUND"


async def test_regenerate_replaces_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-regen@example.com")
    pid = await _project_through_voice(client)
    await client.post(f"/api/projects/{pid}/stages/captions/run")

    from app.db import raw_connection
    from app.queries import queries

    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=pid, name="captions")
    before = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage["id"])]

    assert (await client.post(f"/api/projects/{pid}/stages/captions/regenerate")).status_code == 200

    after = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage["id"])]
    assert len(after) == 1  # 누적되지 않고 교체
    assert after[0]["id"] != before[0]["id"]
    assert (await client.get(f"/api/projects/{pid}/stages/captions/asset")).status_code == 200
```

- [ ] **Step 8: API 테스트가 실패하는지 확인한다**

Run: `npm test -- tests/test_api_captions.py`
Expected: FAIL — `assert 'application/octet-stream' == 'application/x-subrip'` (`_MEDIA_TYPES`에 SRT가 없다)

- [ ] **Step 9: SRT media type을 등록한다**

`app/api/projects.py:156`:

```python
# kind → 내려줄 MIME 타입. 새 산출물 종류가 생기면 여기 한 줄.
_MEDIA_TYPES = {AssetKind.AUDIO: "audio/mpeg", AssetKind.SRT: "application/x-subrip"}
```

- [ ] **Step 10: 전체 테스트를 돌린다**

Run: `npm test`
Expected: PASS — 실패 0건

- [ ] **Step 11: 커밋**

```bash
git add app/providers/captions/ app/providers/base.py app/api/projects.py tests/test_provider_captions_fake.py tests/test_api_captions.py
git commit -m "기능: FakeCaptions provider와 srt 산출물 서빙 추가"
```

---

## Task 5: WhisperCaptions provider (faster-whisper)

진짜 STT를 붙인다. 테스트는 `transcribe` 함수를 주입해 모델·네트워크·오디오 없이 검증한다(`EdgeTTS`의 `communicate_factory`와 같은 패턴).

**Files:**
- Create: `app/providers/captions/whisper.py`
- Modify: `pyproject.toml:19` (의존성)
- Modify: `app/providers/base.py` (import + `REGISTRY["captions"]`)
- Modify: `README.md` (기술 스택 표 + 최초 실행 주의)
- Test: `tests/test_provider_captions_whisper.py`

**Interfaces:**
- Consumes: Task 4의 `input_audio_path`, Task 1의 `to_srt`, Task 2의 `Settings.whisper_model`
- Produces: `WhisperCaptions(transcribe=None)` — `REGISTRY["captions"]["whisper"]`. 주입되는 `transcribe`의 시그니처는 `(audio_path: str, model_size: str) -> tuple[list[dict], str, float]` = `(words, language, duration_sec)`

- [ ] **Step 1: 의존성을 추가한다**

`pyproject.toml`의 `dependencies` 마지막에 한 줄:

```toml
    "edge-tts>=7.2.8",
    "faster-whisper>=1.1.0",
]
```

Run: `uv sync`
Expected: `faster-whisper`와 `ctranslate2`가 설치된다(torch는 설치되지 않는다).

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_provider_captions_whisper.py`:

```python
import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.captions.whisper import WhisperCaptions
from app.utils import storage
from app.utils.errors import AppError

_ASSETS = {StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/9/voice/voice.mp3", "meta": {}}]}

_calls: list[dict] = []


def _fake_transcribe(audio_path: str, model_size: str):
    _calls.append({"audio_path": audio_path, "model_size": model_size})
    words = [{"w": "안녕", "s": 0.0, "e": 0.5}, {"w": "하세요", "s": 0.5, "e": 1.1}]
    return words, "ko", 1.2


@pytest.fixture(autouse=True)
def _reset():
    _calls.clear()


def _ctx() -> StageContext:
    return StageContext(topic="t", input_assets=_ASSETS, workdir="projects/9/captions")


@pytest.mark.asyncio
async def test_run_writes_srt_and_output(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await WhisperCaptions(transcribe=_fake_transcribe).run(_ctx())

    written = (tmp_path / "projects/9/captions/captions.srt").read_text(encoding="utf-8")
    assert written.startswith("1\n00:00:00,000 --> 00:00:00,500\n안녕\n")
    assert result.output == {
        "language": "ko",
        "duration_sec": 1.2,
        "word_count": 2,
        "words": [{"w": "안녕", "s": 0.0, "e": 0.5}, {"w": "하세요", "s": 0.5, "e": 1.1}],
    }
    assert result.assets[0]["kind"] == AssetKind.SRT
    assert result.assets[0]["path"] == "projects/9/captions/captions.srt"


@pytest.mark.asyncio
async def test_run_passes_absolute_audio_path_and_model_size(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await WhisperCaptions(transcribe=_fake_transcribe).run(_ctx())

    # provider는 저장소 상대 경로를 절대 경로로 풀어 넘겨야 한다(whisper는 실제 파일을 연다)
    assert _calls[0]["audio_path"] == str(tmp_path / "projects/9/voice/voice.mp3")
    assert _calls[0]["model_size"] == "small"  # 설정 기본값


@pytest.mark.asyncio
async def test_missing_voice_asset_raises_apperror(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", input_assets={}, workdir="projects/9/captions")

    with pytest.raises(AppError) as exc:
        await WhisperCaptions(transcribe=_fake_transcribe).run(ctx)
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_registry_has_whisper():
    assert REGISTRY["captions"]["whisper"] is WhisperCaptions
```

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `npm test -- tests/test_provider_captions_whisper.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.captions.whisper'`

- [ ] **Step 4: WhisperCaptions를 만든다**

`app/providers/captions/whisper.py`:

```python
import asyncio
from functools import lru_cache

from app.config import get_settings
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.captions.audio import input_audio_path
from app.providers.captions.srt import to_srt
from app.utils import storage

_FILENAME = "captions.srt"
_DEVICE = "cpu"
_COMPUTE_TYPE = "int8"  # CPU에서 2배 이상 빠르고 한국어 품질 저하는 미미하다
_LANGUAGE = "ko"


@lru_cache
def _load_model(model_size: str):
    """모델은 프로세스당 1회만 로드한다. 최초 1회는 자동 다운로드(~500MB)라 느리다."""
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device=_DEVICE, compute_type=_COMPUTE_TYPE)


def _transcribe(audio_path: str, model_size: str) -> tuple[list[dict], str, float]:
    """오디오를 받아써 (단어들, 언어, 길이)를 돌려준다. CPU 블로킹 호출."""
    segments, info = _load_model(model_size).transcribe(
        audio_path, language=_LANGUAGE, word_timestamps=True
    )
    # segments는 지연 제너레이터다 — 이 스레드 안에서 끝까지 소비해야 한다.
    words = [
        {"w": word.word.strip(), "s": round(word.start, 3), "e": round(word.end, 3)}
        for segment in segments
        for word in (segment.words or [])
        if word.word.strip()
    ]
    return words, info.language, round(info.duration, 3)


class WhisperCaptions(Provider):
    """faster-whisper(로컬)로 mp3를 받아써 단어별 srt를 만드는 provider."""

    stage = "captions"
    name = "whisper"

    def __init__(self, transcribe=None):
        # 테스트는 가짜 transcribe를 주입해 모델·네트워크 없이 검증한다.
        self._transcribe = transcribe or _transcribe

    async def run(self, ctx: StageContext) -> StageResult:
        audio = storage.resolve(input_audio_path(ctx))
        model_size = get_settings().whisper_model
        # CPU를 수십 초 점유하는 블로킹 호출 — 이벤트 루프를 비켜준다.
        words, language, duration = await asyncio.to_thread(
            self._transcribe, str(audio), model_size
        )

        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, to_srt(words).encode("utf-8"))
        return StageResult(
            output={
                "language": language,
                "duration_sec": duration,
                "word_count": len(words),
                "words": words,
            },
            assets=[
                {"kind": AssetKind.SRT, "path": rel, "meta": {"model": model_size, "size_bytes": size}}
            ],
        )
```

- [ ] **Step 5: 레지스트리에 등록한다**

`app/providers/base.py` — import 한 줄 추가, `REGISTRY["captions"]`에 항목 추가:

```python
from app.providers.captions.fake import FakeCaptions  # noqa: E402
from app.providers.captions.whisper import WhisperCaptions  # noqa: E402
```

```python
    "captions": {"fake": FakeCaptions, "whisper": WhisperCaptions},
```

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `npm test -- tests/test_provider_captions_whisper.py`
Expected: PASS — 4 passed

- [ ] **Step 7: README에 최초 실행 주의를 적는다**

`README.md`의 백엔드 기술 스택 표에서 `| 테스트 | ... |` 행 **위**에 한 줄 추가:

```
| 자막(STT) | faster-whisper (로컬 CPU, torch 불필요) |
```

`### 최초 1회만` 절의 두 번째 코드 블록(`docker compose up -d db` …) **아래**에 문단 추가:

```
> **captions 단계 최초 실행 시** whisper `small` 모델(~500MB)을 자동으로 내려받습니다.
> 그 첫 실행만 오래 걸리고 이후에는 캐시를 씁니다. 모델 크기는 `.env`의 `WHISPER_MODEL`로 바꿉니다
> (`tiny`|`base`|`small`|`medium`). 키 없이 쓰려면 `CAPTIONS_PROVIDER=fake`로 두세요.
```

- [ ] **Step 8: 전체 테스트를 돌린다**

Run: `npm test`
Expected: PASS — 실패 0건

- [ ] **Step 9: 커밋**

```bash
git add pyproject.toml uv.lock app/providers/captions/whisper.py app/providers/base.py README.md tests/test_provider_captions_whisper.py
git commit -m "기능: faster-whisper 로컬 STT provider 추가"
```

---

## Task 6: 프론트 — captions 카드 (오디오 + 단어 하이라이트)

검토 수단을 붙인다. captions 카드지만 **재생하는 오디오는 voice 단계의 mp3**다.

**Files:**
- Modify: `web/src/lib/projects.ts:10-22, 57-63` (타입 + 가드)
- Modify: `web/src/pages/projects/ProjectDetail.tsx` (STAGE_LABEL, CaptionsView, StageCard, ProjectDetail)

**Interfaces:**
- Consumes: Task 4의 captions `Stage.output` 계약 (`{language, duration_sec, word_count, words:[{w,s,e}]}`)
- Produces: 없음 (마지막 태스크)

- [ ] **Step 1: 타입과 가드를 추가한다**

`web/src/lib/projects.ts` — `VoiceOutput` 아래에 추가:

```ts
export type VoiceOutput = { voice: string; size_bytes: number; chars: number }
export type CaptionWord = { w: string; s: number; e: number }
export type CaptionsOutput = {
  language: string
  duration_sec: number
  word_count: number
  words: CaptionWord[]
}
```

`Stage`의 `output` 유니온에 추가:

```ts
  output: ScriptOutput | VoiceOutput | CaptionsOutput | Record<string, never>
```

파일 맨 아래 `hasVoice` 다음에 추가:

```ts
export function hasCaptions(output: Stage['output']): output is CaptionsOutput {
  return 'words' in output
}
```

- [ ] **Step 2: 타입 검사가 통과하는지 확인한다**

Run: `npm run build`
Expected: 성공 (아직 아무도 `hasCaptions`를 쓰지 않지만 타입은 유효해야 한다)

- [ ] **Step 3: CaptionsView를 만든다**

`web/src/pages/projects/ProjectDetail.tsx` — 1행의 import를 바꾼다:

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
```

5행의 import에 `hasCaptions`를 더한다:

```tsx
import { hasCaptions, hasScript, hasVoice, projects, STAGE_BADGE, type ProjectDetail as Detail, type Stage } from '../../lib/projects'
```

`STAGE_LABEL`에 한 줄 추가:

```tsx
const STAGE_LABEL: Record<string, string> = {
  script: '대본 (script)',
  voice: '음성 (voice)',
  captions: '자막 (captions)',
}
```

`VoiceView` 아래에 `CaptionsView`를 추가한다:

```tsx
function CaptionsView({
  projectId,
  stage,
  voiceAttempt,
}: {
  projectId: number
  stage: Stage
  voiceAttempt: number | null
}) {
  // 훅은 조건부 반환보다 먼저 호출해야 한다.
  const cursor = useRef(0)
  const [active, setActive] = useState(-1)

  if (!hasCaptions(stage.output)) return null
  const { words, word_count, duration_sec } = stage.output

  // 단어가 수백 개라 매 틱 전체를 훑지 않고 현재 위치에서 전진한다.
  const onTimeUpdate = (e: React.SyntheticEvent<HTMLAudioElement>) => {
    const t = e.currentTarget.currentTime
    let i = cursor.current
    if (i >= words.length || t < words[i].s) i = 0 // 뒤로 감았다 → 처음부터 다시 전진
    while (i < words.length - 1 && t >= words[i + 1].s) i += 1
    cursor.current = i
    setActive(t >= words[i].s && t < words[i].e ? i : -1)
  }

  return (
    <div className="mt-4 space-y-3 rounded-md border border-slate-200 p-4">
      {voiceAttempt !== null && (
        <audio
          controls
          className="w-full"
          src={projects.assetUrl(projectId, 'voice', voiceAttempt)}
          onTimeUpdate={onTimeUpdate}
        />
      )}
      <div className="flex flex-wrap gap-1 text-sm leading-7">
        {words.map((word, i) => (
          <span
            key={i}
            className={`rounded px-1 ${
              i === active ? 'bg-yellow-200 text-slate-900' : 'text-slate-700'
            }`}
          >
            {word.w}
          </span>
        ))}
      </div>
      <div className="text-xs text-slate-400">
        {word_count}단어 · {duration_sec.toFixed(1)}초
      </div>
    </div>
  )
}
```

- [ ] **Step 4: StageCard에 연결한다**

`StageCard`의 props에 `voiceAttempt`를 더한다:

```tsx
function StageCard({
  projectId,
  stage,
  voiceAttempt,
  acting,
  act,
}: {
  projectId: number
  stage: Stage
  voiceAttempt: number | null
  acting: boolean
  act: (fn: () => Promise<Detail>) => Promise<void>
}) {
```

[실행] 버튼의 라벨을 바꾼다 — captions는 수십 초가 걸리므로 진행 중임을 알린다:

```tsx
            <button
              onClick={() => act(() => projects.run(projectId, stage.name))}
              disabled={acting}
              className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {acting ? '생성 중… (최대 1분)' : '실행'}
            </button>
```

검토 영역에 `CaptionsView`를 더한다:

```tsx
      {(stage.status === 'NEEDS_REVIEW' || stage.status === 'APPROVED') && (
        <>
          <ScriptView stage={stage} />
          <VoiceView projectId={projectId} stage={stage} />
          <CaptionsView projectId={projectId} stage={stage} voiceAttempt={voiceAttempt} />
        </>
      )}
```

- [ ] **Step 5: ProjectDetail이 voice의 attempt를 내려주게 한다**

`ProjectDetail`의 반환 JSX 직전에 한 줄, 그리고 map을 바꾼다:

```tsx
  const voiceAttempt = detail.stages.find((s) => s.name === 'voice')?.attempt ?? null

  return (
```

```tsx
        {detail.stages.map((s) => (
          <StageCard
            key={s.id}
            projectId={projectId}
            stage={s}
            voiceAttempt={voiceAttempt}
            acting={acting}
            act={act}
          />
        ))}
```

- [ ] **Step 6: 린트와 타입 검사를 돌린다**

Run: `npm run lint`
Expected: 오류 0건

Run: `npm run build`
Expected: 성공 (`tsc -b`가 통과하고 vite 번들이 생성된다)

- [ ] **Step 7: 백엔드 전체 테스트로 회귀를 확인한다**

Run: `npm test`
Expected: PASS — 실패 0건

- [ ] **Step 8: 브라우저에서 직접 확인한다**

Run: `npm run dev`

1. 로그인 → 프로젝트 생성
2. script [실행] → [승인]
3. voice [실행] → 오디오 재생 확인 → [승인]
4. captions [실행] → 버튼이 `생성 중… (최대 1분)`으로 바뀌는지 확인
5. 자막 카드에서 재생 → **단어가 순서대로 노란색으로 하이라이트되는지** 확인
6. 재생바를 뒤로 끌었을 때 하이라이트가 따라오는지 확인
7. [승인] → 프로젝트 상태가 `DONE`이 되는지 확인

> `.env`의 `CAPTIONS_PROVIDER`가 `whisper`면 이 확인 중 whisper 모델(~500MB)을 내려받는다.
> 다운로드 없이 흐름만 보려면 `.env`에 `CAPTIONS_PROVIDER=fake`를 두고 확인한다.

- [ ] **Step 9: 커밋**

```bash
git add web/src/lib/projects.ts web/src/pages/projects/ProjectDetail.tsx
git commit -m "기능: 상세 화면에 captions 카드와 단어 하이라이트 추가"
```

---

## 완료 기준

- `npm test` 전체 통과
- `npm run lint`, `npm run build` 통과
- 주제 입력 → 대본 → 음성 → 자막 → 승인까지 브라우저에서 완주하고 프로젝트가 `DONE`이 된다
- `storage/projects/{id}/captions/captions.srt`가 단어별 큐로 생성돼 있다
