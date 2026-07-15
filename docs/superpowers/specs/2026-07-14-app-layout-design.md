# 로그인 후 기본 레이아웃 설계 (Design Spec)

- **작성일:** 2026-07-14
- **범위:** 로그인 후 화면들이 공유하는 레이아웃 셸(사이드바 + 상단바) + role 기반 메뉴 + admin 라우트 가드
- **선행:** 인증 프론트 완료 (`docs/superpowers/specs/2026-07-13-auth-frontend-design.md`)
- **상위 설계:** `docs/superpowers/specs/2026-07-09-studio-design.md` (5장 통합 UI 구조)

---

## 1. 목표 & 범위

### 목표
로그인 후의 모든 화면이 공유하는 **껍데기**를 만든다. 메뉴가 실제로 동작하고, role에 따라 관리자 메뉴가 가감되며, 앞으로 추가될 페이지는 이 셸 안에 들어가기만 하면 되도록 한다.

### 범위에 포함
| 항목 | 내용 |
|------|------|
| 레이아웃 | 좌측 고정 사이드바 + 상단바 + 콘텐츠 영역 |
| 메뉴 | 단일 정의(`nav.ts`)에서 사이드바와 상단바 제목이 함께 파생 |
| 권한 | `RequireAdmin` 가드 + role에 따른 메뉴 가감 |
| 페이지 | `/projects`, `/settings`, `/admin/*` 4개 — **빈 플레이스홀더**. 메뉴가 실제로 동작하게 하기 위함 |
| 정리 | `Dashboard.tsx`의 헤더·로그아웃을 셸로 이관 |

### 비범위 (이번엔 하지 않음)
- 각 페이지의 실제 콘텐츠 (프로젝트 목록, 설정, 가입 승인 화면)
- 사이드바의 "가입 승인 (대기 N)" **배지** — 승인 화면을 만드는 단계에서 그 화면이 가진 데이터로 붙인다. 지금 넣으면 레이아웃이 관리자 도메인 API를 알게 되어 경계가 흐려진다.
- 모바일 반응형·햄버거 메뉴, 사이드바 접기 — 데스크톱 고정. 지금 사용자는 로컬 PC뿐이고, 영상 편집·단계 검토는 데스크톱 작업이다.
- `/projects/new`, `/projects/{id}` — 메뉴에 없는 경로. 프로젝트 화면 단계에서 만든다.
- 프론트 자동화 테스트 — 기존 방침 유지(수동 브라우저 확인)

---

## 2. 설계의 중심: `lib/nav.ts`

메뉴를 **한 곳에만** 정의하고, 사이드바 렌더와 상단바 제목 조회가 그 배열을 함께 읽는다.

```ts
export type NavItem = {
  path: string
  label: string
  icon: string        // 이모지
  adminOnly?: boolean
}

export const NAV: NavItem[] = [
  { path: '/dashboard', label: '대시보드', icon: '📊' },
  { path: '/projects',  label: '프로젝트', icon: '🎬' },
  { path: '/settings',  label: '설정',     icon: '⚙️' },
  { path: '/admin/approvals', label: '가입 승인',     icon: '🛡️', adminOnly: true },
  { path: '/admin/users',     label: '사용자 관리',   icon: '👥', adminOnly: true },
  { path: '/admin/projects',  label: '전체 프로젝트', icon: '🗂️', adminOnly: true },
  { path: '/admin/system',    label: '시스템 설정',   icon: '🔧', adminOnly: true },
]

// 상단바가 쓴다. 매칭되는 항목이 없으면 빈 문자열.
export function navTitle(pathname: string): string
```

**근거:** 메뉴 라벨이 사이드바와 상단바 두 곳에 각각 적히면 언젠가 어긋난다. 하나의 배열에서 파생시키면 **메뉴 추가는 이 파일 한 줄**이고, 라벨은 구조적으로 어긋날 수 없다.

**한계 (의도한 것):** 제목이 nav 라벨에 묶이므로 `/projects/{id}`처럼 **동적 제목**(프로젝트 이름)은 표현할 수 없다. 그런 페이지가 생기면 그 페이지의 제목은 셸에서 비우고 콘텐츠 안에서 직접 그린다. 지금 그 유연성을 위해 Context 등록 방식(페이지가 `usePageHeader({title})`로 셸에 밀어넣기)을 도입하면, 아직 존재하지 않는 요구를 위해 페이지와 셸을 양방향으로 얽고 등록/해제 타이밍 버그를 떠안는 셈이다.

---

## 3. 컴포넌트 구조

```
web/src/
├─ lib/
│  └─ nav.ts                     # 메뉴 단일 정의 + navTitle()
├─ layouts/
│  └─ AppLayout.tsx              # 사이드바 + 상단바 + <Outlet/>
├─ components/
│  ├─ Placeholder.tsx            # "준비 중입니다" 카드 (플레이스홀더 페이지 공용)
│  └─ layout/
│     ├─ Sidebar.tsx             # 로고 + 메뉴 (role 필터)
│     ├─ Topbar.tsx              # 현재 페이지 제목 + 우측 사용자 영역
│     └─ UserMenu.tsx            # 이메일 · role · 로그아웃
├─ routes/
│  └─ RequireAdmin.tsx           # role !== 'ADMIN' → /dashboard
└─ pages/
   ├─ Projects.tsx  Settings.tsx
   └─ admin/{Approvals,Users,Projects,System}.tsx
```

### 각 단위의 책임
| 단위 | 아는 것 | 모르는 것 |
|------|---------|-----------|
| `AppLayout` | 셸의 배치(사이드바·상단바·콘텐츠 골격) | 메뉴 내용, 현재 사용자 |
| `Sidebar` | `NAV` + `user.role` → 무엇을 보여줄지 | 로그아웃, 페이지 제목 |
| `Topbar` | `navTitle(pathname)` → 지금 어디인지 | 메뉴 목록, 인증 |
| `UserMenu` | `useAuth()` → 누구인지, 나가기 | 라우팅, 메뉴 |
| 각 페이지 | 자기 콘텐츠만 | **셸의 존재 자체를 모른다** |

페이지가 셸을 모른다는 점이 중요하다. 페이지는 `<div>`만 반환하고, 셸에 들어갈지 말지는 **라우트 구조가 결정**한다.

### 시각적 규칙
- **사이드바:** 좌측 고정 폭(`w-60`), 화면 높이 전체(`sticky top-0 h-screen`), 우측 경계선. 상단에 "Studio" 로고, 아래에 메뉴.
- **관리자 그룹:** 접이식이 아니다. 구분선 + "관리자" 소제목 아래에 항목 4개를 항상 펼친다. 항목 4개에 열림/닫힘 상태를 두는 건 과잉이다.
- **활성 표시:** `NavLink`의 `isActive`로 현재 메뉴를 강조한다.
- **아이콘:** 이모지. 아이콘 라이브러리 의존성을 지금 들일 이유가 없다 (상위 설계도 이모지로 그려져 있다).
- **상단바:** 좌측에 페이지 제목, 우측에 `UserMenu`.
- **사용자 메뉴:** **드롭다운이 아니다.** `이메일 · ROLE` 텍스트 옆에 로그아웃 버튼 하나. 항목이 하나뿐인 드롭다운은 클릭만 늘린다. 항목이 늘면 그때 드롭다운으로 바꾼다.
- **콘텐츠:** `flex-1 min-w-0` + 여백. 페이지가 넓어져도 사이드바를 밀지 않는다.

### 기존 코드 정리
`Dashboard.tsx`는 지금 자기 헤더와 로그아웃 버튼을 직접 갖고 있다(인증 확인용 임시 화면이었다). 이 둘은 이제 셸의 책임이므로 제거하고, 대시보드는 본문만 남긴다.

---

## 4. 라우팅과 가드

```tsx
<Route element={<RequireGuest />}>
  <Route path="/login" element={<Login />} />
  <Route path="/register" element={<Register />} />
</Route>
<Route path="/pending" element={<PendingApproval />} />

<Route element={<RequireAuth />}>
  <Route element={<AppLayout />}>              {/* 로그인 후 화면 전부가 셸 안 */}
    <Route path="/dashboard" element={<Dashboard />} />
    <Route path="/projects"  element={<Projects />} />
    <Route path="/settings"  element={<Settings />} />
    <Route element={<RequireAdmin />}>
      <Route path="/admin/approvals" element={<Approvals />} />
      <Route path="/admin/users"     element={<AdminUsers />} />
      <Route path="/admin/projects"  element={<AdminProjects />} />
      <Route path="/admin/system"    element={<AdminSystem />} />
    </Route>
  </Route>
</Route>

<Route path="*" element={<Navigate to="/dashboard" replace />} />
```

- **셸을 부모 라우트로 두는 이유:** 페이지를 옮겨 다녀도 `AppLayout`이 리마운트되지 않는다. 각 페이지가 스스로를 `<Shell>`로 감싸는 방식이었다면 라우트 이동마다 사이드바가 재생성돼 깜빡인다.
- **`/login`·`/register`·`/pending`은 셸 밖에** 그대로 둔다. 비로그인 화면에 사이드바가 있어선 안 된다.
- **`RequireAdmin`:** `RequireAuth`와 같은 모양. `user.role !== 'ADMIN'`이면 `/dashboard`로 리다이렉트한다. role 값은 대문자(`'MEMBER' | 'ADMIN'`)다.

### 이중 방어 원칙 유지
프론트의 메뉴 숨김과 `RequireAdmin`은 **UX일 뿐이다.** `/admin/*`의 실제 차단은 서버의 `require_admin`이 강제한다. 주소창에 직접 쳐서 가드를 우회하더라도 API가 403으로 막는다.

---

## 5. 검증 방법

기존 방침대로 프론트는 자동화 테스트를 붙이지 않고 브라우저에서 직접 확인한다. (백엔드 변경이 없어 pytest 추가분도 없다.)

| # | 확인 |
|---|------|
| 1 | member로 로그인 → 사이드바에 관리자 메뉴가 **보이지 않는가** |
| 2 | member 상태로 주소창에 `/admin/users` 입력 → `/dashboard`로 막히는가 |
| 3 | admin으로 로그인 → 관리자 4개 메뉴가 보이고, 각각 클릭 시 진입되는가 |
| 4 | 메뉴 이동 시 상단바 제목이 바뀌고, 현재 메뉴가 활성 표시되는가 |
| 5 | 메뉴 이동 시 사이드바가 깜빡이지 않는가 (리마운트 없음) |
| 6 | 상단바의 로그아웃 → `/login`으로 가는가 |
| 7 | 셸 안에서 새로고침 → 그 페이지가 유지되는가 (`/login`으로 튕기지 않음) |
| 8 | `/login` 화면에는 사이드바가 없는가 |

추가로 `npm run lint`, `npm run build`가 통과해야 한다.

---

## 6. 다음 단계 (이번 범위 밖)

1. `/admin/approvals` — 가입 승인 목록·승인·거절 (백엔드 API는 이미 있음). 이때 사이드바 대기 건수 배지를 함께 붙인다.
2. `/projects` — 프로젝트 목록·생성 (`/projects/new`, `/projects/{id}`). 동적 페이지 제목이 여기서 처음 필요해진다.
3. `/settings` — 사용자 설정
