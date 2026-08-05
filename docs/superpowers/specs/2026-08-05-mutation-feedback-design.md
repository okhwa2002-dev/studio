# 저장·삭제·수정 결과 알림 설계 (Design Spec)

- **작성일:** 2026-08-05
- **한 줄 요약:** 화면마다 제각각인 변경 결과 알림을 하나의 규칙으로 모은다 — **성공은 토스트, 실패는 그 자리에**. 변경 지점 16곳에 복붙돼 있는 `pending` state · `try/catch` · `e instanceof ApiError ? e.message : UNKNOWN` 세 벌을 `useSubmit` 훅 하나가 대신한다.

---

## 1. 배경 & 목표

### 문제

변경이 끝났을 때 무슨 일이 일어나는지가 화면마다 다르다.

| 화면 | 동작 | 성공 시 | 실패 시 |
|------|------|---------|---------|
| [`AdminNotices.tsx`](../../../web/src/pages/admin/AdminNotices.tsx) | 저장 · 삭제 | **아무 말 없이** 모달만 닫힘 | 모달 안 `FormError` |
| [`AdminFaqs.tsx`](../../../web/src/pages/admin/AdminFaqs.tsx) | 저장 · 삭제 | **아무 말 없이** 모달만 닫힘 | 모달 안 `FormError` |
| [`AdminSystem.tsx`](../../../web/src/pages/admin/AdminSystem.tsx) | 설정 저장 | 초록 배너 (`saved` state) | 페이지 상단 `FormError` |
| [`AdminUsers.tsx`](../../../web/src/pages/admin/AdminUsers.tsx) | 승인 · 거절 · 잠금 해제 | `toast.success` | `toast.error` |
| [`ProjectDetail.tsx`](../../../web/src/pages/projects/ProjectDetail.tsx) | 프로젝트 삭제 | `toast.success` | 확인창 안 인라인 |
| [`NewProjectModal.tsx`](../../../web/src/pages/projects/NewProjectModal.tsx) | 생성 | **아무 말 없이** 모달만 닫힘 | 폼 안 `FormError` |
| [`Settings.tsx`](../../../web/src/pages/Settings.tsx) | 비밀번호 변경 | 초록 배너 (`changed` state) | 폼 안 `FormError` |

성공 방식이 셋(없음 · 배너 · 토스트), 실패 방식이 둘로 갈렸다. 공지를 저장하면 모달이 그냥 사라지는데, 저장된 것인지 취소된 것인지 화면이 말해 주지 않는다.

토스트 인프라([`lib/toast.tsx`](../../../web/src/lib/toast.tsx))는 이미 있고 `ToastProvider`도 [`App.tsx`](../../../web/src/App.tsx)에 붙어 있다. 두 곳만 쓰고 있을 뿐이다. **새로 만들 것이 아니라 규칙을 정하고 나머지를 끌어오는 일이다.**

그 아래에 중복이 한 겹 더 있다.

- `const UNKNOWN = '알 수 없는 오류가 발생했습니다.'` — 페이지 파일 **15곳**에 각각 선언돼 있다. 같은 문자열이 [`lib/api.ts:15`](../../../web/src/lib/api.ts)에 `UNKNOWN_MESSAGE`로 이미 있지만 export되지 않는다.
- `e instanceof ApiError ? e.message : UNKNOWN` — **19개 파일에 32회**.
- 그 옆에는 늘 `pending` / `submitting` / `saving` / `resetting` state와 `try/catch/finally`가 따라온다.

### 목표

변경 동작 하나를 쓸 때 개발자가 적는 것이 **"무엇을 하고, 성공하면 뭐라고 말하고, 그 다음 뭘 할지"** 세 가지뿐이게 한다. 나머지(로딩 잠금 · 오류 문자열화 · 표시 위치 · 중복 제출 차단)는 훅이 정한다.

### 이번 범위

`errorMessage()` 추출 · `useSubmit` 훅 신설 · 변경 지점 전체(16개 동작) 적용 · `AdminSystem` 초록 배너 제거.

### 결정 사항

| 항목 | 결정 | 이유 |
|------|------|------|
| 성공 표시 | 토스트 | 결과를 확인시키되 화면을 밀어내지 않는다. 이미 있는 인프라다 |
| 실패 표시 | **상황별** — 폼이 열려 있으면 그 안, 폼이 없으면 토스트 | [`AdminNotices.tsx:237`](../../../web/src/pages/admin/AdminNotices.tsx)의 기존 판단을 규칙으로 승격한 것이다. "제목이 비었다"·"기간이 어긋난다" 같은 오류는 대부분 **입력을 고쳐야 하는** 오류라, 고칠 대상 옆에 붙어 있어야 하고 3.5초 뒤 사라지면 안 된다. 반대로 목록에서 바로 누르는 승인·잠금 해제는 고칠 폼이 없어 붙일 자리가 없다 |
| 성공 토스트 범위 | **화면이 결과를 스스로 말하지 않는 경우만** | 단계를 실행하면 배지가 즉시 `RUNNING`으로 바뀐다. 여기에 토스트를 겹치면 화면이 이미 한 말을 반복하는 것이고, 단계를 연속 실행하면 토스트가 쌓인다. 토스트가 흔해지면 읽히지 않는다 |
| 공통화 수단 | `useSubmit` 훅 | `errorMessage()` 헬퍼만 빼는 안은 변경량이 가장 작지만 `pending`·`try/catch`·토스트 호출이 그대로 남아 다음 화면에서 또 빠뜨릴 수 있다. API 레이어(`lib/*.ts`)에서 자동으로 띄우는 안은 데이터 모듈이 React 컨텍스트에 의존하게 되고, 조용히 저장해야 할 때 빠져나갈 구멍을 다시 만들어야 한다 |
| 성공 문구 | **호출부가 직접 적는다** | 훅이 "저장했습니다"를 추측하지 않는다. 같은 저장 버튼이라도 임시저장과 게시는 사용자에게 다른 사건이다 |

### 비범위 (YAGNI)

- **확인창 통일** — 삭제 확인이 `window.confirm`(공지 · FAQ · 비밀번호 초기화)과 `ConfirmDialog`(공지 게시 · 사용자 · 프로젝트)로 갈려 있다. 실제 결함이지만 "확인창" 주제이지 "결과 알림" 주제가 아니다. 별건으로 남긴다.
- **토스트에 실행 취소(undo)** — 삭제 토스트에 되돌리기를 붙이지 않는다. 서버에 취소 API가 없다.
- **토스트 큐 길이 제한 · 중복 합치기** — 성공 토스트를 "화면이 못 말하는 경우"로 좁혔으므로 쌓일 일이 거의 없다. 실제로 쌓이는 걸 본 뒤에 정한다.
- **목록 로딩(`load()`) 실패** — 변경이 아니므로 훅 대상이 아니다. `errorMessage()`만 공유한다.
- **`PasswordResetModal`의 성공 메시지** — 3단계 재설정이 끝나면 `onDone(msg)`로 로그인 화면에 안내를 넘긴다. 이 문구("새 비밀번호로 로그인하세요")는 사용자가 비밀번호를 입력하는 **동안 계속 보여야** 쓸모가 있어 3.5초 뒤 사라지는 토스트로 옮기면 오히려 나빠진다. 현행 유지하고 `errorMessage()`만 적용한다.

---

## 2. 설계

### 2.1 `errorMessage()` — 오류를 문장으로 바꾸는 한 곳

[`lib/api.ts`](../../../web/src/lib/api.ts)에 추가한다. `ApiError`와 `UNKNOWN_MESSAGE`가 이미 이 파일에 있으므로 새 파일을 만들 이유가 없다.

```ts
export const UNKNOWN_MESSAGE = '알 수 없는 오류가 발생했습니다.'   // 이미 있다. export만 추가한다

export const errorMessage = (e: unknown): string =>
  e instanceof ApiError ? e.message : UNKNOWN_MESSAGE
```

`useSubmit`이 내부에서 쓰고, 변경이 아닌 **목록 로딩** 실패(`load()`들의 `.catch`)도 직접 쓴다. 이것만으로 15개의 `const UNKNOWN` 선언과 32번의 삼항 연산이 사라진다.

`UNKNOWN_MESSAGE`도 함께 export하는 이유는 [`ProjectDetail.tsx:407`](../../../web/src/pages/projects/ProjectDetail.tsx)의 `<FormError message={error ?? UNKNOWN} />` 때문이다. 이건 오류 객체를 문장으로 바꾸는 자리가 아니라 **메시지가 아예 없을 때의 맨 fallback**이라 `errorMessage()`로 덮이지 않는다. 그런 자리는 상수를 직접 import한다.

### 2.2 `useSubmit` — 변경 동작 하나를 통째로 감싼다

새 파일 `web/src/lib/useSubmit.ts`. 파일명은 [`components/table/useClientPagination.ts`](../../../web/src/components/table/useClientPagination.ts)와 같은 `use*` 관례를 따른다. `lib/`에 두는 이유는 특정 표·폼에 매이지 않고 어느 화면에서나 쓰기 때문이다(같은 위치의 `auth.tsx` · `toast.tsx`가 훅을 export하는 것과 같다).

```
useSubmit() → { pending, error, run, clearError }

run<T>(fn: () => Promise<T>, options?: {
  success?: string               // 없으면 성공 토스트를 띄우지 않는다
  errorAs?: 'inline' | 'toast'   // 기본 'inline'
  onDone?: (result: T) => void   // 성공 후: 모달 닫기 · 목록 새로고침 · 이동
}) → Promise<void>
```

**동작 순서**

| 시점 | 하는 일 |
|------|---------|
| 시작 | 이미 진행 중이면 **아무것도 하지 않고 반환**. 아니면 `pending = true`, 직전 `error`를 지운다 |
| 성공 | `pending = false` → `success`가 있으면 `toast.success` → `onDone(result)` |
| 실패 | `pending = false` → `errorAs === 'toast'`면 `toast.error(errorMessage(e))`, 아니면 `error` state에 담는다 |

**규칙 1 — 성공 시 `pending`을 `onDone`보다 먼저 내린다.** `onDone`은 모달을 닫거나 다른 화면으로 보내는 일을 한다. 순서가 반대면 이미 사라진 컴포넌트에 `setState`하게 된다.

**규칙 2 — 언마운트 뒤의 `setState`는 건너뛴다.** 규칙 1로도 부족한 경우가 실제로 있다. [`AdminNotices.tsx:304`](../../../web/src/pages/admin/AdminNotices.tsx)의 `save()`는 **자기 안에서** `setEditing(null)`을 부르므로, 모달이 `await onSave(...)`에서 돌아온 시점에는 이미 언마운트돼 있다. `ProjectDetail`의 삭제도 `navigate` 때문에 같다. 그래서 훅은 `alive` ref로 마운트 여부를 추적하고 **`setState`만** 가드한다 — 토스트는 컴포넌트가 사라져도 떠야 하므로(삭제하고 목록으로 돌아간 화면에서 "삭제했습니다"가 보여야 한다) 가드 밖이다. [`AdminSystem.tsx:116`](../../../web/src/pages/admin/AdminSystem.tsx)의 `let alive = true` 관용구와 같은 방식이다.

**규칙 3 — 진행 중 재호출은 무시한다.** 판정은 state가 아니라 ref로 한다. state로 보면 같은 렌더의 클로저가 옛 값을 들고 있어 두 번 통과할 수 있다. 버튼 `disabled`는 그대로 두되(눌리지 않는 게 보여야 한다), 마지막 방어선을 훅이 갖는다.

**규칙 4 — `error`는 `errorAs: 'inline'`일 때만 채워진다.** 토스트로 보낸 오류가 화면 어딘가에 함께 남는 일이 없다.

`clearError`는 호출부가 오류를 수동으로 지울 때 쓴다([`ProjectDetail.tsx:248`](../../../web/src/pages/projects/ProjectDetail.tsx)이 편집기를 다시 열 때 `setSaveError(null)`을 하는 자리).

### 2.3 호출부가 어떻게 줄어드는가

[`AdminNotices.tsx:117-147`](../../../web/src/pages/admin/AdminNotices.tsx)의 30줄이 이렇게 된다.

```ts
const { pending, error, run } = useSubmit()

const submit = (status: NoticePayload['status']) =>
  run(() => onSave({ title, body, status, pinned_yn: toYn(pinned), ... }), {
    success: status === 'DRAFT' ? '공지를 임시저장했습니다.' : '공지를 게시했습니다.',
  })

const remove = () => {
  if (!window.confirm('이 공지를 삭제할까요?')) return
  run(() => onDelete(), { success: '공지를 삭제했습니다.' })
}
```

렌더 부분은 `pending`과 `error`를 그대로 쓰므로 바뀌지 않는다. `useState` 두 줄, `try/catch` 두 벌, `UNKNOWN` 선언이 사라진다.

---

## 3. 화면별 변경

| 화면 | 동작 | `success` | `errorAs` | 실패가 뜨는 곳 |
|------|------|-----------|-----------|----------------|
| [`AdminNotices.tsx`](../../../web/src/pages/admin/AdminNotices.tsx) | 임시저장 | `공지를 임시저장했습니다.` | inline | 폼 안 |
| | 게시 | `공지를 게시했습니다.` | inline | 폼 안 |
| | 삭제 | `공지를 삭제했습니다.` | inline | 폼 안 |
| [`AdminFaqs.tsx`](../../../web/src/pages/admin/AdminFaqs.tsx) | 임시저장 | `FAQ를 임시저장했습니다.` | inline | 폼 안 |
| | 게시 | `FAQ를 게시했습니다.` | inline | 폼 안 |
| | 삭제 | `FAQ를 삭제했습니다.` | inline | 폼 안 |
| [`AdminSystem.tsx`](../../../web/src/pages/admin/AdminSystem.tsx) | 설정 저장 | `시스템 설정을 저장했습니다.` | inline | 페이지 상단 |
| [`AdminUsers.tsx`](../../../web/src/pages/admin/AdminUsers.tsx) | 승인 · 거절 · 잠금 해제 | `ACTION_CONFIRM[action].success` | **toast** | — (폼이 없다) |
| | 실패 횟수 초기화 | `로그인 실패 횟수를 초기화했습니다.` | inline | 상세 모달 안 |
| | 비밀번호 초기화 | **없음** | inline | 상세 모달 안 |
| [`ProjectDetail.tsx`](../../../web/src/pages/projects/ProjectDetail.tsx) | 실행 · 승인 · 재생성 (`act`) | **없음** | inline | 페이지 상단 |
| | 대본 저장 | `대본을 저장했습니다.` | inline | 편집기 안 |
| | 프로젝트 삭제 | `프로젝트를 삭제했습니다.` | inline | 확인 대화상자 안 |
| [`NewProjectModal.tsx`](../../../web/src/pages/projects/NewProjectModal.tsx) | 생성 | `프로젝트를 만들었습니다.` | inline | 폼 안 |
| [`Settings.tsx`](../../../web/src/pages/Settings.tsx) | 비밀번호 변경 | `비밀번호를 변경했습니다. 다른 기기는 다시 로그인해야 합니다.` | inline | 폼 안 |
| [`ChangePasswordRequired.tsx`](../../../web/src/pages/ChangePasswordRequired.tsx) | 비밀번호 변경 | `비밀번호를 변경했습니다.` | inline | 폼 안 |

### 판단이 갈릴 만한 네 줄

- **실행 · 승인 · 재생성 — 토스트 없음.** 누르는 즉시 단계 배지가 `RUNNING`으로 바뀌고 진행률이 흐른다. 결과는 SSE로 계속 들어온다. 화면이 이미 충분히 말한다.
- **실행 · 승인 · 재생성의 실패 — "폼이 없으면 토스트"인데 인라인이다.** 목록에서 바로 누르는 승인·잠금 해제와 달리, 이 실패는 읽고 조치해야 하는 내용이다(실행 거절 사유, 예: 이미 실행 중이라 409). 3.5초 뒤 사라지면 안 된다. 그리고 실패한 단계 카드가 페이지 안 바로 아래 있으므로, 페이지 상단이 곧 그 조치 지점이다.
- **비밀번호 초기화 — 토스트 없음.** 발급된 임시 비밀번호가 모달에 그대로 표시된다([`AdminUsers.tsx:183`](../../../web/src/pages/admin/AdminUsers.tsx)의 `TempPassword`). 이보다 분명한 성공 신호가 없다.
- **실패 횟수 초기화 — 토스트 있음.** 숫자가 0이 되고 버튼이 사라지는 게 전부라 너무 조용하다. 잠김 해제까지 함께 일어나는데 그 사실이 화면에 드러나지 않는다.
- **프로젝트 생성 — 토스트 있음.** 주석대로 목록에 머문 채 새로고침만 한다. 새 행이 생기긴 하지만 목록이 길면 어디에 생겼는지 보이지 않는다.

### 함께 사라지는 것

- `const UNKNOWN` 선언 15개, `e instanceof ApiError ? ... : ...` 32회.
- `pending` · `submitting` · `saving` · `savingScript` · `resetting` · `resettingPassword` · `deleting` state와 각각의 `try/catch/finally`.
- [`AdminSystem.tsx:112`](../../../web/src/pages/admin/AdminSystem.tsx)의 `saved` state와 [`165-169`](../../../web/src/pages/admin/AdminSystem.tsx)의 초록 배너, 그리고 `set()`([`137`](../../../web/src/pages/admin/AdminSystem.tsx))·되돌리기 버튼([`353`](../../../web/src/pages/admin/AdminSystem.tsx))의 `setSaved(false)` 두 곳.
- [`Settings.tsx:132`](../../../web/src/pages/Settings.tsx)의 `changed` state와 [`136-140`](../../../web/src/pages/Settings.tsx)의 초록 배너. 배너 문구가 담고 있던 "다른 기기는 다시 로그인해야 합니다"는 **토스트 문구에 그대로 옮긴다** — 사라지면 안 되는 정보다. 모달의 `onChanged` prop도 함께 없어진다(성공을 부모에게 알릴 이유가 사라진다).

### 주의할 자리 두 곳

- **`AdminSystem`의 `error` state는 둘로 나뉜다.** 지금은 초기 로딩 실패와 저장 실패가 같은 state를 쓰고, [`133`](../../../web/src/pages/admin/AdminSystem.tsx)행의 `if (error && !draft)`가 그 둘을 `draft` 유무로 구분한다. 저장 실패는 훅의 `error`로 옮기고, 로딩 실패만 기존 state에 남긴다. 둘 다 렌더한다.
- **`AdminUsers`의 `resetFailures` / `resetPassword`는 부모에 `try/catch`가 없다.** 던지는 쪽은 부모, 받는 쪽은 `UserDetailModal`이다. 훅은 **모달 쪽**에 둔다 — 실패 메시지가 떠야 할 곳이 모달이기 때문이다. `resetPassword`는 임시 비밀번호를 반환하므로 `onDone: setTempPassword`로 받는다.

---

## 4. 검증

이 저장소의 `npm test`는 백엔드 pytest를 돌리고, 프론트엔드 테스트 프레임워크는 없다. 검증은 타입 검사 · 린트 · 수동 확인으로 한다.

- `npm run build` — `tsc -b`. `run`의 제네릭이 `onDone(result)`의 타입을 검사하므로 `ProjectDetail`의 `setDetail`, `AdminUsers`의 `setTempPassword`처럼 결과를 받는 자리가 어긋나면 여기서 걸린다.
- `npm run lint` — oxlint. 남은 `UNKNOWN` 상수와 미사용 import(`ApiError`)를 잡는다. 이게 "빠짐없이 걷어냈다"의 근거다.
- **수동 확인 5가지**
  - 공지 저장: 게시하면 모달이 닫히면서 "공지를 게시했습니다." 토스트가 뜬다. 임시저장은 다른 문구가 뜬다.
  - 공지 저장 실패: 제목을 비우고 게시 → 모달이 **닫히지 않고** 폼 안에 오류가 뜬다. 토스트는 뜨지 않는다.
  - 사용자 승인 실패: 폼이 없는 동작이므로 오류가 토스트로 뜬다.
  - 프로젝트 삭제: 목록으로 이동한 **뒤에도** 토스트가 보인다(언마운트 가드가 토스트를 막지 않는다).
  - 단계 실행: 배지가 `RUNNING`으로 바뀌고 토스트는 뜨지 않는다. 연속 실행해도 토스트가 쌓이지 않는다.

---

## 5. 열린 질문

없음.
