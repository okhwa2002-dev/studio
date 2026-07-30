# 대본 수정 설계

- 작성일: 2026-07-30
- 범위: AI가 생성한 대본을 검토 중에 사람이 고치는 기능

## 1. 목적과 범위

지금 대본 단계에서 할 수 있는 일은 **승인**과 **재생성** 둘뿐이다. 단어 하나가 어색해도 전체를 다시 생성해야 하고, 재생성은 프롬프트에 "이전과 다른 각도로 다시 써줘"가 붙어([user_prompt](../../../app/providers/script/prompts.py)) 마음에 들었던 부분까지 통째로 바뀐다. 결과가 좋아질 보장도 없다.

검토 중(`NEEDS_REVIEW`)인 대본을 직접 고쳐 저장할 수 있게 한다.

**하는 것**

- 제목·훅 수정
- 장면별 나레이션·화면자막 수정
- 장면 추가·삭제·순서 변경
- 저장 후에도 검토 중 상태 유지 (그다음 승인은 기존 버튼으로)

**하지 않는 것**

- **승인 후 수정** — `APPROVED`는 종착 상태이고([ALLOWED_TRANSITIONS](../../../app/core/pipeline.py)) 되돌리려면 하위 단계(음성·자막·영상)와 산출물을 무효화하는 개념이 새로 필요하다. 파이프라인 상태 머신을 건드리는 별도 작업이다
- **AI 없이 처음부터 대본 작성** — 생성 후 다듬는 것이 이 기능이다
- **부분 재생성**("이 장면만 다시 써줘") — 프롬프트·컨텍스트 설계가 따로 필요하다
- **수정 이력·되돌리기** — 저장하면 이전 대본은 사라진다. 승인 전이라 언제든 재생성으로 새 대본을 받을 수 있다
- **"사람이 수정함" 표시** — 필드를 새로 만들 만한 값이 없다. 누가 언제 고쳤는지는 `stages.updated_by`·`updated_at`에 이미 남는다

## 2. 무엇이 실제로 하위 단계에 영향을 주는가

대본 필드 5개 중 **둘만** 뒤 단계가 읽는다. 검증 규칙과 UI 강조가 이 사실을 따라간다.

| 필드 | 읽는 곳 | 비었을 때 |
|---|---|---|
| `scenes[].narration` | **음성** — [narration_text](../../../app/providers/voice/text.py)가 순서대로 이어붙여 TTS에 넣는다 | 무음 mp3가 만들어진다 → **막아야 한다** |
| `scenes[].on_screen` | **영상** — [stock.py](../../../app/providers/render/stock.py)의 소재 검색어 | [queries_for](../../../app/providers/render/sources.py)가 topic → 기본 검색어로 폴백한다 → **비어도 안전** |
| `title` · `hook` | 없음 (화면 표시 전용) | 화면만 빈다 |
| `estimated_duration_sec` | 없음 (화면 표시 전용) | 3-4에서 서버가 유도한다 |

**장면 순서는 배열 순서가 결정한다.** `narration_text`가 `scenes` 배열을 그 순서로 이어붙이므로, `index` 값은 표시용일 뿐 실제 순서를 만들지 않는다. 이 사실이 3-3의 재매김 근거다.

## 3. API

### 3-1. 엔드포인트

| 메서드 | 경로 | 동작 |
|---|---|---|
| PUT | `/api/projects/{project_id}/stages/script` | 대본 내용을 교체한다. 응답은 `views.detail` |

**PATCH가 아니라 PUT인 이유:** 화면이 편집 가능한 대본 전체를 보낸다. 장면 삭제·순서 변경을 부분 갱신으로 표현하려면 어차피 전체 배열이 필요하고, 공지·FAQ 관리 모달도 같은 방침이다("항상 편집 가능한 전체를 보낸다").

**경로에 `script`를 리터럴로 박는 이유:** 편집할 수 있는 단계는 대본뿐이다. `/stages/{name}`으로 열어두면 음성·자막·영상도 편집 가능한 것처럼 읽힌다.

응답을 `views.detail`로 맞추는 것은 `run`·`approve`·`regenerate`와 같다 — 프론트가 한 번의 응답으로 화면 전체를 갱신한다.

### 3-2. 요청 모델

요청에는 **사용자가 실제로 통제하는 필드만** 담는다. `index`와 `estimated_duration_sec`는 서버가 유도하므로 받지 않는다.

```python
class SceneEdit(BaseModel):
    narration: str
    on_screen: str = ""

class ScriptEditRequest(BaseModel):
    title: str
    hook: str = ""
    scenes: list[SceneEdit]
```

**기존 `ScriptDraft`를 요청 모델로 재사용하지 않는다.** 그 모델은 `index`·`estimated_duration_sec`가 필수라, 서버가 정하기로 한 값을 클라이언트에 요구하게 된다. 대신 **저장 직전에 `ScriptDraft`로 조립·검증**한다(3-4) — 그래서 DB에 들어가는 모양은 AI가 생성한 것과 정확히 같고, 하위 단계가 두 경로를 구분할 필요가 없다.

`ScriptEditRequest`에 검증을 두고 `ScriptDraft`는 손대지 않는다. `ScriptDraft`에 상한을 넣으면 AI 생성 경로까지 그 규칙에 걸려(장면 25개를 낸 응답이 `FAILED`가 된다) 이 작업과 무관한 동작이 바뀐다.

### 3-3. 검증 규칙

| 규칙 | 값 | 이유 |
|---|---|---|
| 장면 개수 | 1 ~ 20 | 0개면 TTS가 빈 문자열을 읽는다. 상한은 60초 쇼츠에 한참 넉넉하며, TTS·렌더가 몇십 분짜리를 물지 않게 막는다 |
| `narration` | 공백 불가, 장면당 2000자 이하 | 이게 곧 음성이다 (2-절) |
| 나레이션 총합 | 5000자 이하 | 초당 5자로 약 17분. 쇼츠 기준 상한이 확실하다 |
| `on_screen` | **공백 허용**, 200자 이하 | topic으로 폴백한다 (2-절) |
| `title` | 공백 불가, 200자 이하 | 화면 제목으로 쓰인다 |
| `hook` | 공백 허용, 500자 이하 | 표시 전용이라 비어도 깨지지 않는다 |

모든 문자열은 앞뒤 공백을 다듬는다(`strip`). 위반은 FastAPI가 422로 응답하고, [validation_error_handler](../../../app/main.py)가 어느 항목이 왜 거부됐는지를 메시지에 담아준다.

### 3-4. 서버가 유도하는 값

`app/providers/script/schema.py`에 순수 함수로 둔다. HTTP 없이 테스트할 수 있어야 하고, "정상적인 대본 draft가 어떤 모양인가"는 스키마 모듈이 가질 만한 지식이다.

```python
# 한국어 TTS의 대략적인 낭독 속도. estimated_duration_sec는 표시 전용이므로
# 정밀할 필요가 없고, 사용자가 장면을 지웠을 때 값이 따라 줄기만 하면 된다.
CHARS_PER_SEC = 5.0

def build_draft(title: str, hook: str, scenes: list[tuple[str, str]]) -> ScriptDraft:
    """편집 요청을 정상형 ScriptDraft로 조립한다. index는 1..N, 길이는 글자수에서 유도."""
```

**`index`는 클라이언트 값을 무시하고 1..N으로 다시 매긴다.** 실제 순서를 정하는 것은 배열 순서이므로(2-절), 클라이언트가 보낸 번호를 믿으면 화면 번호와 실제 낭독 순서가 어긋날 수 있다. 순서 변경·삭제 후 번호가 비거나 중복되는 것도 이걸로 함께 막힌다.

**`estimated_duration_sec`는 나레이션 글자수에서 다시 계산한다.** 사용자가 4장면을 2장면으로 줄여도 AI가 낸 "45초"가 그대로 남으면 화면이 거짓말을 한다. 이 필드는 아무 단계도 읽지 않으므로(2-절) 값을 바꿔도 파이프라인에 영향이 없다. 최소 1초로 내림 방지한다.

**AI 생성 경로는 그대로 둔다** — provider가 낸 `estimated_duration_sec`를 재계산하지 않는다. 결과적으로 "생성만 한 대본"은 AI의 추정치를, "한 번이라도 저장한 대본"은 유도값을 보여주는 비대칭이 생긴다. 같은 텍스트에 두 숫자가 나올 수 있다는 뜻이지만, 표시 전용 값이고 AI의 추정이 우리 글자수 공식보다 못하다고 볼 근거도 없어서 생성 경로를 건드리지 않는다.

### 3-5. 상태 가드

소유자만(`_load_owned_project`), 그리고 **`NEEDS_REVIEW`일 때만** 수정할 수 있다.

상태 검사는 [approve_stage](../../../app/core/pipeline.py)·[regenerate_stage](../../../app/core/pipeline.py)와 같은 이유로 **DB의 CAS**로 한다. 요청 진입 시 읽은 `stage["status"]`는 낡을 수 있다 — 다른 탭에서 승인했거나, `auto_run`이 자동 승인하는 순간이거나, 저장 버튼 더블클릭이다. 상태 술어 없는 `UPDATE`를 쓰면 이미 승인돼 음성 생성이 시작된 대본을 덮어써 **음성과 대본이 어긋난다.**

```sql
-- name: update_stage_output_cas<!
UPDATE stages
SET output = :output::jsonb,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND status = :expected_status
RETURNING id;
```

0행이면 409 `STAGE_CONFLICT`, 메시지는 "수정할 수 없는 상태입니다." 코드를 기존과 같게 두는 것은 프론트가 이미 그 코드를 다루기 때문이다.

**`status`와 `attempt`는 바꾸지 않는다.** 수정은 상태 전이가 아니라 검토 중 내용 변경이고, 저장 후에도 여전히 승인 대기다. `attempt`는 AI 재생성의 변주 seed이므로([user_prompt](../../../app/providers/script/prompts.py)가 `attempt > 0`에 다른 각도를 요구한다) 사람이 고친 것과는 무관하다.

## 4. 프론트엔드

### 4-1. 편집기를 별도 파일로 분리

`web/src/pages/projects/ScriptEditor.tsx`를 새로 만든다.

[ProjectDetail.tsx](../../../web/src/pages/projects/ProjectDetail.tsx)는 이미 400줄이 넘고 단계별 뷰 4개 + 진행률 + 액션 + 삭제 확인까지 들고 있다. 장면 목록 편집(입력 여러 개, 추가·삭제·이동, 로컬 draft 상태)을 여기 더 넣으면 한 파일이 너무 많은 일을 한다. 편집기는 경계가 분명하다 — **대본 하나를 받아 수정된 대본을 돌려준다.**

```tsx
function ScriptEditor({ initial, saving, error, onSave, onCancel }: {
  initial: ScriptOutput
  saving: boolean
  error: string | null
  onSave: (payload: ScriptEditPayload) => void
  onCancel: () => void
})
```

서버를 직접 부르지 않는다 — 저장은 `onSave`로 부모에 넘긴다. `ProjectDetail`이 이미 API 호출과 `detail` 상태를 쥐고 있고, 편집기가 따로 부르면 응답으로 온 detail을 부모에 되돌릴 길이 필요해진다.

### 4-2. 화면

읽기 상태의 `ScriptView` 우측에 `[수정]` 버튼을 둔다. `status === 'NEEDS_REVIEW' && !readOnly`일 때만 보인다 — 관리자 열람에서 액션을 숨기는 기존 규칙과 같고, 서버도 그 조건에서만 허용한다.

```
┌─ 대본 (script)                          [검토 필요] ─┐
│  제목  [제주도 3박 4일 완전정복              ]        │
│  훅    [아직도 렌트카부터 알아보세요?        ]        │
│  ──────────────────────────────────────────────────  │
│  #1                                   ↑  ↓  삭제     │
│     나레이션 [                              ]        │
│     화면     [                              ]        │
│  #2                                   ↑  ↓  삭제     │
│     나레이션 [                              ]        │
│     화면     [                              ]        │
│                   [+ 장면 추가]                      │
│  ──────────────────────────────────────────────────  │
│  예상 길이 38초 (저장하면 다시 계산됩니다)           │
│                            [취소]  [저장]            │
└──────────────────────────────────────────────────────┘
```

- 나레이션은 `<textarea>`(여러 줄이 흔하다), 나머지는 `<input>`
- 첫 장면의 `↑`와 마지막 장면의 `↓`는 비활성
- 장면이 1개면 `삭제` 비활성 — 0개는 서버가 422로 막으므로 화면에서 먼저 알려준다
- 장면 20개에 도달하면 `+ 장면 추가` 비활성
- `#N`은 배열 순서로 그때그때 다시 그린다(서버 재매김과 같은 규칙이라 저장 전후 번호가 튀지 않는다)

편집기는 **로컬 draft 상태**를 들고 있다. SSE 이벤트가 도착해 부모의 `detail`이 갱신돼도 작성 중인 내용이 덮이지 않는다. 다른 탭에서 승인되면 `status`가 바뀌어 편집기 조건이 깨지고 편집기가 사라진다 — 저장 직전의 경합은 서버 409가 잡는다.

### 4-3. 클라이언트 검증

서버가 최종 강제하지만 즉각적인 피드백을 위해 저장 버튼을 잠근다. 기존 `ChangePasswordModal`이 쓰는 방식과 같다.

- 제목이 공백이거나 나레이션이 하나라도 공백이면 `[저장]` 비활성
- 해당 입력 아래에 `TextField`의 `error`로 이유를 표시

### 4-4. 저장·실패 처리

성공하면 응답의 detail로 화면을 갱신하고 편집 모드를 닫고, `useToast`로 "대본을 저장했습니다."를 띄운다.

실패하면 **편집 모드를 유지하고** 편집기 안에 `FormError`를 보여준다. 작성한 내용을 날리면 안 된다. 실제로 나올 수 있는 실패는 409(그 사이 승인됨)와 422(검증)다.

### 4-5. API 클라이언트

`web/src/lib/projects.ts`에 추가한다.

```ts
export type ScriptEditPayload = {
  title: string
  hook: string
  scenes: { narration: string; on_screen: string }[]
}

// projects 객체에:
saveScript: (id: number, payload: ScriptEditPayload) =>
  api.put<ProjectDetail>(`/projects/${id}/stages/script`, payload),
```

## 5. 에러 처리

**백엔드**

| 상황 | 응답 |
|---|---|
| 없는 프로젝트 · 남의 프로젝트 · 삭제된 프로젝트 · 관리자 | 404 `RESOURCE_NOT_FOUND` |
| script 단계가 없음 | 404 `RESOURCE_NOT_FOUND` |
| `NEEDS_REVIEW`가 아님 | 409 `STAGE_CONFLICT` |
| 검증 위반 | 422 `VALIDATION_ERROR` (어느 항목인지 메시지에 포함) |
| 비로그인 | 401 |

**프론트엔드**

| 상황 | 처리 |
|---|---|
| 저장 실패 | 편집기 안에 `FormError`, 편집 모드 유지 |
| 저장 성공 | 토스트 + 읽기 모드로 전환 |

## 6. 테스트

**백엔드**

`tests/test_script_edit_schema.py` (신규) — 순수 함수

- `build_draft`가 `index`를 1..N으로 매긴다 (입력 순서 그대로)
- `estimated_duration_sec`가 나레이션 글자수에서 계산된다
- 나레이션이 짧아도 최소 1초다
- 문자열 앞뒤 공백이 다듬어진다

`tests/test_api_script_edit.py` (신규) — API

- 저장이 200이고 응답 detail의 대본이 수정본이다
- **수정한 나레이션이 실제로 음성에 반영된다** — 대본을 고치고 승인한 뒤 음성 단계를 fake provider로 돌려 TTS에 들어간 텍스트가 수정본과 일치하는지 확인한다. 이 기능이 실제로 뜻이 있는지를 보는 유일한 테스트다
- 저장 후에도 `status`가 `NEEDS_REVIEW`이고 `attempt`가 그대로다
- 장면 삭제가 반영된다 (개수·순서)
- 장면 추가가 반영된다
- 순서를 바꿔 보내면 그 순서로 저장되고 `index`가 다시 매겨진다
- `on_screen`이 비어도 200이다
- 장면 0개는 422
- 공백 나레이션은 422
- 장면 21개는 422
- 나레이션 총 5001자는 422
- 공백 제목은 422
- `PENDING`·`RUNNING`·`APPROVED`·`FAILED` 상태는 409이고 output이 그대로다
- script 단계가 없는 프로젝트는 404
- 남의 프로젝트는 404이고 그 대본은 그대로다
- 관리자도 404다
- 비로그인은 401

**프론트엔드**는 자동화 테스트가 없다. 수동 확인 항목만 남긴다.

- 검토 중 대본에 `[수정]`이 보이고, 누르면 편집기가 열린다
- 제목·훅·나레이션·화면자막을 고쳐 저장하면 읽기 화면에 반영된다
- 장면을 추가·삭제하면 번호가 1부터 다시 매겨진다
- 첫 장면의 `↑`, 마지막 장면의 `↓`가 비활성이다
- 장면이 1개면 `삭제`가 비활성이다
- 나레이션을 비우면 `[저장]`이 잠긴다
- `[취소]`를 누르면 고친 내용이 버려지고 읽기 화면으로 돌아간다
- 저장 후 승인 → 음성이 수정된 대본을 읽는다
- 관리자 열람에는 `[수정]`이 없다
- 다크모드에서 입력칸·버튼이 깨지지 않는다

## 7. 구현 순서

1. `build_draft` + `CHARS_PER_SEC` (schema.py) + 순수 함수 테스트
2. `update_stage_output_cas` 쿼리
3. `ScriptEditRequest` + PUT 엔드포인트 + API 테스트
4. 프론트 타입·API 클라이언트
5. `ScriptEditor.tsx`
6. `ProjectDetail`에 `[수정]` 버튼과 편집 모드 연결

1번을 먼저 하는 이유: `index` 재매김과 길이 계산이 이 기능의 유일한 비자명한 로직이고, HTTP 없이 검증할 수 있다. 엔드포인트는 그 함수를 부르는 껍데기가 된다.
