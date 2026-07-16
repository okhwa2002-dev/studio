# 실제 script provider (OpenAI + Claude) — 설계 문서 (Design Spec)

- **작성일:** 2026-07-16
- **프로젝트명:** studio
- **한 줄 요약:** 파이프라인 첫 슬라이스의 `fake` script provider 옆에, 실제 대본을 생성하는 **OpenAI(ChatGPT)와 Claude(Anthropic) provider 두 개**를 추가한다. 기본은 설정으로 고르며(기본값 openai/gpt-4o-mini), 산출물 스키마·core·API·프론트는 그대로 둔다.

---

## 1. 목표 & 범위

### 목표
직전 슬라이스에서 만든 3계층(providers/core/api)의 **provider 교체 seam**을 처음으로 실전 검증한다. `fake`를 실제 LLM 대본 생성으로 바꾸되, **레지스트리에 클래스만 추가**하고 core·API·프론트는 손대지 않는다. 이번에 처음 도입되는 것:
- 외부 LLM SDK 호출 (`openai`, `anthropic`)
- **구조화 출력**으로 기존 대본 JSON 스키마 강제
- `Provider.validate()` (실행 전 API 키 확인 → 친절한 실패)
- 설정 기반 기본 provider 선택

### 확정된 범위
| 항목 | 결정 |
|------|------|
| provider | **openai + claude 둘 다** 레지스트리에 추가 (`fake` 유지) |
| 기본 provider | 설정 `SCRIPT_PROVIDER` (기본 `openai`) |
| OpenAI 모델 | **gpt-4o-mini** (저비용) |
| Claude 모델 | **claude-haiku-4-5** (저비용) |
| SDK | 공식 `openai`(`AsyncOpenAI`) / `anthropic`(`AsyncAnthropic`), 구조화 출력 |
| 대본 스키마 | **기존 그대로** `{title, hook, scenes[{index,narration,on_screen}], estimated_duration_sec}` |
| 키 누락 처리 | 실행 시 `validate()` 예외 → stage `FAILED` + 친절한 메시지 (앱은 안 죽음) |
| 실행 방식 | **동기** (직전 슬라이스와 동일, 워커 없음) |
| 테스트 | 파이프라인·API 통합은 `fake`로 오버라이드(무과금), 두 실제 provider는 **가짜 클라이언트 주입** 단위 테스트 |

### 비범위 (그대로 미룸)
- 워커(procrastinate)·SSE — 실행은 여전히 동기
- voice / captions / render 단계, Asset 테이블, storage
- **프로젝트별 provider 선택 UI** — 이번엔 설정(config)로만 전환. 화면 드롭다운은 다음 슬라이스.
- 모델 ID를 설정으로 노출 — 이번엔 각 provider 모듈 상수로 고정(향후 config 승격 가능)

---

## 2. 아키텍처 — 변경 지점

```
[create_project] ──provider = settings.SCRIPT_PROVIDER──▶ Stage.provider 저장
        │
[run_stage] ──validate()──▶ (키 없으면 FAILED) ──▶ get_provider("script", <name>)
        │                                                  │
        ▼                                                  ▼
   REGISTRY["script"] = {                        [FakeScript] | [OpenAIScript] | [ClaudeScript]
      "fake":   FakeScript,                              │
      "openai": OpenAIScript,   ← 신규                    ▼
      "claude": ClaudeScript,   ← 신규            구조화 출력 → ScriptDraft(Pydantic) → dict
   }                                                     │
                                                         ▼
                                              Stage.output(JSONB)  (스키마 동일)
```

- **core/API/프론트 무변경**: 상태 머신·오케스트레이션·라우트·화면은 provider가 몇 개든 동일. 유일한 변경은 (a) 레지스트리 항목 2줄, (b) `create_project`의 provider 값 출처(하드코딩 → 설정), (c) `run_stage`에 `validate()` 호출 1줄.
- 두 실제 provider는 같은 `Provider` 계약(`run`/`validate`)과 **같은 산출 스키마**를 공유 → 서로, 그리고 fake와 완전 교체 가능.

---

## 3. 설정 · 의존성

### `pyproject.toml`
`dependencies`에 추가:
```toml
"openai>=1.0",
"anthropic>=0.40",
```
(정확한 하한 버전은 구현 시 설치된 버전으로 확정)

### `app/config.py` — `Settings` 추가 필드
```python
openai_api_key: str = ""
anthropic_api_key: str = ""
script_provider: str = "openai"   # openai | claude | fake
```

### `.env.example` 추가
```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
SCRIPT_PROVIDER=openai
```
- 실제 키가 든 `.env`는 git 미포함(기존 규칙). 두 키 모두 **없어도 앱은 기동**되며, 해당 provider 실행 시에만 실패한다.

---

## 4. 공유 스키마 (`app/providers/script/schema.py`)

두 실제 provider가 구조화 출력에 쓰는 Pydantic 모델. **기존 대본 dict와 1:1**.

```python
from pydantic import BaseModel


class ScriptScene(BaseModel):
    index: int
    narration: str   # voice가 읽을 나레이션
    on_screen: str   # 화면 자막/키워드


class ScriptDraft(BaseModel):
    title: str
    hook: str
    scenes: list[ScriptScene]
    estimated_duration_sec: int
```
- `ScriptDraft(...).model_dump()` → `Stage.output`에 저장되는 dict (fake 출력과 동일한 키 구성).
- 구조화 출력 제약(모든 필드 required, 추가 속성 불가)을 자연히 만족.

---

## 5. Provider 구현

두 provider 모두 `app/providers/base.py`의 `Provider`/`StageContext`/`StageResult` 계약을 따르고, **클라이언트를 생성자 주입**할 수 있게 하여 network 없이 단위 테스트한다.

### 공통 프롬프트 규칙
- **시스템**: "주어진 주제로 한국어 숏폼(쇼츠) 영상 대본을 만든다. 3초 훅으로 시작, 장면 3개 내외, 각 장면에 narration과 on_screen을 채운다."
- **유저**: 주제(`ctx.topic`). 재생성 시(`ctx.attempt > 0`) "이전과 다른 새로운 각도로 다시 작성" 힌트 추가 → UI에서 재생성 시 결과가 달라짐.

### `app/providers/script/openai.py` — `OpenAIScript`
```python
from openai import AsyncOpenAI      # 절대 import: 설치된 openai 패키지(이 파일 자신이 아님)

from app.config import get_settings
from app.providers.base import Provider, StageContext, StageResult
from app.providers.script.schema import ScriptDraft
from app.utils.errors import AppError

_MODEL = "gpt-4o-mini"


class OpenAIScript(Provider):
    stage = "script"
    name = "openai"

    def __init__(self, client: "AsyncOpenAI | None" = None):
        self._client = client

    def validate(self, settings: dict) -> None:
        if not get_settings().openai_api_key:
            raise AppError(400, "OPENAI_API_KEY_MISSING", "OPENAI_API_KEY가 설정되지 않았습니다.")

    def _get_client(self) -> "AsyncOpenAI":
        if self._client is None:
            self._client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        return self._client

    async def run(self, ctx: StageContext) -> StageResult:
        client = self._get_client()
        # 구조화 출력: response_format=ScriptDraft (정확한 호출은 구현 시 SDK 문서로 확인)
        completion = await client.beta.chat.completions.parse(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(ctx.topic, ctx.attempt)},
            ],
            response_format=ScriptDraft,
        )
        draft = completion.choices[0].message.parsed
        return StageResult(output=draft.model_dump())
```

### `app/providers/script/claude.py` — `ClaudeScript`
```python
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.providers.base import Provider, StageContext, StageResult
from app.providers.script.schema import ScriptDraft
from app.utils.errors import AppError

_MODEL = "claude-haiku-4-5"


class ClaudeScript(Provider):
    stage = "script"
    name = "claude"

    def __init__(self, client: "AsyncAnthropic | None" = None):
        self._client = client

    def validate(self, settings: dict) -> None:
        if not get_settings().anthropic_api_key:
            raise AppError(400, "ANTHROPIC_API_KEY_MISSING", "ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    def _get_client(self) -> "AsyncAnthropic":
        if self._client is None:
            self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    async def run(self, ctx: StageContext) -> StageResult:
        client = self._get_client()
        # 구조화 출력: messages.parse(output_format=ScriptDraft) → .parsed_output
        message = await client.messages.parse(
            model=_MODEL,
            max_tokens=2048,
            system=_system_prompt(),
            messages=[{"role": "user", "content": _user_prompt(ctx.topic, ctx.attempt)}],
            output_format=ScriptDraft,
        )
        draft = message.parsed_output
        return StageResult(output=draft.model_dump())
```

> **구현 주의(정확도):** 두 SDK의 구조화 출력 정확한 메서드·필드는 구현 단계에서 각 공식 문서/스킬로 검증한다. OpenAI는 `claude-api` 스킬 범위 밖이므로 `openai` 문서를 확인; Claude는 `claude-api` 스킬(`messages.parse(..., output_format=...) → .parsed_output`)을 따른다. 모델 ID(`gpt-4o-mini`, `claude-haiku-4-5`)도 구현 시 확인한다.

### 레지스트리 (`app/providers/base.py`)
```python
from app.providers.script.claude import ClaudeScript   # noqa: E402
from app.providers.script.fake import FakeScript        # noqa: E402
from app.providers.script.openai import OpenAIScript    # noqa: E402

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript, "openai": OpenAIScript, "claude": ClaudeScript},
}
```
- `get_provider`는 기존과 동일(없는 이름 → `AppError`).

---

## 6. 오케스트레이션 · API 변경 (최소)

### `app/core/pipeline.py` — `run_stage`에 `validate()` 추가
`provider.run(ctx)` **직전에** `provider.validate(project.settings)` 호출. 예외는 기존 try/except가 잡아 stage `FAILED` + `error`로 기록한다.
```python
provider = get_provider(stage["name"], stage["provider"])
ctx = StageContext(topic=project["topic"], settings=project.get("settings", {}),
                   inputs={}, attempt=stage["attempt"])
try:
    provider.validate(ctx.settings)        # ← 추가: 키 누락 등 조기 실패
    result = await provider.run(ctx)
    status, output, error = StageStatus.NEEDS_REVIEW, result.output, None
except Exception as exc:
    status, output, error = StageStatus.FAILED, {}, _error_message(exc)
```
- `_error_message(exc)`: `AppError`면 `exc.message`, 아니면 `str(exc)`. (친절한 한글 메시지가 그대로 UI에 노출)

### `app/api/projects.py` — `create_project`의 provider 출처
```python
# 기존: provider="fake" 하드코딩
provider=get_settings().script_provider,   # openai(기본) | claude | fake
```
- 나머지 라우트·응답은 무변경.

---

## 7. 테스트 전략

| 파일 | 대상 |
|---|---|
| `tests/test_provider_script_openai.py` | 가짜 `AsyncOpenAI` 주입 → 프롬프트 구성·응답을 `ScriptDraft`로 매핑·`model_dump()` 출력 스키마; `validate()`가 키 없을 때 `AppError` |
| `tests/test_provider_script_claude.py` | 가짜 `AsyncAnthropic` 주입 → 동일 검증 |
| 기존 `tests/test_pipeline_run_stage.py`, `tests/test_api_projects.py` | **fake로 강제**하여 network·과금 없이 유지 |

- **fake 강제 방법:** 테스트 환경에서 `SCRIPT_PROVIDER=fake`로 설정(`tests/conftest.py`에서 `os.environ` 지정 + `get_settings.cache_clear()`), 그리고 `run_stage` 검증이 `FakeScript.validate`(no-op)를 통과하므로 기존 흐름 그대로 통과.
- 실제 provider 단위 테스트는 **network 미접속**: 클라이언트를 주입하고, 그 가짜가 `ScriptDraft`에 해당하는 파싱 결과를 돌려주도록 스텁. 실제 OpenAI/Anthropic 호출은 하지 않는다(무과금).
- 목표: 전체 스위트가 여전히 무과금·오프라인으로 통과(기존 118 + 신규 provider 단위 테스트).

---

## 8. 에러 처리

- **키 누락**: `validate()` → `AppError(400, "*_API_KEY_MISSING", "…가 설정되지 않았습니다.")` → stage `FAILED` + 메시지. 사용자는 키 넣고 재실행.
- **외부 API 오류**(rate limit·5xx·network): 각 SDK의 내장 재시도(429/5xx, 지수 백오프) 후에도 실패하면 예외 → `FAILED` + 메시지. (별도 `utils/retry`는 도입하지 않음 — SDK 내장으로 충분)
- **구조화 출력 파싱 실패/거부**: 예외 → `FAILED`. 사용자는 재생성.
- 앱은 어떤 경우에도 죽지 않음(단계 상태로 흡수).

---

## 9. 남기는 seam (다음 단계)

| 미래 작업 | 준비된 것 |
|---|---|
| 프로젝트별 provider 선택 UI | provider는 이미 복수 등록됨 → 화면 드롭다운 + `project.settings.provider` 읽기만 추가 |
| 모델 ID 설정화 | 각 provider의 `_MODEL` 상수를 config로 승격(1줄) |
| voice/captions/render | 같은 방식으로 단계별 provider 추가 |
| 워커·SSE(비동기) | `run_stage`는 그대로, run 엔드포인트만 enqueue로 |
