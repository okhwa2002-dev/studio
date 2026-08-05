# 저장·삭제·수정 결과 알림 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**설계 문서:** [2026-08-05-mutation-feedback-design.md](../specs/2026-08-05-mutation-feedback-design.md)

**Goal:** 화면마다 제각각인 변경 결과 알림을 하나의 규칙으로 모은다 — 성공은 토스트, 실패는 상황별(폼이 있으면 그 안, 없으면 토스트).

**Architecture:** `lib/api.ts`에 오류 문자열화(`errorMessage`)를 한 곳 만들고, 그 위에 변경 동작 하나를 통째로 감싸는 `lib/useSubmit.ts` 훅을 얹는다. 8개 화면이 자기 `pending` state · `try/catch` · 토스트 호출을 버리고 훅으로 갈아탄다. 마지막에 변경이 아닌 목록 로딩 쪽의 중복 상수까지 걷어낸다.

**Tech Stack:** React 19 + TypeScript + Vite + Tailwind 4 (프론트). 이 작업은 프론트만 건드린다.

## Global Constraints

- **성공은 토스트, 실패는 상황별.** 고쳐야 할 입력이 있는 폼 안에서는 인라인(`errorAs` 기본값), 목록에서 바로 누르는 동작처럼 붙일 폼이 없으면 `errorAs: 'toast'`.
- **성공 토스트는 화면이 스스로 말하지 않는 경우만 띄운다.** 단계 실행(배지가 `RUNNING`으로 바뀜)과 비밀번호 초기화(임시 비밀번호가 모달에 뜸)는 `success`를 넘기지 않는다.
- **성공 문구는 호출부가 적는다.** 훅은 문구를 추측하지 않는다. 임시저장과 게시는 다른 문구를 쓴다.
- **`useSubmit()` 호출은 반드시 조기 return보다 위에 둔다.** `AdminSystem`·`ProjectDetail`은 로딩 중 `return`이 컴포넌트 중간에 있다. 훅이 그 아래로 가면 React 훅 규칙 위반이고 oxlint가 잡는다.
- **주석은 한국어**, "무엇"이 아니라 "왜"를 적는다(이 저장소의 기존 주석 방식).
- **태스크마다 커밋한다.** `feat/mutation-feedback` 브랜치에 쌓고, 정리(squash·reset)는 나중에 사용자가 판단한다.
- **프론트엔드 테스트 프레임워크가 없다.** 이 저장소의 `npm test`는 백엔드 pytest다. 검증 사이클은 `npm run build`(= `tsc -b && vite build`)와 `npm run lint`(oxlint), 그리고 `npm run dev`로 눈 확인이다. 새 프레임워크를 도입하지 않는다.
- 프론트 명령은 `web/` 디렉터리에서 실행한다.
- **각 화면 태스크는 그 파일의 `const UNKNOWN` 선언까지 함께 지운다.** 남으면 oxlint가 미사용 상수로 잡는다. `import { ApiError }`도 그 파일에서 마지막 사용처가 사라지면 함께 지운다.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `web/src/lib/api.ts` (수정) | `ApiError`·`UNKNOWN_MESSAGE`가 이미 있는 곳. `errorMessage()`를 여기 붙인다 |
| `web/src/lib/useSubmit.ts` (신규) | 변경 동작 하나의 수명 전체 — 진행 잠금 · 오류 문자열화 · 표시 위치 · 성공 토스트 |
| `web/src/pages/admin/AdminNotices.tsx` (수정) | 공지 저장·삭제 |
| `web/src/pages/admin/AdminFaqs.tsx` (수정) | FAQ 저장·삭제 |
| `web/src/pages/admin/AdminSystem.tsx` (수정) | 설정 저장. 초록 배너를 걷어낸다 |
| `web/src/pages/admin/AdminUsers.tsx` (수정) | 승인·거절·잠금 해제 / 실패 횟수·비밀번호 초기화 |
| `web/src/pages/projects/ProjectDetail.tsx` (수정) | 단계 실행 · 대본 저장 · 프로젝트 삭제 |
| `web/src/pages/projects/NewProjectModal.tsx` (수정) | 프로젝트 생성 |
| `web/src/pages/Settings.tsx` (수정) | 비밀번호 변경. 초록 배너를 걷어낸다 |
| `web/src/pages/ChangePasswordRequired.tsx` (수정) | 강제 비밀번호 변경 |
| 목록 로딩 화면 7개 + 인증 폼 3개 (수정) | 변경이 아니므로 훅을 쓰지 않는다. `errorMessage()`만 공유한다 |

---

### Task 1: `errorMessage()` 추출

**Files:**
- Modify: `web/src/lib/api.ts:15`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `UNKNOWN_MESSAGE: string` (기존 상수를 export로 바꾼 것)
  - `errorMessage(e: unknown): string`

- [ ] **Step 1: 상수를 export하고 변환 함수를 붙인다**

`web/src/lib/api.ts` 15행의 `const UNKNOWN_MESSAGE = '알 수 없는 오류가 발생했습니다.'`를 아래로 바꾼다:

```ts
// 화면 15곳이 저마다 선언하던 문자열이다. 이미 이 파일이 같은 값을 쓰고 있었으므로
// 새로 만들지 않고 export만 연다.
export const UNKNOWN_MESSAGE = '알 수 없는 오류가 발생했습니다.'
```

그리고 같은 파일 **맨 아래**(`export const api = {...}` 블록 다음)에 붙인다:

```ts
// catch로 잡은 값을 사람이 읽을 문장으로 바꾼다. ApiError가 아닌 것(코드 버그로 던져진
// TypeError 등)은 서버 메시지가 없으므로 일반 문장으로 덮는다.
//
// 화면 19곳에 흩어져 있던 `e instanceof ApiError ? e.message : UNKNOWN`이 이 한 줄이다.
export const errorMessage = (e: unknown): string =>
  e instanceof ApiError ? e.message : UNKNOWN_MESSAGE
```

- [ ] **Step 2: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. 아직 아무도 `errorMessage`를 쓰지 않으므로 화면은 그대로다.

- [ ] **Step 3: 커밋**

커밋 메시지:

```
refactor: API 오류를 문장으로 바꾸는 함수를 api.ts에 모음
```

---

### Task 2: `useSubmit` 훅

**Files:**
- Create: `web/src/lib/useSubmit.ts`

**Interfaces:**
- Consumes: `errorMessage` (Task 1), `useToast` (`lib/toast.tsx`, 기존)
- Produces:
  - `useSubmit(): { pending: boolean; error: string | null; run: <T>(fn: () => Promise<T>, options?: RunOptions<T>) => Promise<void>; clearError: () => void }`
  - `RunOptions<T> = { success?: string; errorAs?: 'inline' | 'toast'; onDone?: (result: T) => void }`

- [ ] **Step 1: 파일을 만든다**

`web/src/lib/useSubmit.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from './api'
import { useToast } from './toast'

type RunOptions<T> = {
  // 성공 토스트 문구. 넘기지 않으면 토스트를 띄우지 않는다 — 결과가 화면에 곧바로
  // 드러나는 동작(단계 실행 → 배지가 RUNNING, 비밀번호 초기화 → 임시 비번 표시)은
  // 토스트가 화면이 이미 한 말을 반복하는 꼴이 된다.
  success?: string
  // 실패를 어디에 보여줄지. 기본은 인라인이다 — 저장 실패의 대부분은 "제목이 비었다"
  // 처럼 입력을 고쳐야 하는 오류라, 고칠 대상 옆에 붙어 있어야 하고 3.5초 뒤 사라지면
  // 안 된다. 목록에서 바로 누르는 승인·잠금 해제처럼 붙일 폼이 없을 때만 toast를 쓴다.
  errorAs?: 'inline' | 'toast'
  // 성공 후 처리 — 모달 닫기 · 목록 새로고침 · 화면 이동.
  onDone?: (result: T) => void
}

// 저장·삭제·수정 한 번의 수명 전체를 감싼다. 화면마다 복붙되던 pending state ·
// try/catch/finally · 오류 문자열화 · 토스트 호출을 여기로 모아, 호출부에는
// "무엇을 하고, 성공하면 뭐라고 말하고, 그다음 뭘 할지"만 남긴다.
export function useSubmit() {
  const toast = useToast()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 진행 중 판정은 state가 아니라 ref로 한다. state로 보면 같은 렌더의 클로저가 옛 값을
  // 들고 있어 빠른 연타가 두 번 통과할 수 있다. 버튼 disabled는 그대로 두고(눌리지 않는
  // 것이 보여야 한다) 여기는 마지막 방어선이다.
  const running = useRef(false)

  // onDone이 모달을 닫거나(setEditing(null)) 화면을 옮기면(navigate) 이 컴포넌트는
  // 사라진다. 실제로 AdminNotices의 save()는 자기 안에서 모달을 닫으므로, await가
  // 돌아온 시점에 이미 언마운트돼 있다. 그 뒤의 setState는 아무 일도 하지 않아야 한다.
  //
  // 토스트는 이 가드 밖이다 — 프로젝트를 지우고 목록으로 돌아간 화면에서도
  // "삭제했습니다"는 보여야 한다.
  const alive = useRef(true)
  useEffect(() => {
    // 값을 effect 안에서 다시 켠다. StrictMode는 마운트 직후 cleanup을 한 번 돌리는데,
    // 선언부에서만 true를 주면 그 뒤로 영영 false에 머문다.
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const run = useCallback(
    async <T,>(fn: () => Promise<T>, options: RunOptions<T> = {}): Promise<void> => {
      if (running.current) return
      running.current = true
      setPending(true)
      setError(null)
      try {
        const result = await fn()
        // pending을 onDone보다 먼저 내린다 — onDone이 이 컴포넌트를 언마운트시키므로
        // 순서가 반대면 사라진 뒤에 setState하는 꼴이 된다.
        if (alive.current) setPending(false)
        if (options.success) toast.success(options.success)
        options.onDone?.(result)
      } catch (e) {
        if (alive.current) setPending(false)
        const message = errorMessage(e)
        if (options.errorAs === 'toast') toast.error(message)
        // 토스트로 보낸 오류가 화면 어딘가에 함께 남지 않도록, error는 인라인일 때만 채운다.
        else if (alive.current) setError(message)
      } finally {
        running.current = false
      }
    },
    [toast],
  )

  // 폼을 다시 열 때처럼 호출부가 직접 오류를 지우는 자리에서 쓴다.
  const clearError = useCallback(() => setError(null), [])

  return { pending, error, run, clearError }
}
```

- [ ] **Step 2: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. 아직 아무 화면도 쓰지 않는다.

- [ ] **Step 3: 커밋**

커밋 메시지:

```
feat: 저장·삭제 결과 처리를 모으는 useSubmit 훅 추가
```

---

### Task 3: `AdminNotices` 적용

이 화면이 표준형이다 — 모달 폼 + 부모의 저장/삭제. Task 4가 같은 모양을 따른다.

**Files:**
- Modify: `web/src/pages/admin/AdminNotices.tsx`

**Interfaces:**
- Consumes: `useSubmit` (Task 2), `errorMessage` (Task 1)
- Produces: 없음 (화면 적용)

- [ ] **Step 1: import와 상수를 정리한다**

18행 `import { ApiError } from '../../lib/api'`를 바꾼다:

```tsx
import { errorMessage } from '../../lib/api'
import { useSubmit } from '../../lib/useSubmit'
```

44행 `const UNKNOWN = '알 수 없는 오류가 발생했습니다.'`를 지운다.

- [ ] **Step 2: `NoticeFormModal`의 state를 훅으로 바꾼다**

102–103행의 두 줄을 지운다:

```tsx
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
```

같은 자리에 넣는다:

```tsx
  const { pending, error, run } = useSubmit()
```

- [ ] **Step 3: `submit`과 `remove`를 바꾼다**

117–147행(`const submit = async ...`부터 `remove`의 닫는 중괄호까지)을 아래로 교체한다:

```tsx
  const submit = (status: NoticePayload['status']) =>
    run(
      () =>
        onSave({
          title,
          body,
          status,
          pinned_yn: toYn(pinned),
          popup_yn: toYn(popup),
          starts_at: fromInputValue(startsAt),
          ends_at: fromInputValue(endsAt),
        }),
      // 임시저장과 게시는 사용자에게 다른 사건이다 — 같은 버튼 줄에 있어도 문구를 나눈다.
      { success: status === 'DRAFT' ? '공지를 임시저장했습니다.' : '공지를 게시했습니다.' },
    )

  const remove = () => {
    if (!window.confirm('이 공지를 삭제할까요?')) return
    run(() => onDelete(), { success: '공지를 삭제했습니다.' })
  }
```

성공 후 모달을 닫고 목록을 다시 부르는 일은 부모의 `save`/`remove`(304–315행)가 그대로 한다 — `onDone`을 쓰지 않는다. 훅의 언마운트 가드가 그 순서를 감당한다.

- [ ] **Step 4: 목록 로딩의 오류 변환을 바꾼다**

270행:

```tsx
      .catch((e) => setError(errorMessage(e)))
```

- [ ] **Step 5: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. `UNKNOWN`이나 `ApiError`가 남아 있으면 미사용으로 걸린다.

- [ ] **Step 6: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인 (`/admin/notices`):
- 새 공지를 임시저장 → 모달이 닫히고 상단에 "공지를 임시저장했습니다." 초록 토스트가 뜬다.
- 같은 공지를 열어 게시하기 → "공지를 게시했습니다."가 뜬다(문구가 다르다).
- 제목을 비우고 게시하기 → **모달이 닫히지 않고** 폼 안에 오류가 뜬다. 토스트는 뜨지 않는다.
- 공지를 삭제 → 모달이 닫히고 "공지를 삭제했습니다."가 뜬다.

- [ ] **Step 7: 커밋**

커밋 메시지:

```
feat: 공지 저장·삭제 결과를 토스트로 알림
```

---

### Task 4: `AdminFaqs` 적용

Task 3과 같은 모양이다. 행 번호와 문구만 다르다.

**Files:**
- Modify: `web/src/pages/admin/AdminFaqs.tsx`

**Interfaces:**
- Consumes: `useSubmit` (Task 2), `errorMessage` (Task 1)
- Produces: 없음

- [ ] **Step 1: import와 상수를 정리한다**

9행 `import { ApiError } from '../../lib/api'`를 바꾼다:

```tsx
import { errorMessage } from '../../lib/api'
import { useSubmit } from '../../lib/useSubmit'
```

29행 `const UNKNOWN = '알 수 없는 오류가 발생했습니다.'`를 지운다.

- [ ] **Step 2: `FaqFormModal`의 state를 훅으로 바꾼다**

69–70행의 두 줄을 지운다:

```tsx
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
```

같은 자리에 넣는다:

```tsx
  const { pending, error, run } = useSubmit()
```

- [ ] **Step 3: `submit`과 `remove`를 바꾼다**

72–100행을 아래로 교체한다:

```tsx
  const submit = (status: FaqPayload['status']) =>
    run(
      () =>
        onSave({
          question,
          answer,
          category,
          status,
          sort_order: Number(sortOrder) || 0,
        }),
      { success: status === 'DRAFT' ? 'FAQ를 임시저장했습니다.' : 'FAQ를 게시했습니다.' },
    )

  const remove = () => {
    if (!window.confirm('이 FAQ를 삭제할까요?')) return
    run(() => onDelete(), { success: 'FAQ를 삭제했습니다.' })
  }
```

- [ ] **Step 4: 목록 로딩의 오류 변환을 바꾼다**

196행:

```tsx
      .catch((e) => setError(errorMessage(e)))
```

- [ ] **Step 5: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS.

- [ ] **Step 6: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인 (`/admin/faqs`): 임시저장 · 게시 · 삭제가 각각 다른 토스트를 띄운다. 질문을 비우고 게시하면 모달 안에 오류가 남는다.

- [ ] **Step 7: 커밋**

커밋 메시지:

```
feat: FAQ 저장·삭제 결과를 토스트로 알림
```

---

### Task 5: `AdminSystem` 적용 (초록 배너 제거)

이 화면은 조기 return이 컴포넌트 중간(133–134행)에 있다. **훅 호출은 반드시 그 위에 둔다.**
그리고 지금 `error` state 하나가 초기 로딩 실패와 저장 실패를 겸하고 있다 — 저장 실패만 훅으로 옮기고 로딩 실패는 남긴다.

**Files:**
- Modify: `web/src/pages/admin/AdminSystem.tsx`

**Interfaces:**
- Consumes: `useSubmit` (Task 2), `errorMessage` (Task 1)
- Produces: 없음

- [ ] **Step 1: import와 상수를 정리한다**

4행 `import { ApiError } from '../../lib/api'`를 바꾼다:

```tsx
import { errorMessage } from '../../lib/api'
import { useSubmit } from '../../lib/useSubmit'
```

11행 `const UNKNOWN = '알 수 없는 오류가 발생했습니다.'`를 지운다.

- [ ] **Step 2: state 선언을 바꾼다**

109–113행을 아래로 교체한다:

```tsx
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null)
  const [draft, setDraft] = useState<RuntimeSettings | null>(null)
  // 첫 조회 실패 전용이다. 저장 실패는 useSubmit이 따로 들고 있다 — 둘을 한 state에
  // 담으면 "draft가 있으면 저장 실패"라는 암묵 규칙으로 구분하게 된다.
  const [loadError, setLoadError] = useState<string | null>(null)
  // 조기 return(아래 if 두 줄)보다 위여야 한다. 훅은 렌더마다 같은 순서로 불려야 한다.
  const { pending: saving, error: saveError, run, clearError } = useSubmit()
```

`saved` state는 사라진다.

- [ ] **Step 3: 조회 `useEffect`의 오류 처리를 바꾼다**

124–127행:

```tsx
      .catch((e) => {
        if (!alive) return
        setLoadError(errorMessage(e))
      })
```

- [ ] **Step 4: 조기 return을 바꾼다**

133행:

```tsx
  if (loadError && !draft) return <FormError message={loadError} />
```

134행(`if (!snapshot || !draft) ...`)은 그대로 둔다.

- [ ] **Step 5: `set`과 `save`를 바꾼다**

136–139행의 `set`에서 `setSaved(false)`를 지운다:

```tsx
  const set = <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => {
    setDraft({ ...draft, [key]: value })
  }
```

148–161행의 `save`를 아래로 교체한다:

```tsx
  const save = () =>
    run(() => systemSettings.save(draft), {
      success: '시스템 설정을 저장했습니다.',
      onDone: (next) => {
        setSnapshot(next)
        setDraft(next.settings)
      },
    })
```

- [ ] **Step 6: 초록 배너를 걷어내고 오류 표시를 바꾼다**

164–170행을 아래로 교체한다:

```tsx
    <div className="max-w-3xl space-y-4 pb-20">
      {saveError && <FormError message={saveError} />}
```

성공 배너(`{saved && <p ...>시스템 설정을 저장했습니다.</p>}`) 다섯 줄이 여기서 사라진다 — 같은 문장을 토스트가 말한다.

- [ ] **Step 7: 되돌리기 버튼을 바꾼다**

349–356행의 `onClick`을 바꾼다:

```tsx
          onClick={() => {
            setDraft(snapshot.settings)
            clearError()
          }}
```

`setSaved(false)`와 `setError(null)`이 `clearError()` 하나가 된다.

- [ ] **Step 8: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. 훅 호출이 조기 return 아래로 내려가 있으면 oxlint의 react-hooks 규칙이 여기서 잡는다.

- [ ] **Step 9: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인 (`/admin/system`):
- 값을 바꾸고 저장 → 초록 배너 대신 상단에 토스트가 뜨고, 3.5초 뒤 사라진다.
- 렌더 폰트 크기를 범위 밖(예: 1)으로 넣고 저장 → 페이지 상단에 오류가 뜬다(토스트 아님).
- 오류가 뜬 상태에서 되돌리기 → 오류가 사라진다.

- [ ] **Step 10: 커밋**

커밋 메시지:

```
feat: 시스템 설정 저장 결과를 토스트로 알림
```

---

### Task 6: `AdminUsers` 적용

두 곳을 고친다 — 목록의 승인·거절·잠금 해제(폼이 없어 실패도 토스트)와 상세 모달의 초기화 두 개(폼이 있어 인라인).
`actingId`는 코드 어디서도 id 자체를 쓰지 않고 `!== null` 비교로만 쓰이므로(388 · 395 · 408 · 506행) 훅의 `pending`으로 통째로 대체한다.

**Files:**
- Modify: `web/src/pages/admin/AdminUsers.tsx`

**Interfaces:**
- Consumes: `useSubmit` (Task 2), `errorMessage` (Task 1)
- Produces: 없음

- [ ] **Step 1: import와 상수를 정리한다**

`import { ApiError } from '../../lib/api'` 줄을 바꾼다:

```tsx
import { errorMessage } from '../../lib/api'
import { useSubmit } from '../../lib/useSubmit'
```

`useToast` import(13행)는 **그대로 둔다** — 이 파일은 더 이상 `toast`를 직접 부르지 않으므로 마지막에 지워야 한다. Step 4에서 처리한다.

39행 `const UNKNOWN = '알 수 없는 오류가 발생했습니다.'`를 지운다.

- [ ] **Step 2: `UserDetailModal`의 state를 훅 두 개로 바꾼다**

137–140행을 아래로 교체한다:

```tsx
  // 두 동작은 서로 다른 버튼에 붙어 있고 각자 "초기화 중…" 라벨을 갖는다. 훅 하나를
  // 나눠 쓰면 한쪽을 누를 때 다른 쪽 버튼까지 진행 중으로 보인다.
  const { pending: resetting, error: resetError, run: runReset } = useSubmit()
  const { pending: resettingPassword, error: passwordError, run: runPassword } = useSubmit()
  const [tempPassword, setTempPassword] = useState<string | null>(null)
  // 표시 자리는 모달 아래 한 곳뿐이다(229행) — 둘 중 있는 쪽을 보여준다.
  const error = resetError ?? passwordError
```

- [ ] **Step 3: 모달의 두 동작을 바꾼다**

142–171행을 아래로 교체한다:

```tsx
  const reset = () =>
    // 숫자가 0이 되고 버튼이 사라지는 게 전부라 너무 조용하다. 잠김 해제까지 함께
    // 일어나는데 그 사실은 화면에 드러나지 않으므로 문장으로 말해 준다.
    runReset(() => onResetFailures(user.id), {
      success: '로그인 실패 횟수를 초기화했습니다.',
    })

  const resetPassword = () => {
    // 되돌릴 수 없고 이 사용자의 모든 세션을 끊는다 — 실패 횟수 초기화와 달리 한 번 묻는다.
    const ok = window.confirm(
      `${user.name}(${user.email})의 비밀번호를 초기화하시겠습니까?\n\n` +
        '이 사용자의 모든 로그인 세션이 종료되고, 다음 로그인 시 새 비밀번호를 설정해야 합니다.',
    )
    if (!ok) return

    // 성공 토스트가 없다 — 발급된 임시 비밀번호가 곧바로 이 모달에 뜬다.
    // 그보다 분명한 성공 신호가 없다.
    runPassword(() => onResetPassword(user.id), { onDone: setTempPassword })
  }
```

- [ ] **Step 4: 목록의 `act`를 바꾼다**

277–278행에서 `actingId` state를 지운다:

```tsx
  const [error, setError] = useState<string | null>(null)
```

(`const [actingId, setActingId] = useState<number | null>(null)` 줄이 사라진다.)

286행 `const toast = useToast()`를 지우고, 그 자리에 넣는다:

```tsx
  const { pending: acting, run } = useSubmit()
```

13행의 `import { useToast } from '../../lib/toast'`도 지운다 — 이제 이 파일에서 토스트를 직접 부르지 않는다.

330–342행의 `act`를 아래로 교체한다:

```tsx
  const act = (id: number, action: ActionKey) =>
    // 목록 행에서 바로 누르는 동작이라 실패를 붙일 폼이 없다 — 성공도 실패도 토스트다.
    run(() => adminUsers[action](id), {
      success: ACTION_CONFIRM[action].success,
      errorAs: 'toast',
      onDone: load, // 처리된 사용자는 현재(대기) 목록에서 빠진다
    })
```

- [ ] **Step 5: 목록 로딩과 버튼 잠금을 바꾼다**

322행:

```tsx
      .catch((e) => setError(errorMessage(e)))
```

388 · 395 · 408행의 `disabled={actingId !== null}`을 모두 바꾼다:

```tsx
                disabled={acting}
```

506행:

```tsx
          busy={acting}
```

- [ ] **Step 6: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. `actingId` · `UNKNOWN` · `ApiError` · `useToast`가 남아 있으면 미사용으로 걸린다.

- [ ] **Step 7: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인 (`/admin/users`):
- 대기 사용자를 승인 → 확인창이 닫히고 "승인했습니다." 토스트가 뜬다. 목록에서 그 행이 빠진다.
- 이미 승인된 사용자를 다른 탭에서 다시 승인(409 유도) → 오류가 **토스트로** 뜬다.
- 행을 눌러 상세 → 실패 횟수 초기화 → "로그인 실패 횟수를 초기화했습니다." 토스트가 뜨고 숫자가 0이 된다.
- 상세에서 비밀번호 초기화 → **토스트 없이** 임시 비밀번호가 모달에 뜬다.

- [ ] **Step 8: 커밋**

커밋 메시지:

```
feat: 사용자 관리 동작의 성공·실패 알림을 useSubmit으로 통일
```

---

### Task 7: `ProjectDetail` 적용

이 파일은 훅이 셋 필요하다 — 단계 실행(`act`), 대본 저장(`StageCard`), 프로젝트 삭제(`remove`). 오류가 뜨는 자리가 각각 다르기 때문이다.
SSE의 치명적 오류를 담는 페이지 `error` state는 **그대로 둔다**. 그건 변경 실패가 아니라 화면 자체가 성립하지 않는 상태다(407행의 조기 return).

**Files:**
- Modify: `web/src/pages/projects/ProjectDetail.tsx`

**Interfaces:**
- Consumes: `useSubmit` (Task 2), `UNKNOWN_MESSAGE` (Task 1)
- Produces: 없음

- [ ] **Step 1: import와 상수를 정리한다**

`import { ApiError } from '../../lib/api'` 줄을 바꾼다:

```tsx
import { UNKNOWN_MESSAGE } from '../../lib/api'
import { useSubmit } from '../../lib/useSubmit'
```

`import { useToast } from '../../lib/toast'`(6행)를 지운다.

11행 `const UNKNOWN = '알 수 없는 오류가 발생했습니다.'`를 지운다. 이 파일에는 407행에 오류 객체가 아닌 **맨 fallback**(`error ?? UNKNOWN`)이 하나 남으므로 상수를 import해 쓴다.

- [ ] **Step 2: `StageCard`의 대본 저장을 바꾼다**

215–230행을 아래로 교체한다:

```tsx
  const [editing, setEditing] = useState(false)
  // act()를 쓰지 않는 이유: act는 실패를 페이지 상단으로 올리는데, 저장 실패는 편집기를
  // 닫지 않고 그 안에 보여줘야 한다(작성 중인 내용을 날리면 안 된다).
  const {
    pending: savingScript,
    error: saveError,
    run: runSave,
    clearError: clearSaveError,
  } = useSubmit()

  const saveScript = (payload: ScriptEditPayload) =>
    runSave(() => projects.saveScript(projectId, payload), {
      success: '대본을 저장했습니다.',
      onDone: (updated) => {
        onDetail(updated)
        setEditing(false)
      },
    })
```

212–214행에 있던 주석은 위 코드 안으로 옮겨 붙였다 — 원래 자리의 주석 세 줄은 지운다.

245–256행의 '수정' 버튼에서 `setSaveError(null)`을 `clearSaveError()`로 바꾼다:

```tsx
          {editable && !editing && (
            <button
              onClick={() => {
                clearSaveError()
                setEditing(true)
              }}
              disabled={acting}
              className="rounded-md border border-line-strong px-3 py-1 text-xs font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
            >
              수정
            </button>
          )}
```

- [ ] **Step 3: 페이지의 state 선언을 바꾼다**

325–330행을 아래로 교체한다:

```tsx
  // 단계 실행·승인·재생성. 성공 문구를 넘기지 않는다 — 누르는 즉시 배지가 RUNNING으로
  // 바뀌고 진행률이 흐른다. 화면이 이미 말하는 것을 토스트가 반복할 이유가 없고,
  // 단계를 연속 실행하면 토스트만 쌓인다.
  const { pending: acting, error: actError, run: runAct } = useSubmit()
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const {
    pending: deleting,
    error: deleteError,
    run: runRemove,
    clearError: clearDeleteError,
  } = useSubmit()
  const navigate = useNavigate()
```

`const toast = useToast()`가 사라진다. `error` · `loading` state(324행 위쪽)는 그대로 둔다 — SSE 전용이다.

- [ ] **Step 4: `act`와 `remove`를 바꾼다**

378–404행을 아래로 교체한다:

```tsx
  // 요청을 보내는 동안만 잠근다. 실행 완료를 기다리지 않는다 — 결과는 SSE로 온다.
  const act = (fn: () => Promise<Detail>) => runAct(fn, { onDone: setDetail })

  const remove = () =>
    runRemove(() => projects.remove(projectId), {
      success: '프로젝트를 삭제했습니다.',
      // 대화상자를 닫지 않는다 — 실행 중이라 거절된 경우(409) 사용자가 읽고 취소해야
      // 하므로 실패는 기본값대로 인라인이다.
      onDone: () => {
        // replace인 이유: 뒤로 가기로 방금 지운 상세에 돌아가면 404 화면이 뜬다.
        navigate('/projects', { replace: true })
      },
    })
```

- [ ] **Step 5: 오류 표시 자리를 바꾼다**

407행:

```tsx
  if (!detail) return <FormError message={error ?? UNKNOWN_MESSAGE} />
```

416행:

```tsx
      {actError && <div className="mt-4"><FormError message={actError} /></div>}
```

446행의 `setDeleteError(null)`을 바꾼다:

```tsx
              clearDeleteError()
```

- [ ] **Step 6: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. `act`의 반환 타입이 `Promise<void>`라 `StageCard`의 `act` prop 타입(208행)과 그대로 맞는다.

- [ ] **Step 7: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인 (`/projects/:id`):
- 단계를 실행 → 배지가 RUNNING으로 바뀌고 **토스트는 뜨지 않는다**. 연속으로 실행해도 토스트가 쌓이지 않는다.
- 대본을 수정하고 저장 → 편집기가 닫히고 "대본을 저장했습니다."가 뜬다.
- 대본 제목을 비우고 저장 → 편집기가 닫히지 않고 그 안에 오류가 남는다.
- 프로젝트를 삭제 → 목록으로 이동한 **뒤에도** "프로젝트를 삭제했습니다."가 보인다(언마운트 가드가 토스트를 막지 않는다).

- [ ] **Step 8: 커밋**

커밋 메시지:

```
feat: 프로젝트 상세의 저장·삭제 결과 알림을 useSubmit으로 통일
```

---

### Task 8: `NewProjectModal` · `Settings` · `ChangePasswordRequired` 적용

셋 다 단일 폼 + 단일 제출이라 한 태스크로 묶는다. `Settings`에서는 초록 배너와 `onChanged` prop이 함께 사라진다.

**Files:**
- Modify: `web/src/pages/projects/NewProjectModal.tsx`
- Modify: `web/src/pages/Settings.tsx`
- Modify: `web/src/pages/ChangePasswordRequired.tsx`

**Interfaces:**
- Consumes: `useSubmit` (Task 2)
- Produces: 없음

- [ ] **Step 1: `NewProjectModal.tsx`를 고친다**

5행 `import { ApiError } from '../../lib/api'`를 바꾼다:

```tsx
import { useSubmit } from '../../lib/useSubmit'
```

8행 `const UNKNOWN = ...`을 지운다.

21–22행의 두 state를 지우고 훅으로 바꾼다:

```tsx
  const { pending: submitting, error, run } = useSubmit()
```

24–35행의 `submit`을 아래로 교체한다:

```tsx
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    // 목록에 머문 채 새로고침만 하므로(주석 참조) 새 행이 어디 생겼는지 눈에 띄지 않는다.
    // 만들어졌다는 사실은 문장으로 말해 준다.
    run(() => projects.create({ title: title.trim(), topic: topic.trim(), auto_run: autoRun }), {
      success: '프로젝트를 만들었습니다.',
      onDone: onCreated,
    })
  }
```

- [ ] **Step 2: `Settings.tsx`의 모달을 고친다**

7행 `import { ApiError } from '../lib/api'`를 바꾼다:

```tsx
import { useSubmit } from '../lib/useSubmit'
```

11행 `const UNKNOWN = ...`을 지운다.

42–48행의 컴포넌트 시그니처에서 `onChanged`를 뺀다:

```tsx
// 비밀번호 변경 폼을 담은 팝업. 성공하면 토스트가 알리고 스스로 닫힌다.
function ChangePasswordModal({ onClose }: { onClose: () => void }) {
```

53–54행의 `error` · `submitting` state를 지우고 훅으로 바꾼다:

```tsx
  const { pending: submitting, error, run } = useSubmit()
```

62–75행의 `submit`을 아래로 교체한다:

```tsx
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    // 현재 세션은 서버가 쿠키를 회전해 그대로 유지된다. "다른 기기는 다시 로그인해야
    // 한다"는 안내는 원래 설정 화면의 초록 배너가 하던 말이다 — 문장을 잃지 않도록
    // 토스트가 그대로 이어받는다.
    run(() => account.changePassword({ current_password: current, new_password: next }), {
      success: '비밀번호를 변경했습니다. 다른 기기는 다시 로그인해야 합니다.',
      onDone: onClose,
    })
  }
```

- [ ] **Step 3: `Settings.tsx`의 페이지에서 배너를 걷어낸다**

130–140행을 아래로 교체한다:

```tsx
export function Settings() {
  const [showPassword, setShowPassword] = useState(false)

  return (
    <div className="max-w-2xl space-y-4">
```

147–155행의 변경 버튼에서 `setChanged(false)`를 뺀다:

```tsx
          <button
            onClick={() => setShowPassword(true)}
            className="shrink-0 rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-fg-body hover:bg-surface-muted"
          >
            변경
          </button>
```

159–163행의 모달 사용부에서 `onChanged`를 뺀다:

```tsx
      {showPassword && <ChangePasswordModal onClose={() => setShowPassword(false)} />}
```

- [ ] **Step 4: `ChangePasswordRequired.tsx`를 고친다**

7행 `import { ApiError } from '../lib/api'`를 바꾼다:

```tsx
import { useSubmit } from '../lib/useSubmit'
```

11행 `const UNKNOWN = ...`을 지운다.

27–28행의 두 state를 지우고 훅으로 바꾼다:

```tsx
  const { pending: submitting, error, run } = useSubmit()
```

36–50행의 `submit`을 아래로 교체한다:

```tsx
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    run(
      async () => {
        await account.changePassword({ current_password: current, new_password: next })
        // 서버가 쿠키를 회전해 현재 세션은 유지된다. /auth/me를 다시 읽어
        // must_change_password가 내려간 것을 반영하면 아래 가드가 통과한다.
        // refresh까지 run 안에 넣는 이유: 둘 중 하나라도 못 끝내면 이 화면을 떠나면
        // 안 되고, 버튼도 그때까지 잠겨 있어야 한다.
        await refresh()
      },
      {
        // 화면이 통째로 바뀌므로 무슨 일이 일어났는지 말해 주는 문장이 필요하다.
        success: '비밀번호를 변경했습니다.',
        onDone: () => navigate('/dashboard', { replace: true }),
      },
    )
  }
```

`canSubmit`(33–34행)의 `!submitting`은 그대로 둔다 — 이름이 같으므로 고칠 것이 없다.

- [ ] **Step 5: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. `Settings`의 `onChanged`를 한쪽만 지웠으면 여기서 타입 오류가 난다.

- [ ] **Step 6: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인:
- `/projects`에서 새 프로젝트 만들기 → 모달이 닫히고 "프로젝트를 만들었습니다."가 뜬다. 목록에 새 행이 있다.
- `/settings`에서 비밀번호 변경 → 초록 배너 대신 토스트가 뜨고, "다른 기기는 다시 로그인해야 합니다"가 문구에 남아 있다.
- 현재 비밀번호를 틀리게 넣고 변경 → 모달이 닫히지 않고 폼 안에 오류가 뜬다.

- [ ] **Step 7: 커밋**

커밋 메시지:

```
feat: 프로젝트 생성·비밀번호 변경 결과를 토스트로 알림
```

---

### Task 9: 남은 오류 변환 정리

여기까지가 변경 지점이다. 이 태스크는 **변경이 아닌** 화면들 — 목록 로딩과 로그인·회원가입·비밀번호 재설정 — 의 중복 상수만 걷어낸다. `useSubmit`을 쓰지 않는다.

**Files:**
- Modify: `web/src/pages/Dashboard.tsx:9,218`
- Modify: `web/src/pages/faqs/Faqs.tsx:14,53`
- Modify: `web/src/pages/notices/Notices.tsx:12,60`
- Modify: `web/src/pages/notices/NoticeDetail.tsx:9,46`
- Modify: `web/src/pages/admin/AdminProjects.tsx:31,77`
- Modify: `web/src/pages/admin/AdminAuditLogs.tsx:11,91`
- Modify: `web/src/pages/projects/Projects.tsx:12,42`
- Modify: `web/src/pages/Login.tsx:43`
- Modify: `web/src/pages/Register.tsx:81`
- Modify: `web/src/components/PasswordResetModal.tsx:33,49,72`

**Interfaces:**
- Consumes: `errorMessage` (Task 1)
- Produces: 없음

- [ ] **Step 1: 목록 로딩 화면 7개를 고친다**

`Dashboard.tsx` · `Faqs.tsx` · `Notices.tsx` · `NoticeDetail.tsx` · `AdminProjects.tsx` · `AdminAuditLogs.tsx` · `Projects.tsx` 각각에서:

`import { ApiError } from '...lib/api'`를 바꾼다(경로의 `../` 깊이는 파일마다 다르니 원래 줄의 경로를 그대로 쓴다):

```tsx
import { errorMessage } from '../../lib/api'
```

`const UNKNOWN = '알 수 없는 오류가 발생했습니다.'` 줄을 지운다.

`.catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))`을 바꾼다:

```tsx
      .catch((e) => setError(errorMessage(e)))
```

`NoticeDetail.tsx:46`만 `.catch` 콜백이 아니라 `try/catch` 안의 문장이다:

```tsx
        setError(errorMessage(e))
```

- [ ] **Step 2: `Login.tsx`를 고친다**

`Login.tsx`는 37행에서 `e instanceof ApiError && e.status === 403`으로 **상태 코드**를 본다. 이건 문자열 변환이 아니므로 `ApiError` import를 **남긴다.** 43행만 바꾼다:

```tsx
      setError(errorMessage(e))
```

import 줄에 `errorMessage`를 더한다:

```tsx
import { ApiError, errorMessage } from '../lib/api'
```

- [ ] **Step 3: `Register.tsx`를 고친다**

81행:

```tsx
      setError(errorMessage(e))
```

`ApiError` import를 `errorMessage`로 바꾼다:

```tsx
import { errorMessage } from '../lib/api'
```

- [ ] **Step 4: `PasswordResetModal.tsx`를 고친다**

33 · 49 · 72행 세 곳 모두 같은 리터럴을 인라인으로 들고 있다. 셋 다 바꾼다:

```tsx
      setError(errorMessage(e))
```

import 줄을 바꾼다:

```tsx
import { api, errorMessage } from '../lib/api'
```

성공 안내(`onDone('비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요.')`, 70행)는 **그대로 둔다.** 이 문구는 사용자가 로그인 폼에 비밀번호를 입력하는 동안 계속 보여야 쓸모가 있어, 3.5초 뒤 사라지는 토스트로 옮기면 오히려 나빠진다(설계 문서의 비범위 참조).

- [ ] **Step 5: 남은 흔적이 없는지 확인한다**

Run (저장소 루트에서): `grep -rn "알 수 없는 오류가 발생했습니다" web/src`
Expected: `web/src/lib/api.ts`의 `UNKNOWN_MESSAGE` 한 줄만 나온다.

Run (저장소 루트에서): `grep -rn "instanceof ApiError" web/src`
Expected: 세 줄만 남는다 — `lib/api.ts`(`errorMessage` 본문), `lib/events.ts:89`(404·401 상태 판정), `pages/Login.tsx:37`(403 상태 판정). 셋 다 메시지 변환이 아니라 **상태 코드 분기**라 그대로 두는 것이 맞다.

- [ ] **Step 6: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS.

- [ ] **Step 7: 커밋**

커밋 메시지:

```
refactor: 남은 화면의 오류 문자열 변환을 errorMessage로 모음
```

---

## 최종 검증

모든 태스크를 마친 뒤 한 번에 돌린다.

- [ ] Run (`web/`에서): `npm run build` → PASS
- [ ] Run (`web/`에서): `npm run lint` → PASS
- [ ] Run (저장소 루트에서): `uv run pytest` → 전체 PASS (백엔드는 건드리지 않았으므로 회귀가 없어야 한다)
- [ ] Run (저장소 루트에서): `grep -rn "알 수 없는 오류가 발생했습니다" web/src` → `lib/api.ts` 한 줄만
- [ ] Run (저장소 루트에서): `grep -rn "setSaved\|setChanged\|actingId" web/src` → 결과 없음
- [ ] **성공 규칙 확인** — 저장·삭제·수정 후 토스트가 뜨는 화면: `/admin/notices` · `/admin/faqs` · `/admin/system` · `/admin/users` · `/projects`(생성) · `/projects/:id`(대본 저장·삭제) · `/settings`
- [ ] **생략 규칙 확인** — `/projects/:id`에서 단계를 세 번 연속 실행해도 토스트가 하나도 뜨지 않는다. `/admin/users` 상세에서 비밀번호를 초기화하면 임시 비밀번호만 뜨고 토스트는 없다
- [ ] **실패 규칙 확인** — 폼이 있는 화면(공지·FAQ·설정·대본·비밀번호)의 오류는 전부 그 자리에 남고 사라지지 않는다. 폼이 없는 사용자 승인만 토스트로 뜬다
- [ ] **언마운트 확인** — 프로젝트를 삭제하고 목록으로 이동한 뒤에도 토스트가 보이고, 브라우저 콘솔에 React 경고가 없다
