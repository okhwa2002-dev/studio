# 사용자 관리 목록 화면 설계 (Design Spec)

- **작성일:** 2026-07-15
- **범위:** 관리자용 사용자 관리 목록 화면 + 재사용 가능한 `Table`·`Pagination` 컴포넌트
- **선행:** 로그인 후 레이아웃 셸 완료 (`docs/superpowers/specs/2026-07-14-app-layout-design.md`), 관리자 라우트 `/admin/users`는 플레이스홀더로 존재
- **상위 설계:** `docs/superpowers/specs/2026-07-09-studio-design.md` (5장 통합 UI 구조)

---

## 1. 목표 & 범위

### 목표
`/admin/users` 플레이스홀더를 실제 화면으로 바꾼다. 관리자가 상태별로 사용자를 조회하고, 가입 대기자를 승인·거절할 수 있게 한다. 동시에 앞으로의 관리자 목록 화면들이 재사용할 표·페이징 컴포넌트를 만든다.

### 범위에 포함
| 항목 | 내용 |
|------|------|
| 컴포넌트 | 제네릭 `Table`, `Pagination` — 순수 표시, 도메인 무지 |
| API 래퍼 | `lib/admin.ts` — `AdminUser` 타입 + `list/approve/reject` |
| 화면 | `AdminUsers.tsx` — 상태 탭, 조회, 승인/거절, 클라이언트 페이징 |

### 비범위 (이번엔 하지 않음)
- **백엔드 변경 없음.** 기존 API(`GET /admin/users?status=X`, `POST /admin/users/{id}/approve|reject`)만 쓴다.
- "전체" 탭 — API가 상태 하나만 받으므로 백엔드 작업이 필요하다. 넣지 않는다.
- 비활성화(DISABLED 전환), role 변경 — 엔드포인트가 없다. 필요해질 때 별도 단계.
- 서버 페이징(`LIMIT`/`OFFSET`) — 데이터 규모가 작아 과하다. 클라이언트 페이징으로 시작한다.
- 컬럼 정렬 토글·너비 리사이즈·검색 — YAGNI. `Table`은 표시만 한다.
- `/admin/approvals`(가입 승인) 화면 — 이 화면이 전체 목록을 담당하므로, 승인 화면은 이후 이 목록의 PENDING 탭으로 가는 단축으로 재정의한다. 이번 범위 밖.
- 프론트 자동화 테스트 — 기존 방침 유지(수동 브라우저 확인, 러너 미도입).

---

## 2. 기존 API (변경 없음)

`app/auth/admin_router.py`:

| 메서드 | 경로 | 동작 |
|--------|------|------|
| GET | `/admin/users?status=PENDING\|ACTIVE\|DISABLED\|REJECTED` | 해당 상태 사용자 목록. `created_at ASC` 정렬. status 미지정 시 기본 PENDING. |
| POST | `/admin/users/{id}/approve` | status → ACTIVE |
| POST | `/admin/users/{id}/reject` | status → REJECTED |

목록 행의 컬럼(`app/queries/users.sql`의 `list_by_status`):
`id, email, role, status, approved_at, approved_by, created_at, updated_at`.
화면은 이 중 `id, email, role, status, created_at, approved_at`만 쓴다.

**주의:** 잘못된 status 값은 FastAPI가 422로 거절한다(`UserStatus` enum 검증). 프론트 탭은 항상 유효한 값만 보내므로 정상 흐름에서 발생하지 않는다.

---

## 3. 재사용 컴포넌트

### `components/Table.tsx` — 제네릭 표
책임은 **하나: 스타일된 표를 그리는 것.** 데이터를 가져오지 않고, 정렬·페이징도 없고, "사용자"가 뭔지 모른다.

```tsx
import type { ReactNode } from 'react'

export type Column<T> = {
  header: string
  cell: (row: T) => ReactNode   // 셀 내용을 직접 그린다 — 버튼·배지도 여기서
  align?: 'left' | 'right'      // 기본 left
}

export function Table<T>(props: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  empty?: ReactNode             // rows가 비었을 때 표 자리에 보여줄 내용
}): JSX.Element
```

- `rows`가 비어 있으면 헤더 없이 `empty`(있으면)를 렌더한다. 없으면 빈 표.
- `cell`이 `ReactNode`를 반환하므로 상태 배지·날짜 포맷·액션 버튼이 전부 **소비자 쪽 코드**에 있다. 표는 배치만 한다.
- 제네릭 함수 선언(`function Table<T>`)이라 `.tsx`에서 JSX와 모호해지지 않는다(화살표 제네릭의 `<T,>` 우회가 불필요).
- `align`은 "가입일"·"액션" 열을 오른쪽 정렬하는 최소 옵션. 그 이상의 컬럼 설정은 넣지 않는다.

### `components/Pagination.tsx` — 페이지 버튼
```tsx
export function Pagination(props: {
  page: number          // 1-기반 현재 페이지
  totalPages: number
  onChange: (page: number) => void
}): JSX.Element | null
```

- `totalPages <= 1`이면 `null`을 반환한다(페이지가 하나면 컨트롤을 숨긴다).
- "이전 / n / 다음" 형태. 경계에서 이전·다음 버튼 비활성화.
- 이 컴포넌트도 도메인을 모른다 — 숫자만 안다.

---

## 4. API 래퍼: `lib/admin.ts`

페이지가 HTTP 세부(경로 조립, 응답 타입)를 모르게 admin/users API를 얇게 감싼다. `api.ts`는 HTTP만 알고(인증 개념 없음), `admin.ts`는 admin/users 계약만 안다.

```ts
import { api } from './api'

export type AdminUser = {
  id: number
  email: string
  role: 'MEMBER' | 'ADMIN'
  status: 'PENDING' | 'ACTIVE' | 'DISABLED' | 'REJECTED'
  created_at: string          // 백엔드가 로컬 naive ISO 문자열로 준다
  approved_at: string | null
}

export const adminUsers = {
  list: (status: AdminUser['status']) =>
    api.get<AdminUser[]>(`/admin/users?status=${status}`),
  approve: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/approve`),
  reject: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/reject`),
}
```

- `status` 타입은 `AdminUser['status']`를 재사용한다(별도 enum 파일을 새로 만들지 않는다).
- 응답 타입은 실제 쓰는 것만 좁게 잡는다. `approve`/`reject`의 반환은 화면이 성공 여부만 보므로 최소로 둔다.

---

## 5. 화면: `pages/admin/AdminUsers.tsx`

### 상태
| 상태 | 초기값 | 의미 |
|------|--------|------|
| `status` | `'ACTIVE'` | 선택된 탭. 사용자 관리의 주 뷰는 활성 사용자다. |
| `rows` | `[]` | 현재 탭의 전체 사용자(서버가 상태별로 걸러 준 것) |
| `loading` | `true` | 조회 중 |
| `error` | `null` | `ApiError.message` 또는 null |
| `page` | `1` | 클라이언트 페이지(1-기반) |

### 데이터 흐름
- **탭 변경/최초:** `status`가 바뀌면 `loading=true` → `adminUsers.list(status)` → 성공 시 `rows` 채우고 `page=1`, 실패 시 `error=ApiError.message`. `finally`로 `loading=false`.
- **페이징(클라이언트):**
  - `PAGE_SIZE = 10` (모듈 상수).
  - `totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))`.
  - `pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)` — 이것만 `Table`에 넘긴다.
  - `Pagination`에 `page`·`totalPages`·`setPage`를 넘긴다.
- **승인/거절:** `adminUsers.approve(id)`(또는 reject) 성공 → 현재 탭 재조회(그 사용자는 PENDING 목록에서 빠진다). 처리 중인 행의 두 버튼은 비활성화(`actingId` 상태로 어떤 행이 처리 중인지 추적, 중복 클릭 방지). 실패 시 `error` 배너.

### 컬럼 정의 (화면 쪽 `cell` 함수)
| 헤더 | 내용 |
|------|------|
| 이메일 | `row.email` |
| 역할 | `roleLabel(row.role)` — 'MEMBER'→"일반", 'ADMIN'→"관리자" |
| 상태 | 상태 배지: `statusLabel`+색상 (PENDING 노랑, ACTIVE 초록, REJECTED 빨강, DISABLED 회색) |
| 가입일 | `formatDate(row.created_at)` — `YYYY-MM-DD`, `align: 'right'` |
| 액션 | **`status === 'PENDING'` 탭에서만** 열을 추가. 승인·거절 버튼, `align: 'right'` |

- 라벨·배지·날짜 헬퍼는 이 화면 파일 안의 작은 순수 함수다(표가 아니라 소비자 책임).
- 컬럼 배열은 `status`에 따라 만든다: 기본 4열, `status === 'PENDING'`이면 액션 열을 `concat`. 다른 탭에 빈 "액션" 헤더가 남지 않는다.

### 탭
- 4개: 활성 / 대기 / 거절 / 비활성 → `ACTIVE / PENDING / REJECTED / DISABLED`.
- 선택된 탭 강조. 탭 클릭 시 `status` 변경(→ 위 흐름이 재조회).

### 화면 상태 표시
| 상황 | 표시 |
|------|------|
| 로딩 | "불러오는 중…" (기존 셸 로딩 문구와 일관) |
| 에러 | 서버 메시지 배너(`error`). 기존 `FormError` 패턴과 유사한 톤. |
| 빈 목록 | `Table`의 `empty`: "해당 상태의 사용자가 없습니다." |

---

## 6. 파일 구조 요약

```
web/src/
├─ components/
│  ├─ Table.tsx           # 신규 — 제네릭 표
│  └─ Pagination.tsx      # 신규 — 페이지 버튼
├─ lib/
│  └─ admin.ts            # 신규 — AdminUser + adminUsers.list/approve/reject
└─ pages/admin/
   └─ AdminUsers.tsx      # 수정 — 플레이스홀더 → 실제 화면
```

각 단위의 경계:
- `Table`·`Pagination`: 도메인 무지, 표시만. 다른 관리자 목록에 재사용.
- `admin.ts`: admin/users API 계약만 안다. 화면 무지.
- `AdminUsers`: 사용자 도메인을 아는 유일한 곳. 탭·조회·액션·페이징을 조율한다.

---

## 7. 검증 방법

기존 방침대로 프론트 자동화 테스트 없이 브라우저에서 확인한다. 백엔드 변경이 없어 pytest 추가분도 없다.

| # | 확인 |
|---|------|
| 1 | admin으로 로그인 → `/admin/users` 진입 시 기본 "활성" 탭 목록이 뜨는가 |
| 2 | 탭 전환(활성/대기/거절/비활성) 시 각 상태 사용자만 나오는가 |
| 3 | "대기" 탭에서만 승인·거절 버튼이 보이는가 |
| 4 | 대기자 승인 → 목록에서 빠지고, "활성" 탭에서 보이는가 (거절 → "거절" 탭) |
| 5 | 승인/거절 처리 중 해당 행 버튼이 비활성화되는가 |
| 6 | 사용자가 10명 초과인 상태에서 페이지 버튼이 뜨고, 페이지 이동이 되는가 |
| 7 | 사용자가 10명 이하이면 페이지 버튼이 숨는가 |
| 8 | 빈 상태 탭에서 "해당 상태의 사용자가 없습니다."가 뜨는가 |
| 9 | member 계정으로 `/admin/users` 직접 접근 → `/dashboard`로 막히는가 (기존 가드 회귀) |

추가로 `npm run lint`, `npm run build` 통과.

- 대기자 표본이 없으면 `/register`로 새 계정을 만들어 PENDING 상태를 만든다.
- 페이징 확인용 다수 사용자는 `npm run seed:sample`(개발용 샘플 8명)을 활용하거나 여러 번 가입한다.

---

## 8. 다음 단계 (이번 범위 밖)

1. `/admin/approvals`를 이 목록의 "대기" 탭 단축으로 재정의(또는 제거하고 사이드바에서 대기 건수 배지로 통합).
2. 사용자 비활성화·role 변경 — 백엔드 엔드포인트부터.
3. 데이터가 커지면 서버 페이징으로 전환(`Pagination` UI는 그대로, 데이터 소스만 교체).
4. `Table`·`Pagination`을 "전체 프로젝트" 관리자 화면에 재사용.
