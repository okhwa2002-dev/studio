# 페이지당 건수 선택 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**설계 문서:** [2026-08-04-page-size-select-design.md](../specs/2026-08-04-page-size-select-design.md)

**Goal:** 목록 화면 7곳에 하드코딩된 페이지 크기를 사용자가 20 · 50 · 100 중에서 고를 수 있게 한다.

**Architecture:** 셀렉터(`PageSizeSelect`)와 클라이언트 페이징 계산(`useClientPagination`)을 `web/src/components/table/`에 새로 만들고, `TableFooter`의 왼쪽 빈 칸에 셀렉터를 꽂는다. 클라이언트 페이징 6개 화면은 훅으로 갈아타고, 서버 페이징인 감사 로그만 `pageSize` state를 직접 든다.

**Tech Stack:** React 19 + TypeScript + Vite + Tailwind 4 (프론트), FastAPI + pytest (백엔드)

## Global Constraints

- **선택지는 `[20, 50, 100]`, 기본값은 20** — 7개 화면 공통. 목록과 기본값은 `PageSizeSelect.tsx` 한 파일에만 둔다.
- **상태 수명은 화면 안까지** — `useState`만 쓴다. localStorage · URL에 저장하지 않는다.
- **기존 `setPage(1)` 호출은 전부 유지한다** — 필터 변경 시 1페이지 복귀는 훅의 범위 보정과 다른 규칙이다.
- **주석은 한국어**, "무엇"이 아니라 "왜"를 적는다(이 저장소의 기존 주석 방식).
- **태스크마다 커밋한다.** `feat/page-size` 브랜치에 쌓고, 정리(squash·reset)는 나중에 사용자가 판단한다.
- **프론트엔드 테스트 프레임워크가 없다.** 이 저장소의 `npm test`는 백엔드 pytest다. 프론트 태스크의 검증 사이클은 `npm run build`(= `tsc -b && vite build`)와 `npm run lint`다. 새 프레임워크를 도입하지 않는다.
- 프론트 명령은 `web/` 디렉터리에서, pytest는 저장소 루트에서 실행한다.
- 훅이 돌려주는 `setPage`는 `useState` 설정 함수 그 자체라 렌더마다 바뀌지 않는다. 그래도 린트가 `useEffect` 의존성에 `setPage`를 넣으라고 하면 넣는다 — 값이 안정적이라 무한 루프가 생기지 않는다.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `web/src/components/table/PageSizeSelect.tsx` (신규) | 선택지 목록 · 기본값 상수 · 셀렉터 표시. 숫자만 안다 |
| `web/src/components/table/useClientPagination.ts` (신규) | 클라이언트 페이징 계산과 두 가지 페이지 보정 규칙 |
| `web/src/components/table/TableFooter.tsx` (수정) | 아랫줄 3열 배치. 왼쪽 칸에 셀렉터를 놓는다 |
| `web/src/pages/**` 7개 (수정) | 상수 대신 state를 쓰고 `TableFooter`에 넘긴다 |
| `app/api/admin_audit_logs.py` (수정) | `size` 기본값을 화면과 맞춘다 |
| `tests/test_api_audit_logs.py` (수정) | 기본값 회귀 테스트 추가 |

---

### Task 1: `PageSizeSelect` 컴포넌트

**Files:**
- Create: `web/src/components/table/PageSizeSelect.tsx`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `PAGE_SIZE_OPTIONS: readonly [20, 50, 100]`
  - `DEFAULT_PAGE_SIZE: 20`
  - `PageSizeSelect({ value: number, onChange: (size: number) => void }): JSX.Element`

- [ ] **Step 1: 파일을 만든다**

`web/src/components/table/PageSizeSelect.tsx`:

```tsx
// 페이지당 몇 건을 보여줄지 고르는 셀렉터. Pagination과 같은 방침이다 —
// 도메인을 모르고 숫자만 알며, 바깥 여백·정렬은 두지 않는다(배치는 쓰는 쪽이 정한다).
export const PAGE_SIZE_OPTIONS = [20, 50, 100] as const

// 목록 화면 일곱 곳이 모두 이 값에서 시작한다. 화면마다 10 / 50으로 갈려 있던
// 기본값을 하나로 맞춘 것이라, 바꾸려면 여기 한 곳만 고치면 된다.
export const DEFAULT_PAGE_SIZE = 20

export function PageSizeSelect({
  value,
  onChange,
}: {
  value: number
  onChange: (size: number) => void
}) {
  return (
    <select
      value={value}
      // select의 value는 언제나 문자열이다. 쓰는 쪽은 숫자만 다루게 여기서 되돌린다.
      onChange={(e) => onChange(Number(e.target.value))}
      aria-label="페이지당 건수"
      className="rounded-md border border-line-strong px-2 py-1.5 text-sm text-fg-body hover:bg-surface-muted focus:border-fg-muted focus:outline-none"
    >
      {PAGE_SIZE_OPTIONS.map((size) => (
        <option key={size} value={size}>
          {size}건씩
        </option>
      ))}
    </select>
  )
}
```

- [ ] **Step 2: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. 아직 아무도 이 컴포넌트를 쓰지 않으므로 화면은 그대로다.

- [ ] **Step 3: 커밋**

커밋 메시지:

```
feat: 페이지당 건수 셀렉터 컴포넌트 추가
```

---

### Task 2: `useClientPagination` 훅

**Files:**
- Create: `web/src/components/table/useClientPagination.ts`

**Interfaces:**
- Consumes: `DEFAULT_PAGE_SIZE` (Task 1)
- Produces:
  - `useClientPagination<T>(rows: T[]): { page: number; setPage: (page: number) => void; pageSize: number; setPageSize: (size: number) => void; totalPages: number; total: number; pageRows: T[] }`

- [ ] **Step 1: 파일을 만든다**

`web/src/components/table/useClientPagination.ts`:

> 최초 파일명은 `usePagination.ts`였다. `components/table/`의 다른 파일들(`Table.tsx` ·
> `TableFooter.tsx` · `Pagination.tsx` · `PageSizeSelect.tsx` · `seqColumn.ts`)은 전부
> 파일명 = 단일 export명인데 이 파일만 어긋나 있던 것을 최종 브랜치 리뷰에서 지적받아
> `useClientPagination.ts`로 rename했다(`git mv`로 이력 보존, import 6곳 동시 수정).

```ts
import { useEffect, useState } from 'react'
import { DEFAULT_PAGE_SIZE } from './PageSizeSelect'

// 전량을 받아 프론트가 잘라 보여주는 목록(감사 로그를 뺀 여섯 화면)의 공통 계산.
// 화면마다 복붙되던 세 줄(useState(1) · totalPages · slice)에 더해, 페이지 크기가
// 사용자 선택으로 바뀌면서 생긴 보정 규칙 둘을 한곳에 모은다.
//
// seqColumn이 total과 pageSize를 함께 받으므로 total도 돌려준다 — 화면이 rows.length를
// 두 번 세지 않게 한다.
export function useClientPagination<T>(rows: T[]) {
  const [page, setPage] = useState(1)
  // 리터럴 20으로 좁혀지면 50·100을 넣을 수 없다. number로 못박는다.
  const [pageSize, setPageSizeState] = useState<number>(DEFAULT_PAGE_SIZE)

  const total = rows.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  // 행이 줄어 지금 페이지가 사라지는 경우를 막는다(마지막 페이지의 마지막 항목을
  // 지우고 목록을 다시 부르는 상황). 렌더에서 먼저 보정해야 빈 표가 한 프레임
  // 스쳐 보이지 않는다.
  const safePage = Math.min(page, totalPages)

  // 상태에도 써 넣는다. 화면에만 보정하고 두면 목록이 다시 늘었을 때 예전 페이지
  // 번호가 되살아난다.
  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  // 크기를 줄이면 있던 페이지가 통째로 사라지므로 언제나 1페이지로 돌아간다.
  // 필터를 바꿀 때의 setPage(1)은 화면이 그대로 들고 있다 — 그쪽은 아직 유효한
  // 페이지를 굳이 되돌리는 규칙이라 위의 범위 보정으로는 표현되지 않는다.
  const setPageSize = (size: number) => {
    setPageSizeState(size)
    setPage(1)
  }

  return {
    page: safePage,
    setPage,
    pageSize,
    setPageSize,
    totalPages,
    total,
    pageRows: rows.slice((safePage - 1) * pageSize, safePage * pageSize),
  }
}
```

- [ ] **Step 2: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS.

- [ ] **Step 3: 커밋**

커밋 메시지:

```
feat: 클라이언트 페이징 계산 훅 추가
```

---

### Task 3: `TableFooter`에 셀렉터 자리 만들기

props를 **이 태스크에서는 옵셔널로** 둔다. 필수로 만들면 아직 안 고친 7개 화면이 한꺼번에 컴파일 오류가 나서 중간 커밋이 빌드되지 않는다. Task 8에서 전부 옮긴 뒤 필수로 바꾼다.

**Files:**
- Modify: `web/src/components/table/TableFooter.tsx`

**Interfaces:**
- Consumes: `PageSizeSelect` (Task 1)
- Produces: `TableFooter`가 `pageSize?: number`, `onPageSizeChange?: (size: number) => void`를 추가로 받는다

- [ ] **Step 1: 파일 전체를 아래로 교체한다**

`web/src/components/table/TableFooter.tsx`:

```tsx
import { PageSizeSelect } from './PageSizeSelect'
import { Pagination } from './Pagination'

// 표 아래 줄의 배치만 책임진다. 페이지 이동은 Pagination에, 건수 선택은 PageSizeSelect에
// 그대로 위임하고, 여기서는 "좌측 건수 선택 · 가운데 버튼 · 우측 건수" 규칙만 안다.
// 3열 그리드라 버튼이 양옆 폭에 밀리지 않고 항상 정중앙에 온다(양 끝 칸이 폭을 나눠 가짐).
export function TableFooter({
  page,
  totalPages,
  onChange,
  total,
  pageSize,
  onPageSizeChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
  total: number // 페이지가 아니라 전체 행 수
  // 화면을 하나씩 옮기는 동안만 옵셔널이다. 전부 옮기면 필수로 바꿔, 빠뜨린 화면을
  // 타입 검사가 잡게 한다.
  pageSize?: number
  onPageSizeChange?: (size: number) => void
}) {
  return (
    <div className="mt-4 grid grid-cols-3 items-center text-sm text-fg-muted">
      <div>
        {pageSize !== undefined && onPageSizeChange && (
          <PageSizeSelect value={pageSize} onChange={onPageSizeChange} />
        )}
      </div>
      <div className="flex justify-center">
        <Pagination page={page} totalPages={totalPages} onChange={onChange} />
      </div>
      <div className="text-right">전체 {total}건</div>
    </div>
  )
}
```

- [ ] **Step 2: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. 7개 화면 모두 새 props를 넘기지 않으므로 화면은 아직 그대로다.

- [ ] **Step 3: 커밋**

커밋 메시지:

```
feat: 표 아랫줄에 페이지당 건수 선택 자리 마련
```

---

### Task 4: `Projects` · `AdminProjects` 적용

두 화면 모두 `seqColumn`을 쓰고 필터가 단순해서 훅 전환의 표준형이 된다.

**Files:**
- Modify: `web/src/pages/projects/Projects.tsx`
- Modify: `web/src/pages/admin/AdminProjects.tsx`

**Interfaces:**
- Consumes: `useClientPagination` (Task 2), `TableFooter`의 새 props (Task 3)
- Produces: 없음 (화면 적용)

- [ ] **Step 1: `Projects.tsx`를 고친다**

import에 훅을 더한다:

```tsx
import { useClientPagination } from '../../components/table/useClientPagination'
```

`const PAGE_SIZE = 10` 줄을 지운다 (11행).

`const [page, setPage] = useState(1)` (29행)을 지우고, `load` 정의 **위**에 훅 호출을 넣는다. `rows` state 선언 바로 아래가 자리다:

```tsx
  const [rows, setRows] = useState<ProjectSummary[]>([])
  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(rows)
```

`load()` 안의 `setPage(1)`은 그대로 둔다 — 새 프로젝트가 맨 위에 뜨므로 1페이지로 돌아가는 게 맞다.

`seqColumn` 호출(51행)에서 상수를 훅 값으로 바꾼다:

```tsx
    seqColumn<ProjectSummary>(total, page, pageSize),
```

`totalPages` · `pageRows` 계산 두 줄(64–65행)을 지운다.

`TableFooter`(96–101행)를 아래로 바꾼다:

```tsx
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
```

- [ ] **Step 2: `AdminProjects.tsx`를 고친다**

import에 훅을 더한다:

```tsx
import { useClientPagination } from '../../components/table/useClientPagination'
```

`const PAGE_SIZE = 10` 줄을 지운다 (30행).

`const [page, setPage] = useState(1)` (43행)을 지운다. 이 화면은 `filteredRows`가 `rows` 아래에서 계산되므로, 훅 호출은 **`filteredRows` 정의 다음**에 놓는다 (81행 뒤):

```tsx
  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)
```

딥링크 `useEffect`의 `setPage(1)`(51행)과 `load()` 안의 `setPage(1)`(61행)은 그대로 둔다. 다만 `setPage`가 훅에서 오므로 선언 순서가 뒤바뀐다 — `useEffect`와 `load`는 `filteredRows`보다 위에 있고 `setPage`는 아래에서 정의된다. `const`는 호이스팅되지 않으니 **훅 호출을 `rows` state 선언 바로 아래로 올리고, `filteredRows`도 그 위로 함께 올린다.** 최종 순서는 다음과 같다:

```tsx
export function AdminProjects() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [rows, setRows] = useState<AdminProject[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [searchParams] = useSearchParams()

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter((p) => {
    if (status !== 'ALL' && p.status !== status) return false
    if (!keyword) return true
    return (
      p.title.toLowerCase().includes(keyword) ||
      p.topic.toLowerCase().includes(keyword) ||
      p.owner_name.toLowerCase().includes(keyword) ||
      p.owner_email.toLowerCase().includes(keyword)
    )
  })

  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)

  // 대시보드 딥링크의 필터를 반영한다: ?status=DRAFT·REVIEW·DONE 등 → 해당 탭.
  useEffect(() => {
    const s = searchParams.get('status')
    if (s && STATUS_VALUES.has(s)) setStatus(s as StatusFilter)
    setPage(1)
  }, [searchParams])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminProjects
      .list()
      .then((data) => {
        setRows(data)
        setPage(1)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])
```

`seqColumn` 호출(85행)을 바꾼다:

```tsx
    seqColumn<AdminProject>(total, page, pageSize),
```

`totalPages` · `pageRows` 계산 두 줄(106–107행)을 지우고, `TableFooter`에 `pageSize` · `onPageSizeChange`를 더한다:

```tsx
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
```

- [ ] **Step 3: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. 실패하면 대개 `setPage`를 쓰는 위치가 훅 호출보다 위인 경우다 — 순서를 확인한다.

- [ ] **Step 4: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인: `/projects`와 `/admin/projects` 표 아래 왼쪽에 `20건씩` 셀렉터가 있고, 100으로 바꾸면 한 화면에 100행이 나오며 No 열 번호가 이어진다.

- [ ] **Step 5: 커밋**

커밋 메시지:

```
feat: 프로젝트 목록에 페이지당 건수 선택 적용
```

---

### Task 5: `AdminUsers` · `AdminFaqs` 적용

**Files:**
- Modify: `web/src/pages/admin/AdminUsers.tsx`
- Modify: `web/src/pages/admin/AdminFaqs.tsx`

**Interfaces:**
- Consumes: `useClientPagination` (Task 2), `TableFooter`의 새 props (Task 3)
- Produces: 없음

- [ ] **Step 1: `AdminUsers.tsx`를 고친다**

import에 훅을 더한다:

```tsx
import { useClientPagination } from '../../components/table/useClientPagination'
```

`const PAGE_SIZE = 10` 줄을 지운다 (38행).

`const [page, setPage] = useState(1)` (278행)을 지운다. 이 화면은 `setPage`를 `useEffect`(295행)와 `load()`(305행)에서 쓰는데 `const`는 호이스팅되지 않으므로, `keyword` · `filteredRows`(353–364행)를 통째로 그 위로 옮기고 훅 호출을 이어 붙인다. 두 값은 `rows` · `status` · `query`에만 의존하므로 위로 올려도 결과가 같다.

`const status = readStatus(searchParams)` 다음이 아래처럼 된다:

```tsx
  const status = readStatus(searchParams)

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows
    .filter((u) => {
      if (status === 'LOCKED' && !u.locked_at) return false
      if (!keyword) return true
      return u.name.toLowerCase().includes(keyword) || u.email.toLowerCase().includes(keyword)
    })
    // 승인 대기가 관리자의 할 일이다 — 상태를 섞어 보는 탭('전체'·'잠김')에서 맨 위로 올린다.
    // 정렬은 여기서 한다: 페이지 자르기(pageRows)보다 앞서야 1페이지에 모이고,
    // filter가 만든 새 배열이라 rows 원본은 건드리지 않는다.
    // sort는 안정 정렬이므로 같은 그룹 안에서는 서버 정렬(가입일 오름차순)이 그대로 남는다.
    .sort((a, b) => Number(b.status === 'PENDING') - Number(a.status === 'PENDING'))

  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)

  // 탭을 바꾸면 목록이 통째로 바뀐다 — 이전 탭에서 보던 페이지 번호는 의미가 없다.
  useEffect(() => {
    setPage(1)
  }, [status])
```

원래 자리(353–364행)에 있던 `keyword` · `filteredRows` 두 선언은 지운다.

`seqColumn` 호출(367행)을 바꾼다:

```tsx
    seqColumn<AdminUser>(total, page, pageSize),
```

`totalPages` · `pageRows` 계산 두 줄(421–422행)을 지우고, `TableFooter`(480–485행)를 바꾼다:

```tsx
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
```

검색 입력의 `setPage(1)`(450행)과 탭 전환용 `useEffect`의 `setPage(1)`(295행)은 그대로 둔다.

- [ ] **Step 2: `AdminFaqs.tsx`를 고친다**

import에 훅을 더한다:

```tsx
import { useClientPagination } from '../../components/table/useClientPagination'
```

`const PAGE_SIZE = 10` 줄을 지운다 (28행).

`const [page, setPage] = useState(1)` (187행)을 지우고, `filteredRows` 정의(206–210행) 바로 아래에 훅 호출을 넣는다:

```tsx
  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)
```

이 화면의 `setPage(1)`은 전부 JSX 안(탭 245행, 검색 263행)이라 순서를 옮길 필요가 없다 — 그대로 둔다.

`seqColumn` 호출(213행)을 바꾼다:

```tsx
    seqColumn<AdminFaq>(total, page, pageSize),
```

`totalPages` · `pageRows` 계산 두 줄(220–221행)을 지우고, `TableFooter`(294–299행)를 바꾼다:

```tsx
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
```

- [ ] **Step 3: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS.

- [ ] **Step 4: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인: `/admin/users`, `/admin/faqs`에 셀렉터가 보이고 50 · 100 전환이 동작한다. FAQ 화면에서 탭을 바꾸면 1페이지로 돌아간다.

- [ ] **Step 5: 커밋**

커밋 메시지:

```
feat: 사용자·FAQ 목록에 페이지당 건수 선택 적용
```

---

### Task 6: `Notices` · `AdminNotices` 적용

이 둘은 `badgedSeqColumn`을 쓴다. 그 함수는 페이지가 아니라 목록 전체(`filteredRows`)로 번호를 매기므로 `pageSize`와 무관하다 — **순번 열은 건드리지 않는다.**

**Files:**
- Modify: `web/src/pages/notices/Notices.tsx`
- Modify: `web/src/pages/admin/AdminNotices.tsx`

**Interfaces:**
- Consumes: `useClientPagination` (Task 2), `TableFooter`의 새 props (Task 3)
- Produces: 없음

- [ ] **Step 1: `Notices.tsx`를 고친다**

import에 훅을 더한다:

```tsx
import { useClientPagination } from '../../components/table/useClientPagination'
```

`const PAGE_SIZE = 10` 줄을 지운다 (12행).

`const [page, setPage] = useState(1)` (46행)을 지우고, `filteredRows` 정의(76–81행) 바로 아래에 훅 호출을 넣는다:

```tsx
  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)
```

검색 입력의 `setPage(1)`(110행)은 JSX 안이라 그대로 둔다.

`badgedSeqColumn` 호출(86행)은 그대로 둔다.

`totalPages` · `pageRows` 계산 두 줄(99–100행)을 지우고, `TableFooter`(134–139행)를 바꾼다:

```tsx
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
```

- [ ] **Step 2: `AdminNotices.tsx`를 고친다**

import에 훅을 더한다:

```tsx
import { useClientPagination } from '../../components/table/useClientPagination'
```

`const PAGE_SIZE = 10` 줄을 지운다 (42행).

`const [page, setPage] = useState(1)` (227행)을 지우고, `filteredRows` 정의(247–251행) 바로 아래에 훅 호출을 넣는다:

```tsx
  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)
```

탭·검색의 `setPage(1)`(293행, 311행)은 JSX 안이라 그대로 둔다.

`badgedSeqColumn` 호출(255행)은 그대로 둔다.

`totalPages` · `pageRows` 계산 두 줄(268–269행)을 지우고, `TableFooter`(342–347행)를 바꾼다:

```tsx
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
```

- [ ] **Step 3: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS.

- [ ] **Step 4: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인: `/notices`, `/admin/notices`에 셀렉터가 보인다. 고정 공지 행은 계속 '공지' 배지를 달고, 나머지 행의 번호는 페이지를 넘겨도 이어진다.

- [ ] **Step 5: 커밋**

커밋 메시지:

```
feat: 공지 목록에 페이지당 건수 선택 적용
```

---

### Task 7: `AdminAuditLogs` 적용 (서버 페이징)

유일하게 서버가 잘라 주는 화면이라 훅을 쓰지 않는다. `pageSize`만 state로 들고 조회 파라미터에 넣는다.

**Files:**
- Modify: `web/src/pages/admin/AdminAuditLogs.tsx`

**Interfaces:**
- Consumes: `TableFooter`의 새 props (Task 3)
- Produces: 없음

- [ ] **Step 1: 상수를 state로 바꾼다**

import에 기본값을 더한다:

```tsx
import { DEFAULT_PAGE_SIZE } from '../../components/table/PageSizeSelect'
```

`const PAGE_SIZE = 50` 줄(10행)을 지우고, `keyword` state 아래(46행 다음)에 넣는다:

```tsx
  // 서버 페이징이라 useClientPagination을 쓰지 않는다 — 자를 배열이 손에 없다.
  // 크기만 화면이 들고, 자르는 일은 서버가 한다. 기본값은 나머지 여섯 화면과 같은 상수를
  // 본다 — 페이징 방식이 달라도 사용자가 보는 기본 건수까지 달라질 이유는 없다.
  // 리터럴 20으로 좁혀지면 50·100을 넣을 수 없어 number로 못박는다.
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)
```

- [ ] **Step 2: 조회·표시에서 상수를 state로 바꾼다**

`load` 안의 `size`(80행)와 의존성 배열(88행):

```tsx
        size: pageSize,
      })
      .then((data) => {
        setRows(data.items)
        setTotal(data.total)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [from, to, action, success, q, page, pageSize])
```

`seqColumn` 호출(95행):

```tsx
    seqColumn<AuditLog>(total, page, pageSize),
```

`totalPages` 계산(126행):

```tsx
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
```

- [ ] **Step 3: `TableFooter`에 셀렉터를 연결한다**

199–204행을 바꾼다:

```tsx
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={(next) => setFilter({ page: String(next) })}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={(size) => {
              setPageSize(size)
              // 빈 patch를 넘기면 setFilter가 URL에서 page를 지운다 → 1페이지.
              // 필터를 바꿀 때와 같은 경로를 타므로 규칙이 하나뿐이다.
              setFilter({})
            }}
          />
```

- [ ] **Step 4: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. `PAGE_SIZE`가 남아 있으면 미사용 상수로 걸린다.

- [ ] **Step 5: 눈으로 확인한다**

Run (`web/`에서): `npm run dev`
확인: `/admin/audit-logs`에서 3페이지로 간 뒤 100건씩으로 바꾸면 주소의 `page`가 사라지고 1페이지가 다시 조회된다. 네트워크 탭에서 요청 쿼리에 `size=100`이 붙는다.

- [ ] **Step 6: 커밋**

커밋 메시지:

```
feat: 감사 로그 목록에 페이지당 건수 선택 적용
```

---

### Task 8: `TableFooter` props 필수화

7개 화면이 모두 넘기고 있으므로 이제 옵셔널을 걷어낸다. 이 태스크의 빌드 통과가 "빠뜨린 화면이 없다"는 근거다.

**Files:**
- Modify: `web/src/components/table/TableFooter.tsx`

**Interfaces:**
- Consumes: Task 4–7에서 고친 7개 화면
- Produces: `TableFooter`의 `pageSize` · `onPageSizeChange`가 필수 props가 된다

- [ ] **Step 1: 옵셔널 표시와 조건부 렌더를 걷어낸다**

`TableFooter.tsx`를 아래로 교체한다:

```tsx
import { PageSizeSelect } from './PageSizeSelect'
import { Pagination } from './Pagination'

// 표 아래 줄의 배치만 책임진다. 페이지 이동은 Pagination에, 건수 선택은 PageSizeSelect에
// 그대로 위임하고, 여기서는 "좌측 건수 선택 · 가운데 버튼 · 우측 건수" 규칙만 안다.
// 3열 그리드라 버튼이 양옆 폭에 밀리지 않고 항상 정중앙에 온다(양 끝 칸이 폭을 나눠 가짐).
export function TableFooter({
  page,
  totalPages,
  onChange,
  total,
  pageSize,
  onPageSizeChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
  total: number // 페이지가 아니라 전체 행 수
  // 옵셔널로 두지 않는다 — 목록 화면은 전부 셀렉터를 쓰기로 했으므로,
  // 빠뜨린 화면은 타입 검사가 잡아야 한다.
  pageSize: number
  onPageSizeChange: (size: number) => void
}) {
  return (
    <div className="mt-4 grid grid-cols-3 items-center text-sm text-fg-muted">
      <div>
        <PageSizeSelect value={pageSize} onChange={onPageSizeChange} />
      </div>
      <div className="flex justify-center">
        <Pagination page={page} totalPages={totalPages} onChange={onChange} />
      </div>
      <div className="text-right">전체 {total}건</div>
    </div>
  )
}
```

- [ ] **Step 2: 타입 검사와 린트를 돌린다**

Run (`web/`에서): `npm run build && npm run lint`
Expected: 둘 다 PASS. 실패하면 그 화면이 Task 4–7에서 누락된 것이다 — 해당 태스크의 `TableFooter` 수정을 다시 적용한다.

- [ ] **Step 3: 커밋**

커밋 메시지:

```
refactor: 표 아랫줄 건수 선택 props를 필수로 바꿈
```

---

### Task 9: 감사 로그 API 기본값을 화면과 맞춤

**Files:**
- Modify: `app/api/admin_audit_logs.py:30`
- Test: `tests/test_api_audit_logs.py`

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (프론트는 언제나 `size`를 명시하므로 실동작은 그대로다)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_api_audit_logs.py` 끝에 붙인다:

```python
async def test_default_size_matches_screen_default(client, db_session):
    """size를 생략하면 목록 화면 공통 기본값(20)과 같은 값으로 답한다.

    프론트는 언제나 size를 보내므로 실동작은 이 값에 걸리지 않는다. 그래도 맞춰 두는
    것은 /docs에 뜨는 기본값이 화면과 어긋나면 API만 보고 판단하는 사람이 틀리기
    때문이다.
    """
    await _login(client, db_session, "logs-default-size@example.com")
    await _seed(db_session)

    data = await _list(client)

    assert data["size"] == 20
```

- [ ] **Step 2: 실패를 확인한다**

Run (저장소 루트에서): `uv run pytest tests/test_api_audit_logs.py::test_default_size_matches_screen_default -v`
Expected: FAIL — `assert 50 == 20`

- [ ] **Step 3: 기본값을 화면 기본값(20)과 맞춘다**

`app/api/admin_audit_logs.py` 30행:

```python
    # 목록 화면 공통 기본값(20)과 맞춘다. 프론트는 언제나 size를 명시하므로 실동작은
    # 이 값에 걸리지 않지만, /docs에 뜨는 기본값이 화면과 어긋나면 API만 보고 판단하는
    # 사람이 틀린다.
    size: int = Query(20, ge=1, le=_MAX_SIZE),
```

`_MAX_SIZE = 200`은 그대로 둔다 — 최대 선택지 100에 여유가 있고, `test_size_over_limit_is_422`가 상한을 지킨다.

- [ ] **Step 4: 통과를 확인한다**

Run (저장소 루트에서): `uv run pytest tests/test_api_audit_logs.py -v`
Expected: 파일 내 전체 PASS (새 테스트 포함, 기존 페이징·상한 테스트도 그대로).

- [ ] **Step 5: 커밋**

커밋 메시지:

```
feat: 감사 로그 조회 기본 건수를 화면 기본값(20)과 맞춤
```

---

## 최종 검증

모든 태스크를 마친 뒤 한 번에 돌린다.

- [ ] Run (`web/`에서): `npm run build` → PASS
- [ ] Run (`web/`에서): `npm run lint` → PASS
- [ ] Run (저장소 루트에서): `uv run pytest` → 전체 PASS
- [ ] Run (`web/`에서): `npm run dev` 후 7개 화면(`/projects`, `/notices`, `/admin/projects`, `/admin/users`, `/admin/notices`, `/admin/faqs`, `/admin/audit-logs`)에서 셀렉터가 같은 자리에 있고 20 · 50 · 100이 모두 동작하는지 확인
- [ ] 클램프 확인: `/admin/faqs`에서 마지막 페이지에 항목 하나만 남게 한 뒤 그것을 삭제 → 빈 표가 아니라 직전 페이지가 보인다
- [ ] `grep -rn "PAGE_SIZE" web/src` → `PageSizeSelect.tsx`의 `PAGE_SIZE_OPTIONS` · `DEFAULT_PAGE_SIZE`만 남는다
