# 사용자 관리 목록 화면 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/admin/users` 플레이스홀더를 상태 탭·클라이언트 페이징·승인/거절이 되는 실제 화면으로 바꾸고, 재사용 가능한 `Table`·`Pagination` 컴포넌트를 만든다.

**Architecture:** `Table`·`Pagination`은 도메인을 모르는 순수 표시 컴포넌트다. `lib/admin.ts`가 admin/users API를 얇게 감싸고, `AdminUsers.tsx`만 사용자 도메인을 알며 탭·조회·페이징·액션을 조율한다. 백엔드는 건드리지 않는다.

**Tech Stack:** React 19 + TypeScript + React Router 7 + Tailwind CSS v4, oxlint. 기존 `lib/api.ts`(fetch 래퍼)와 `FormError` 컴포넌트를 재사용한다.

**설계 문서:** `docs/superpowers/specs/2026-07-15-admin-users-list-design.md`

## Global Constraints

- **백엔드 변경 없음.** 기존 API만 쓴다: `GET /admin/users?status=PENDING|ACTIVE|DISABLED|REJECTED`, `POST /admin/users/{id}/approve`, `POST /admin/users/{id}/reject`. 마이그레이션·pytest 추가분 없음.
- **프론트 자동화 테스트 하네스가 없다** (Vitest/Playwright 미도입 — 기존 설계 결정). 테스트 파일을 만들지 말 것. 각 태스크 검증은 `npm run lint` + `npm run build` + (마지막에 사람이) 브라우저 수동 확인이다.
- **role 값은 대문자** `'MEMBER' | 'ADMIN'`, **status 값도 대문자** `'PENDING' | 'ACTIVE' | 'DISABLED' | 'REJECTED'`. 소문자로 비교하면 안 맞는다.
- **"전체" 탭을 만들지 않는다.** API가 상태 하나만 받는다 — "전체"는 백엔드 작업이 필요하므로 범위 밖.
- **페이징은 클라이언트에서.** 서버가 상태별 전체를 주고, 브라우저에서 10개씩 자른다. `Table`·`Pagination`은 페이징 로직을 모른다(화면이 자른 행만 넘긴다).
- **이중 방어:** `/admin/users` 라우트는 이미 `RequireAdmin` 안에 있다(레이아웃 단계에서 배선). 서버도 `require_admin`으로 강제한다. 이 계획은 가드를 새로 만들지 않는다.
- **Tailwind v4** (`@import "tailwindcss"`). `tailwind.config.js` 없음, 만들지 않는다.
- 모든 npm 명령은 **프로젝트 루트**(`d:\workspace\ok2020\studio`)에서 실행한다.
- **커밋은 사용자가 직접 한다.** 각 태스크의 커밋 단계는 제안 메시지다. 임의로 `git commit`하지 말고 사용자에게 알린다.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `web/src/components/Table.tsx` (신규) | 제네릭 표. 컬럼 정의(`cell` 렌더)로 임의 내용 표시. 도메인 무지. |
| `web/src/components/Pagination.tsx` (신규) | 페이지 버튼(이전/n/다음). 숫자만 안다. |
| `web/src/lib/admin.ts` (신규) | `AdminUser` 타입 + `adminUsers.list/approve/reject`. admin/users API 계약. |
| `web/src/pages/admin/AdminUsers.tsx` (수정) | 플레이스홀더 → 실제 화면. 탭·조회·페이징·액션 조율. |

---

## Task 1: 재사용 표시 컴포넌트 (Table + Pagination)

도메인을 모르는 순수 표시 컴포넌트 둘. 화면이 없어 브라우저 확인은 없고, 타입·빌드로 검증한다.

**Files:**
- Create: `web/src/components/Table.tsx`
- Create: `web/src/components/Pagination.tsx`

**Interfaces:**
- Consumes: 없음 (React만)
- Produces:
  - `type Column<T> = { header: string; cell: (row: T) => ReactNode; align?: 'left' | 'right' }`
  - `function Table<T>(props: { columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string | number; empty?: ReactNode })`
  - `function Pagination(props: { page: number; totalPages: number; onChange: (page: number) => void })`

- [ ] **Step 1: `web/src/components/Table.tsx` 생성**

반환 타입은 명시하지 않는다(React 19 타입에서 `JSX.Element` 전역이 불안정하므로 추론에 맡긴다). 컬럼 key는 `header`(탭 안에서 유일)를 쓴다.

```tsx
import type { ReactNode } from 'react'

export type Column<T> = {
  header: string
  cell: (row: T) => ReactNode // 셀 내용을 직접 그린다 — 배지·버튼도 여기서
  align?: 'left' | 'right' // 기본 left
}

// 책임은 하나: 스타일된 표를 그린다. 데이터를 가져오지 않고, 정렬·페이징도 없고,
// 무슨 도메인인지 모른다. rows가 비고 empty가 주어지면 표 대신 empty를 보여준다.
export function Table<T>({
  columns,
  rows,
  rowKey,
  empty,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  empty?: ReactNode
}) {
  if (rows.length === 0 && empty !== undefined) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
        {empty}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            {columns.map((col) => (
              <th
                key={col.header}
                className={`px-4 py-3 font-medium ${col.align === 'right' ? 'text-right' : 'text-left'}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-slate-100 last:border-0">
              {columns.map((col) => (
                <td
                  key={col.header}
                  className={`px-4 py-3 text-slate-700 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  {col.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: `web/src/components/Pagination.tsx` 생성**

```tsx
// 페이지가 하나뿐이면 컨트롤을 숨긴다. 도메인을 모르고 숫자만 안다.
export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
}) {
  if (totalPages <= 1) return null

  return (
    <div className="mt-4 flex items-center justify-center gap-3 text-sm">
      <button
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
      >
        이전
      </button>
      <span className="text-slate-600">
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
      >
        다음
      </button>
    </div>
  )
}
```

- [ ] **Step 3: 린트·빌드**

Run: `npm run lint` 그리고 `npm run build`
Expected: 둘 다 통과. (아직 아무도 import하지 않으므로 화면 변화 없음. `auth.tsx:62`의 기존 react-refresh 경고는 무관하며 그대로 남아 있다.)

- [ ] **Step 4: 커밋 (사용자에게 제안)**

```
기능: 재사용 표시 컴포넌트 Table·Pagination 추가
```

---

## Task 2: 사용자 목록 조회 화면 (탭 + 페이징, 액션 제외)

`lib/admin.ts`와 `AdminUsers` 화면을 만든다. 이 태스크가 끝나면 상태 탭으로 사용자를 조회하고 페이지를 넘길 수 있다. 승인/거절은 다음 태스크.

**Files:**
- Create: `web/src/lib/admin.ts`
- Modify: `web/src/pages/admin/AdminUsers.tsx` (플레이스홀더 전체 교체)

**Interfaces:**
- Consumes: Task 1의 `Table`, `Column`, `Pagination`. 기존 `lib/api.ts`의 `api.get/post`·`ApiError`, `components/FormError.tsx`의 `FormError`.
- Produces:
  - `type AdminUser = { id: number; email: string; role: 'MEMBER' | 'ADMIN'; status: 'PENDING' | 'ACTIVE' | 'DISABLED' | 'REJECTED'; created_at: string; approved_at: string | null }`
  - `const adminUsers = { list, approve, reject }` — Task 3이 `approve`/`reject`를 쓴다.

- [ ] **Step 1: `web/src/lib/admin.ts` 생성**

`api.ts`는 HTTP만 알고, 이 파일은 admin/users 계약만 안다. `status` 타입은 `AdminUser['status']`를 재사용한다(별도 enum 파일을 만들지 않는다).

```ts
import { api } from './api'

export type AdminUser = {
  id: number
  email: string
  role: 'MEMBER' | 'ADMIN'
  status: 'PENDING' | 'ACTIVE' | 'DISABLED' | 'REJECTED'
  created_at: string // 백엔드가 로컬 naive ISO 문자열로 준다
  approved_at: string | null
}

export const adminUsers = {
  list: (status: AdminUser['status']) => api.get<AdminUser[]>(`/admin/users?status=${status}`),
  approve: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/approve`),
  reject: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/reject`),
}
```

- [ ] **Step 2: `web/src/pages/admin/AdminUsers.tsx` 교체 (액션 없는 버전)**

기존 플레이스홀더 내용을 아래로 전부 바꾼다. 조회 로직은 `useCallback`으로 묶어 `useEffect` 의존성 경고를 피하고(기존 `auth.tsx`처럼 마운트 시 조회), Task 3에서 액션이 이 `load`를 재사용한다.

```tsx
import { useCallback, useEffect, useState } from 'react'
import { FormError } from '../../components/FormError'
import { Pagination } from '../../components/Pagination'
import { Table, type Column } from '../../components/Table'
import { adminUsers, type AdminUser } from '../../lib/admin'
import { ApiError } from '../../lib/api'

const STATUS_TABS: { status: AdminUser['status']; label: string }[] = [
  { status: 'ACTIVE', label: '활성' },
  { status: 'PENDING', label: '대기' },
  { status: 'REJECTED', label: '거절' },
  { status: 'DISABLED', label: '비활성' },
]

const PAGE_SIZE = 10
const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

function roleLabel(role: AdminUser['role']) {
  return role === 'ADMIN' ? '관리자' : '일반'
}

const STATUS_BADGE: Record<AdminUser['status'], { label: string; className: string }> = {
  PENDING: { label: '대기', className: 'bg-yellow-100 text-yellow-800' },
  ACTIVE: { label: '활성', className: 'bg-green-100 text-green-800' },
  REJECTED: { label: '거절', className: 'bg-red-100 text-red-800' },
  DISABLED: { label: '비활성', className: 'bg-slate-100 text-slate-600' },
}

function StatusBadge({ status }: { status: AdminUser['status'] }) {
  const badge = STATUS_BADGE[status]
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
      {badge.label}
    </span>
  )
}

function formatDate(iso: string) {
  // 백엔드가 로컬 naive ISO 문자열(예: 2026-07-15T12:34:56)을 준다. 앞 10글자가 날짜다.
  // Date로 파싱하면 타임존 보정이 끼어드니, 문자열을 그대로 자른다.
  return iso.slice(0, 10)
}

export function AdminUsers() {
  const [status, setStatus] = useState<AdminUser['status']>('ACTIVE')
  const [rows, setRows] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminUsers
      .list(status)
      .then((data) => {
        setRows(data)
        setPage(1)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [status])

  useEffect(() => {
    load()
  }, [load])

  const columns: Column<AdminUser>[] = [
    { header: '이메일', cell: (u) => u.email },
    { header: '역할', cell: (u) => roleLabel(u.role) },
    { header: '상태', cell: (u) => <StatusBadge status={u.status} /> },
    { header: '가입일', cell: (u) => formatDate(u.created_at), align: 'right' },
  ]

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <div className="mb-4 flex gap-1">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.status}
            onClick={() => setStatus(tab.status)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              status === tab.status
                ? 'bg-slate-900 font-medium text-white'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4">
          <FormError message={error} />
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-sm text-slate-500">불러오는 중…</div>
      ) : (
        <>
          <Table
            columns={columns}
            rows={pageRows}
            rowKey={(u) => u.id}
            empty="해당 상태의 사용자가 없습니다."
          />
          <Pagination page={page} totalPages={totalPages} onChange={setPage} />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 린트·빌드**

Run: `npm run lint` 그리고 `npm run build`
Expected: 둘 다 통과. (`auth.tsx:62` 경고 외 새 경고 없음.)

- [ ] **Step 4: 커밋 (사용자에게 제안)**

```
기능: 사용자 관리 목록 조회 화면 (상태 탭 + 클라이언트 페이징)
```

> 이 시점에 브라우저에서 보면: admin 로그인 후 `/admin/users`에서 "활성" 탭 목록이 뜨고, 탭 전환·페이지 이동이 된다. 승인/거절 버튼은 아직 없다(Task 3). 브라우저 확인은 마지막에 사용자와 함께 한다.

---

## Task 3: 승인/거절 액션 (대기 탭)

"대기" 탭 행에 승인·거절 버튼을 붙이고, 처리 후 목록을 다시 불러온다. 이 태스크가 끝나면 화면이 완성된다.

**Files:**
- Modify: `web/src/pages/admin/AdminUsers.tsx`

**Interfaces:**
- Consumes: Task 2의 `adminUsers.approve(id)`·`adminUsers.reject(id)`·`load`(useCallback), 기존 상태들.
- Produces: 없음 (화면 완성)

- [ ] **Step 1: `AdminUsers.tsx`에 액션 상태와 핸들러 추가**

`export function AdminUsers()` 안, `page` 상태 선언 아래에 처리 중인 행을 추적하는 상태를 더한다. 중복 클릭과 동시 처리를 막는다.

```tsx
  const [actingId, setActingId] = useState<number | null>(null)
```

그리고 `load`를 정의한 `useCallback` 블록 **아래**, `columns` 선언 **위**에 핸들러를 추가한다. 성공하면 현재 탭을 다시 불러온다 — 처리된 사용자는 대기 목록에서 빠지고 해당 상태 탭으로 옮겨간다.

```tsx
  const act = async (id: number, action: 'approve' | 'reject') => {
    setActingId(id)
    setError(null)
    try {
      await adminUsers[action](id)
      load() // 처리된 사용자는 현재(대기) 목록에서 빠진다
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setActingId(null)
    }
  }
```

- [ ] **Step 2: "대기" 탭에서만 액션 열을 추가**

`columns` 배열 선언 **바로 아래**에, 대기 탭일 때만 액션 열을 덧붙인 최종 컬럼을 만든다. 다른 탭에는 빈 "액션" 헤더가 남지 않는다. 처리 중(`actingId !== null`)이면 모든 버튼을 비활성화한다.

```tsx
  const columnsWithAction: Column<AdminUser>[] =
    status === 'PENDING'
      ? [
          ...columns,
          {
            header: '액션',
            align: 'right',
            cell: (u) => (
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => act(u.id, 'approve')}
                  disabled={actingId !== null}
                  className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  승인
                </button>
                <button
                  onClick={() => act(u.id, 'reject')}
                  disabled={actingId !== null}
                  className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  거절
                </button>
              </div>
            ),
          },
        ]
      : columns
```

- [ ] **Step 3: `Table`에 넘기는 컬럼을 `columnsWithAction`으로 교체**

`<Table>`의 `columns={columns}`를 `columns={columnsWithAction}`으로 바꾼다.

```tsx
          <Table
            columns={columnsWithAction}
            rows={pageRows}
            rowKey={(u) => u.id}
            empty="해당 상태의 사용자가 없습니다."
          />
```

- [ ] **Step 4: 린트·빌드**

Run: `npm run lint` 그리고 `npm run build`
Expected: 둘 다 통과. (`auth.tsx:62` 경고 외 새 경고 없음.)

- [ ] **Step 5: 전체 수동 검증 (설계 문서 7장)**

Run: `npm run dev` → http://localhost:5173. **admin 계정**으로 확인한다. (admin 계정이 없으면 README "최초 관리자 만들기" 절차. 대기자 표본은 `/register`로 새로 가입, 다수 표본은 `npm run seed:sample`.)

| # | 확인 | 기대 |
|---|------|------|
| 1 | admin으로 `/admin/users` 진입 | 기본 "활성" 탭 목록이 뜬다 |
| 2 | 탭 전환(활성/대기/거절/비활성) | 각 상태 사용자만 나온다 |
| 3 | "대기" 탭 | 승인·거절 버튼이 보인다 (다른 탭에는 없다) |
| 4 | 대기자 승인 | 목록에서 빠지고, "활성" 탭에서 보인다 (거절 → "거절" 탭) |
| 5 | 승인/거절 처리 중 | 해당 행 버튼이 비활성화된다 |
| 6 | 10명 초과 상태 | 페이지 버튼이 뜨고 이동된다 |
| 7 | 10명 이하 상태 | 페이지 버튼이 숨는다 |
| 8 | 빈 상태 탭 | "해당 상태의 사용자가 없습니다." |
| 9 | member 계정으로 `/admin/users` 직접 접근 | `/dashboard`로 막힌다 (기존 가드 회귀) |

- [ ] **Step 6: 커밋 (사용자에게 제안)**

```
기능: 사용자 관리 화면 승인/거절 액션 추가
```

---

## Self-Review 결과

- **스펙 커버리지:** 설계 3장(Table/Pagination) → Task 1. 4장(lib/admin.ts) → Task 2 Step 1. 5장(화면·탭·페이징·상태 표시) → Task 2 Step 2. 5장(승인/거절 액션·대기 탭 액션 열) → Task 3. 7장(검증 9항목) → Task 3 Step 5. 비범위(백엔드 변경, "전체" 탭, 비활성화/role 변경, 서버 페이징, 정렬/검색, 자동화 테스트)는 어떤 태스크에도 없다 — 의도한 것.
- **타입 일관성:** `Column<T>`/`Table`/`Pagination`(Task 1) → Task 2·3에서 동일 시그니처로 사용. `AdminUser`/`adminUsers.list/approve/reject`(Task 2) → Task 3에서 `adminUsers[action]`으로 사용. `load`(useCallback, Task 2) → Task 3의 `act`가 재사용. `columns`(Task 2) → Task 3에서 `columnsWithAction`으로 확장.
- **플레이스홀더 없음:** 모든 코드 단계에 실제 코드가 들어 있다. 테스트 러너가 없어 TDD 대신 lint+build+수동 확인으로 검증한다(Global Constraints).
