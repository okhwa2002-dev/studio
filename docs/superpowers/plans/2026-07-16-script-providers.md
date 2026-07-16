# 실제 script provider (OpenAI + Claude) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `fake` 옆에 실제 대본을 생성하는 `openai`(gpt-4o-mini)·`claude`(Haiku 4.5) script provider 두 개를 레지스트리에 추가하고, 기본 provider를 설정으로 고르게 한다 — core·API·프론트·대본 스키마는 그대로.

**Architecture:** 직전 슬라이스가 만든 `Provider` 계약/레지스트리에 provider 클래스 2개만 얹는다. 두 provider는 공식 `openai`/`anthropic` SDK의 **구조화 출력**으로 동일한 대본 JSON 스키마(`ScriptDraft`)를 강제하고, `validate()`로 실행 전 API 키를 확인한다. `create_project`는 provider 이름을 설정(`SCRIPT_PROVIDER`)에서 읽고, `run_stage`는 `run()` 직전에 `validate()`를 호출한다.

**Tech Stack:** Python 3.12 · FastAPI · openai SDK(`AsyncOpenAI`) · anthropic SDK(`AsyncAnthropic`) · Pydantic(구조화 출력 스키마) · pytest(가짜 클라이언트 주입, network 없음) · uv.

## Global Constraints

- **provider 2개 추가, `fake` 유지.** 레지스트리 `REGISTRY["script"] = {"fake":…, "openai":…, "claude":…}`.
- **기본 provider = 설정 `SCRIPT_PROVIDER`(기본 `openai`).** `create_project`가 `get_settings().script_provider`를 사용.
- **모델 ID:** OpenAI `gpt-4o-mini`, Claude `claude-haiku-4-5`. 각 provider 모듈 상수 `_MODEL`로 고정.
- **대본 스키마 불변:** `{title, hook, scenes[{index, narration, on_screen}], estimated_duration_sec}` — fake 출력과 1:1. Pydantic `ScriptDraft`로 표현.
- **API 키:** `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`는 앱 설정(env)에서 읽는다(프로젝트 settings 아님). 없어도 앱은 기동되고, 해당 provider 실행 시에만 실패.
- **키 누락/외부 오류 → stage `FAILED` + 친절한 메시지.** 앱은 죽지 않음. 재시도는 각 SDK 내장(429/5xx). 별도 `utils/retry` 없음.
- **테스트 무과금·오프라인:** 파이프라인·API 통합 테스트는 `SCRIPT_PROVIDER=fake`로 강제, 실제 provider 2개는 **가짜 클라이언트 주입** 단위 테스트(실제 API 미호출).
- **SDK 호출 검증:** 구조화 출력 메서드/필드는 설치된 SDK 버전에 맞춰 확인 후 사용(각 태스크에 확인 스텝 포함).
- **커밋:** 각 태스크 끝에 커밋 스텝이 있으나, 이 저장소는 사용자가 직접 커밋한다 — 구현자는 커밋하지 말고 변경을 working tree에 남긴다(디스패치 시 컨트롤러가 지시).
- **테스트 실행:** `uv run pytest ...` 사용(bare `pytest`/`python`은 이 환경에서 막힐 수 있음).
- **참조 스펙:** `docs/superpowers/specs/2026-07-16-script-providers-design.md`

---

### Task 1: 의존성 + 설정 + 공유 스키마/프롬프트

**Files:**
- Modify: `pyproject.toml` (deps)
- Modify: `app/config.py` (Settings 필드)
- Modify: `.env.example`
- Create: `app/providers/script/schema.py`
- Create: `app/providers/script/prompts.py`
- Test: `tests/test_script_schema.py`

**Interfaces:**
- Produces:
  - `app.config.Settings.openai_api_key: str`, `.anthropic_api_key: str`, `.script_provider: str`(기본 `"openai"`)
  - `app.providers.script.schema.ScriptScene`, `ScriptDraft` (Pydantic)
  - `app.providers.script.prompts.system_prompt() -> str`, `user_prompt(topic: str, attempt: int) -> str`

- [ ] **Step 1: 의존성 추가**

Run: `uv add openai anthropic`
Expected: `pyproject.toml`의 `dependencies`에 `openai`, `anthropic` 추가되고 `uv.lock` 갱신. (오프라인이라 실패하면, 네트워크가 되는 환경에서 실행해야 함 — 이 태스크는 네트워크 필요)

확인:
Run: `uv run python -c "import openai, anthropic; print('ok')"`
Expected: `ok`

- [ ] **Step 2: 실패 테스트 작성** — `tests/test_script_schema.py`

```python
from app.config import Settings
from app.providers.script.prompts import system_prompt, user_prompt
from app.providers.script.schema import ScriptDraft, ScriptScene


def test_settings_has_provider_fields():
    s = Settings(database_url="postgresql+asyncpg://x", jwt_secret="secret-secret-secret-32bytes!!")
    assert s.script_provider == "openai"       # 기본값
    assert s.openai_api_key == ""
    assert s.anthropic_api_key == ""


def test_script_draft_shape():
    draft = ScriptDraft(
        title="t",
        hook="h",
        scenes=[ScriptScene(index=1, narration="n", on_screen="o")],
        estimated_duration_sec=45,
    )
    dumped = draft.model_dump()
    assert set(dumped.keys()) == {"title", "hook", "scenes", "estimated_duration_sec"}
    assert set(dumped["scenes"][0].keys()) == {"index", "narration", "on_screen"}


def test_user_prompt_adds_regenerate_hint():
    assert "새로운 각도" not in user_prompt("바다 거북", attempt=0)
    assert "새로운 각도" in user_prompt("바다 거북", attempt=1)
    assert "바다 거북" in user_prompt("바다 거북", attempt=0)
    assert isinstance(system_prompt(), str) and system_prompt()
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/test_script_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: app.providers.script.schema` (또는 Settings 필드 없음)

- [ ] **Step 4: Settings 필드 추가** — `app/config.py`의 `Settings` 클래스에 아래 3줄 추가(기존 필드들 아래)

```python
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    script_provider: str = "openai"
```

- [ ] **Step 5: `.env.example` 추가** — 파일 끝에 추가

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
SCRIPT_PROVIDER=openai
```

- [ ] **Step 6: 공유 스키마 작성** — `app/providers/script/schema.py`

```python
from pydantic import BaseModel


class ScriptScene(BaseModel):
    index: int
    narration: str   # voice가 읽을 나레이션
    on_screen: str   # 화면에 표시할 짧은 자막/키워드


class ScriptDraft(BaseModel):
    title: str
    hook: str
    scenes: list[ScriptScene]
    estimated_duration_sec: int
```

- [ ] **Step 7: 공유 프롬프트 작성** — `app/providers/script/prompts.py`

```python
_SYSTEM = (
    "너는 한국어 숏폼(쇼츠) 영상 대본 작가다. 주어진 주제로 60초 이내 쇼츠 대본을 만든다. "
    "3초 안에 시선을 잡는 훅으로 시작하고, 장면 3개 내외로 구성하며, 각 장면에는 "
    "나레이션(narration)과 화면에 표시할 짧은 자막(on_screen)을 채운다. 과장은 피하고 사실적으로 쓴다."
)


def system_prompt() -> str:
    return _SYSTEM


def user_prompt(topic: str, attempt: int) -> str:
    text = f"주제: {topic}"
    if attempt > 0:
        text += "\n\n이전 시도와는 다른 새로운 각도로 다시 작성해줘."
    return text
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run pytest tests/test_script_schema.py -q`
Expected: PASS (3 passed)

- [ ] **Step 9: 커밋**

```bash
git add pyproject.toml uv.lock app/config.py .env.example app/providers/script/schema.py app/providers/script/prompts.py tests/test_script_schema.py
git commit -m "기능: script provider용 openai·anthropic 의존성, 설정, 공유 스키마/프롬프트 추가"
```

---

### Task 2: OpenAIScript provider

**Files:**
- Create: `app/providers/script/openai.py`
- Test: `tests/test_provider_script_openai.py`

**Interfaces:**
- Consumes: `Provider`/`StageContext`/`StageResult` (`app.providers.base`), `ScriptDraft`(schema), `system_prompt`/`user_prompt`(prompts), `get_settings`(config), `AppError`(errors)
- Produces: `OpenAIScript` — `stage="script"`, `name="openai"`, `__init__(client=None)`; `validate(settings)`가 `openai_api_key` 없으면 `AppError(400, "OPENAI_API_KEY_MISSING", …)`; `run(ctx)`가 구조화 출력으로 `ScriptDraft`를 얻어 `StageResult(output=draft.model_dump())` 반환

> **SDK 확인(중요):** 구조화 출력 호출은 설치된 `openai` 버전에 따라 `client.beta.chat.completions.parse(...)` 또는 `client.chat.completions.parse(...)`이며, 결과는 `completion.choices[0].message.parsed`(Pydantic 인스턴스)다. Step 3에서 설치 버전에 어느 경로가 있는지 확인하고 `run()`의 실제 호출과 아래 테스트의 가짜 클라이언트 속성 체인을 **같은 경로로** 맞춘다. 아래 코드는 `beta.chat.completions.parse` 기준.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_script_openai.py`

```python
from types import SimpleNamespace

import pytest

from app.providers.base import StageContext, StageResult
from app.providers.script.openai import OpenAIScript
from app.providers.script.schema import ScriptDraft, ScriptScene
from app.utils.errors import AppError

_DRAFT = ScriptDraft(
    title="바다 거북 — 60초 쇼츠",
    hook="3초 안에 반전을 보여드립니다.",
    scenes=[ScriptScene(index=1, narration="n", on_screen="o")],
    estimated_duration_sec=45,
)


class _FakeCompletions:
    def __init__(self, draft):
        self._draft = draft
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(parsed=self._draft)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeOpenAI:
    def __init__(self, draft):
        self.completions = _FakeCompletions(draft)
        # client.beta.chat.completions.parse 경로를 흉내
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self.completions))


@pytest.mark.asyncio
async def test_run_maps_structured_output_to_schema():
    fake = _FakeOpenAI(_DRAFT)
    result = await OpenAIScript(client=fake).run(StageContext(topic="바다 거북"))
    assert isinstance(result, StageResult)
    assert result.output == _DRAFT.model_dump()
    # 모델·주제가 요청에 실렸는지
    call = fake.completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert any("바다 거북" in m["content"] for m in call["messages"])


@pytest.mark.asyncio
async def test_run_passes_regenerate_hint_on_attempt():
    fake = _FakeOpenAI(_DRAFT)
    await OpenAIScript(client=fake).run(StageContext(topic="바다 거북", attempt=1))
    call = fake.completions.calls[0]
    assert any("새로운 각도" in m["content"] for m in call["messages"])


def test_validate_raises_when_key_missing(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.openai.get_settings",
        lambda: SimpleNamespace(openai_api_key=""),
    )
    with pytest.raises(AppError) as exc:
        OpenAIScript().validate({})
    assert exc.value.code == "OPENAI_API_KEY_MISSING"


def test_validate_passes_when_key_present(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.openai.get_settings",
        lambda: SimpleNamespace(openai_api_key="sk-test"),
    )
    OpenAIScript().validate({})  # 예외 없음
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_provider_script_openai.py -q`
Expected: FAIL — `ModuleNotFoundError: app.providers.script.openai`

- [ ] **Step 3: 설치된 openai SDK의 구조화 출력 경로 확인**

Run: `uv run python -c "import openai, inspect; c=openai.AsyncOpenAI(api_key='x'); print('beta.parse' if hasattr(c.beta.chat.completions,'parse') else 'chat.parse' if hasattr(c.chat.completions,'parse') else 'none')"`
Expected: `beta.parse` 또는 `chat.parse`. 결과에 맞춰 아래 `run()`의 `client.beta.chat.completions.parse`를 `client.chat.completions.parse`로 바꾸고, 위 테스트의 가짜 클라이언트 속성 체인도 동일하게 맞춘다.

- [ ] **Step 4: provider 작성** — `app/providers/script/openai.py`

```python
from typing import TYPE_CHECKING, Optional

from app.config import get_settings
from app.providers.base import Provider, StageContext, StageResult
from app.providers.script.prompts import system_prompt, user_prompt
from app.providers.script.schema import ScriptDraft
from app.utils.errors import AppError

if TYPE_CHECKING:
    from openai import AsyncOpenAI

_MODEL = "gpt-4o-mini"


class OpenAIScript(Provider):
    """OpenAI(ChatGPT)로 대본을 생성하는 provider. 구조화 출력으로 ScriptDraft를 강제한다."""

    stage = "script"
    name = "openai"

    def __init__(self, client: Optional["AsyncOpenAI"] = None):
        self._client = client

    def validate(self, settings: dict) -> None:
        if not get_settings().openai_api_key:
            raise AppError(400, "OPENAI_API_KEY_MISSING", "OPENAI_API_KEY가 설정되지 않았습니다.")

    def _get_client(self) -> "AsyncOpenAI":
        if self._client is None:
            # 파일명이 openai.py지만 절대 import라 설치된 openai 패키지를 가져온다.
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        return self._client

    async def run(self, ctx: StageContext) -> StageResult:
        client = self._get_client()
        completion = await client.beta.chat.completions.parse(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": user_prompt(ctx.topic, ctx.attempt)},
            ],
            response_format=ScriptDraft,
        )
        draft: ScriptDraft = completion.choices[0].message.parsed
        return StageResult(output=draft.model_dump())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_provider_script_openai.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/providers/script/openai.py tests/test_provider_script_openai.py
git commit -m "기능: OpenAI(gpt-4o-mini) script provider 추가"
```

---

### Task 3: ClaudeScript provider

**Files:**
- Create: `app/providers/script/claude.py`
- Test: `tests/test_provider_script_claude.py`

**Interfaces:**
- Consumes: 동일(`Provider`/`StageContext`/`StageResult`, `ScriptDraft`, `system_prompt`/`user_prompt`, `get_settings`, `AppError`)
- Produces: `ClaudeScript` — `stage="script"`, `name="claude"`, `__init__(client=None)`; `validate(settings)`가 `anthropic_api_key` 없으면 `AppError(400, "ANTHROPIC_API_KEY_MISSING", …)`; `run(ctx)`가 `StageResult(output=draft.model_dump())` 반환

> **SDK 확인:** `claude-api` 스킬 기준 구조화 출력은 `client.messages.parse(model=…, max_tokens=…, system=…, messages=[…], output_format=ScriptDraft)`이고 결과는 `message.parsed_output`(Pydantic). Step 3에서 설치된 `anthropic` 버전에 `messages.parse`가 있는지 확인하고, 없으면 `messages.create(...)` + JSON 파싱으로 대체하되 최종적으로 `ScriptDraft`로 검증해 `model_dump()`한다. 아래 코드는 `messages.parse` 기준.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_script_claude.py`

```python
from types import SimpleNamespace

import pytest

from app.providers.base import StageContext, StageResult
from app.providers.script.claude import ClaudeScript
from app.providers.script.schema import ScriptDraft, ScriptScene
from app.utils.errors import AppError

_DRAFT = ScriptDraft(
    title="바다 거북 — 60초 쇼츠",
    hook="3초 안에 반전을 보여드립니다.",
    scenes=[ScriptScene(index=1, narration="n", on_screen="o")],
    estimated_duration_sec=45,
)


class _FakeMessages:
    def __init__(self, draft):
        self._draft = draft
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self._draft)


class _FakeAnthropic:
    def __init__(self, draft):
        self.messages = _FakeMessages(draft)


@pytest.mark.asyncio
async def test_run_maps_structured_output_to_schema():
    fake = _FakeAnthropic(_DRAFT)
    result = await ClaudeScript(client=fake).run(StageContext(topic="바다 거북"))
    assert isinstance(result, StageResult)
    assert result.output == _DRAFT.model_dump()
    call = fake.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert any("바다 거북" in m["content"] for m in call["messages"])


@pytest.mark.asyncio
async def test_run_passes_regenerate_hint_on_attempt():
    fake = _FakeAnthropic(_DRAFT)
    await ClaudeScript(client=fake).run(StageContext(topic="바다 거북", attempt=2))
    call = fake.messages.calls[0]
    assert any("새로운 각도" in m["content"] for m in call["messages"])


def test_validate_raises_when_key_missing(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.claude.get_settings",
        lambda: SimpleNamespace(anthropic_api_key=""),
    )
    with pytest.raises(AppError) as exc:
        ClaudeScript().validate({})
    assert exc.value.code == "ANTHROPIC_API_KEY_MISSING"


def test_validate_passes_when_key_present(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.claude.get_settings",
        lambda: SimpleNamespace(anthropic_api_key="sk-ant-test"),
    )
    ClaudeScript().validate({})
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_provider_script_claude.py -q`
Expected: FAIL — `ModuleNotFoundError: app.providers.script.claude`

- [ ] **Step 3: 설치된 anthropic SDK의 구조화 출력 경로 확인**

Run: `uv run python -c "import anthropic; c=anthropic.AsyncAnthropic(api_key='x'); print('has parse' if hasattr(c.messages,'parse') else 'no parse')"`
Expected: `has parse`. `no parse`면 `run()`을 `messages.create(...)` + `ScriptDraft.model_validate_json(text)`로 대체하고, 테스트의 가짜 클라이언트도 그 형태로 맞춘다.

- [ ] **Step 4: provider 작성** — `app/providers/script/claude.py`

```python
from typing import TYPE_CHECKING, Optional

from app.config import get_settings
from app.providers.base import Provider, StageContext, StageResult
from app.providers.script.prompts import system_prompt, user_prompt
from app.providers.script.schema import ScriptDraft
from app.utils.errors import AppError

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

_MODEL = "claude-haiku-4-5"


class ClaudeScript(Provider):
    """Claude(Anthropic)로 대본을 생성하는 provider. 구조화 출력으로 ScriptDraft를 강제한다."""

    stage = "script"
    name = "claude"

    def __init__(self, client: Optional["AsyncAnthropic"] = None):
        self._client = client

    def validate(self, settings: dict) -> None:
        if not get_settings().anthropic_api_key:
            raise AppError(400, "ANTHROPIC_API_KEY_MISSING", "ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    def _get_client(self) -> "AsyncAnthropic":
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    async def run(self, ctx: StageContext) -> StageResult:
        client = self._get_client()
        message = await client.messages.parse(
            model=_MODEL,
            max_tokens=2048,
            system=system_prompt(),
            messages=[{"role": "user", "content": user_prompt(ctx.topic, ctx.attempt)}],
            output_format=ScriptDraft,
        )
        draft: ScriptDraft = message.parsed_output
        return StageResult(output=draft.model_dump())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_provider_script_claude.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/providers/script/claude.py tests/test_provider_script_claude.py
git commit -m "기능: Claude(Haiku 4.5) script provider 추가"
```

---

### Task 4: 레지스트리 등록 (base.py)

**Files:**
- Modify: `app/providers/base.py`
- Test: `tests/test_provider_registry.py`

**Interfaces:**
- Consumes: `OpenAIScript`, `ClaudeScript`, `FakeScript`
- Produces: `REGISTRY["script"] == {"fake":…, "openai":…, "claude":…}`; `get_provider("script", name)`가 각 provider 인스턴스 반환

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_registry.py`

```python
from app.providers.base import REGISTRY, get_provider
from app.providers.script.claude import ClaudeScript
from app.providers.script.fake import FakeScript
from app.providers.script.openai import OpenAIScript


def test_registry_has_all_three_script_providers():
    assert set(REGISTRY["script"].keys()) == {"fake", "openai", "claude"}


def test_get_provider_returns_each_type():
    assert isinstance(get_provider("script", "fake"), FakeScript)
    assert isinstance(get_provider("script", "openai"), OpenAIScript)
    assert isinstance(get_provider("script", "claude"), ClaudeScript)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_provider_registry.py -q`
Expected: FAIL — `KeyError`/`AssertionError` (openai·claude 미등록)

- [ ] **Step 3: base.py의 하단 import·REGISTRY 교체** — `app/providers/base.py`의 `# 새 도구 추가` 주석부터 `REGISTRY` 정의까지를 아래로 교체

```python
# 새 도구 추가 = 클래스 1개 + 여기 1줄. core는 손대지 않는다.
from app.providers.script.claude import ClaudeScript  # noqa: E402
from app.providers.script.fake import FakeScript  # noqa: E402
from app.providers.script.openai import OpenAIScript  # noqa: E402

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript, "openai": OpenAIScript, "claude": ClaudeScript},
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_provider_registry.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/providers/base.py tests/test_provider_registry.py
git commit -m "기능: 레지스트리에 openai·claude script provider 등록"
```

---

### Task 5: run_stage에서 validate() 호출

**Files:**
- Modify: `app/core/pipeline.py` (`run_stage`에 `validate()` + `_error_message`)
- Test: `tests/test_pipeline_validate.py`

**Interfaces:**
- Consumes: `get_provider`, `StageContext`, 상수, `now_local`, `queries`, `raw_connection`
- Produces: `run_stage`가 `provider.run()` 전에 `provider.validate(ctx.settings)`를 호출하고, 예외 시 stage `FAILED` + `error`(친절한 메시지). `error` 문자열은 `AppError`면 `.message`, 아니면 `str(exc)`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_pipeline_validate.py`

```python
import json

import pytest

from app.constants import ProjectStatus, StageName, StageStatus
from app.core import pipeline
from app.db import raw_connection
from app.queries import queries
from app.utils.time import now_local


async def _seed_openai_stage(session):
    conn = await raw_connection(session)
    now = now_local()
    from app.auth.security import hash_password
    from app.constants import UserRole, UserStatus
    from app.models.user import User

    user = User(email="valowner@example.com", password_hash=hash_password("pw12345"),
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
        conn, project_id=project_id, name=StageName.SCRIPT, provider="openai",
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await session.commit()
    project = pipeline.decode_stage(dict(await queries.find_project_by_id(conn, id=project_id)))
    stage = pipeline.decode_stage(dict(await queries.find_stage(conn, project_id=project_id, name=StageName.SCRIPT)))
    return user.id, project, stage


@pytest.mark.asyncio
async def test_run_stage_fails_friendly_when_openai_key_missing(db_session, monkeypatch):
    # OpenAIScript.validate가 참조하는 설정의 키를 비운다 → 실행 시 FAILED(친절 메시지), network 미접속
    monkeypatch.setattr(
        "app.providers.script.openai.get_settings",
        lambda: __import__("types").SimpleNamespace(openai_api_key=""),
    )
    actor, project, stage = await _seed_openai_stage(db_session)
    updated = await pipeline.run_stage(db_session, project, stage, actor_id=actor)
    assert updated["status"] == StageStatus.FAILED
    assert "OPENAI_API_KEY" in (updated["error"] or "")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_pipeline_validate.py -q`
Expected: FAIL — validate 미호출이라 `AsyncOpenAI()`가 빈 키로 생성되며 다른 예외가 나거나(네트워크/인증) 메시지에 `OPENAI_API_KEY`가 없어 assert 실패

- [ ] **Step 3: `run_stage`에 validate + 헬퍼 추가** — `app/core/pipeline.py`

`run_stage`의 provider 실행 블록을 아래로 교체(기존 `try:` 앞 `provider = ...`/`ctx = ...`는 그대로 두고, try 내부 첫 줄에 `validate` 추가):

```python
    try:
        provider.validate(ctx.settings)          # 키 누락 등 조기 실패 → FAILED로 흡수
        result = await provider.run(ctx)
        status, output, error = StageStatus.NEEDS_REVIEW, result.output, None
    except Exception as exc:  # provider 예외는 삼키지 않고 상태로 기록
        status, output, error = StageStatus.FAILED, {}, _error_message(exc)
```

파일 하단(또는 `run_stage` 위)에 헬퍼 추가:

```python
def _error_message(exc: Exception) -> str:
    """AppError면 친절한 message를, 아니면 문자열 표현을 반환한다."""
    return getattr(exc, "message", None) or str(exc)
```

> 기존 `except`가 `error = str(exc)`였다면 `_error_message(exc)`로 바꾼다. `AppError`는 `.message`를 가지므로 `OPENAI_API_KEY가 설정되지 않았습니다.`가 그대로 노출된다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_pipeline_validate.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: 기존 파이프라인 테스트 회귀 확인**

Run: `uv run pytest tests/test_pipeline_run_stage.py -q`
Expected: PASS (기존 4개 — FakeScript.validate는 no-op이라 영향 없음)

- [ ] **Step 6: 커밋**

```bash
git add app/core/pipeline.py tests/test_pipeline_validate.py
git commit -m "기능: run_stage가 provider.validate()로 키 누락을 친절한 실패로 처리"
```

---

### Task 6: create_project의 provider를 설정에서 읽기 + 테스트 기본값 fake

**Files:**
- Modify: `app/api/projects.py` (`create_project`, import)
- Modify: `tests/conftest.py` (테스트 기본 `SCRIPT_PROVIDER=fake`)
- Test: `tests/test_api_projects.py` (신규 테스트 1개 추가)

**Interfaces:**
- Consumes: `get_settings`
- Produces: `create_project`가 `provider=get_settings().script_provider`로 stage 생성. 테스트 환경은 `SCRIPT_PROVIDER=fake`로 강제되어 기존 API 통합 테스트가 network 없이 통과.

- [ ] **Step 1: conftest에 테스트 기본 provider 강제** — `tests/conftest.py` 파일 **맨 위**(다른 import보다 먼저)에 추가

```python
import os

os.environ["SCRIPT_PROVIDER"] = "fake"  # 통합 테스트는 실제 LLM 호출 없이 fake로

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()  # 위 env가 반영되도록 lru_cache 초기화
```

> 기존 conftest 상단의 다른 import들은 이 블록 아래에 그대로 둔다.

- [ ] **Step 2: 테스트 2개 작성** — `tests/test_api_projects.py` 끝에 추가

```python
async def test_create_uses_configured_provider(client, db_session):
    # conftest가 SCRIPT_PROVIDER=fake로 강제 → 생성된 script 단계 provider가 fake (가드)
    await _login(client, db_session, "provider-cfg@example.com")
    body = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    assert body["stages"][0]["provider"] == "fake"


async def test_create_uses_openai_when_configured(client, db_session, monkeypatch):
    # 설정이 openai면 생성된 단계 provider도 openai (create는 실행을 안 하므로 network 없음)
    monkeypatch.setattr(
        "app.api.projects.get_settings",
        lambda: __import__("types").SimpleNamespace(script_provider="openai"),
    )
    await _login(client, db_session, "provider-openai@example.com")
    body = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    assert body["stages"][0]["provider"] == "openai"
```

- [ ] **Step 3: 테스트 실패 확인 (진짜 RED)**

Run: `uv run pytest tests/test_api_projects.py::test_create_uses_openai_when_configured -q`
Expected: FAIL — `create_project`가 아직 `provider="fake"`를 하드코딩하므로 생성된 provider가 `fake`라 `== "openai"` assert 실패. (가드 테스트 `test_create_uses_configured_provider`는 이 시점에도 통과.) 또한 `monkeypatch`가 `app.api.projects.get_settings`를 대체하므로, 하드코딩을 설정 연동으로 바꾸기 전에는 이 대체가 무의미해 여전히 fake.

- [ ] **Step 4: create_project를 설정 연동으로 변경** — `app/api/projects.py`

import 추가(상단 import 블록):

```python
from app.config import get_settings
```

`create_project`의 `insert_stage` 호출에서 `provider="fake"`를 아래로 변경:

```python
        conn, project_id=project_id, name=StageName.SCRIPT, provider=get_settings().script_provider,
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_api_projects.py -q`
Expected: PASS (기존 6 + 신규 2 = 8 passed). Step 4로 `test_create_uses_openai_when_configured`가 RED→GREEN, 가드 테스트도 유지.

- [ ] **Step 7: 전체 스위트 회귀 확인**

Run: `uv run pytest -q`
Expected: 전체 PASS (기존 118 + 신규 provider/schema/registry/validate 테스트). network·과금 없음.

- [ ] **Step 8: 커밋**

```bash
git add app/api/projects.py tests/conftest.py tests/test_api_projects.py
git commit -m "기능: create_project가 SCRIPT_PROVIDER 설정으로 provider 선택(테스트는 fake 강제)"
```

---

## 최종 검증

- [ ] 전체 백엔드 테스트: `uv run pytest -q` → 전체 PASS (오프라인·무과금)
- [ ] (선택, 유료) 실제 호출 스모크: `.env`에 `OPENAI_API_KEY` 넣고 `SCRIPT_PROVIDER=openai`로 앱 기동 → 프로젝트 생성 → 실행 → 실제 gpt-4o-mini 대본이 `needs_review`로 뜨는지 확인. `claude`도 `ANTHROPIC_API_KEY`+`SCRIPT_PROVIDER=claude`로 동일 확인. (키 없으면 stage FAILED + 안내 메시지 확인)

## Self-Review 결과 (작성자 점검)

- **스펙 커버리지:** 설정·의존성(§3)→T1, 공유 스키마(§4)→T1, OpenAIScript(§5)→T2, ClaudeScript(§5)→T3, 레지스트리(§5)→T4, run_stage validate(§6)→T5, create_project 설정 연동·테스트 fake 강제(§6/§7)→T6, 에러 처리(§8)→T5(+각 validate). 누락 없음.
- **플레이스홀더:** 코드·명령·기대출력 구체화. SDK 경로 차이는 "확인 스텝(T2·T3 Step 3)"으로 명시적 처리(막연한 TODO 아님).
- **타입 일관성:** `ScriptDraft`/`ScriptScene`가 T1 정의와 T2·T3 사용에서 일치. `system_prompt`/`user_prompt` 시그니처 일치. `validate(settings)`·`run(ctx)->StageResult` 계약이 base와 일치. `_error_message(exc)`가 T5에서 정의·사용. `REGISTRY["script"]` 키 `{"fake","openai","claude"}`가 T4·T6 테스트와 일치.
- **알려진 확인 지점:** T2·T3의 구조화 출력 SDK 경로(설치 버전 확인 후 실제 호출+가짜 클라이언트 동일화). T1의 `uv add`는 네트워크 필요.
