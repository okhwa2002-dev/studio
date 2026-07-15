# 로그인 후 기본 레이아웃 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인 후 모든 화면이 공유하는 레이아웃 셸(좌측 사이드바 + 상단바)을 만들고, role에 따라 관리자 메뉴가 가감되며 메뉴가 실제로 동작하게 한다.

**Architecture:** 메뉴를 `lib/nav.ts` 한 곳에만 정의하고 사이드바 렌더와 상단바 제목이 그 배열에서 파생된다. 셸(`AppLayout`)은 React Router의 **부모 라우트**로 두어 페이지 이동 시 리마운트되지 않게 한다. 페이지들은 셸의 존재를 모르고 자기 콘텐츠만 렌더한다.

**Tech Stack:** Vite + React 19 + TypeScript + React Router + Tailwind CSS v4, oxlint

**설계 문서:** `docs/superpowers/specs/2026-07-14-app-layout-design.md`

## Global Constraints

- **role 값은 대문자다:** `'MEMBER' | 'ADMIN'` (`web/src/lib/auth.tsx`의 `User` 타입). 소문자로 비교하면 관리자 메뉴가 영영 안 나온다.
- **프론트 자동화 테스트는 없다.** 이 프로젝트는 화면이 적어 Vitest/Playwright를 아직 도입하지 않았다(`2026-07-13-auth-frontend-design.md` 7장). 따라서 이 계획의 각 태스크는 `테스트 작성 → 실패 확인` 대신 **`npm run lint` + `npm run build` + 브라우저 수동 확인**으로 검증한다. 테스트 파일을 새로 만들지 말 것 — 하네스가 없어 실행되지 않는다.
- **Tailwind v4**를 쓴다(`@import "tailwindcss"`). `tailwind.config.js`는 없다. 유틸리티 클래스만 쓰고 설정 파일을 새로 만들지 않는다.
- **아이콘은 이모지.** 아이콘 라이브러리(lucide 등)를 설치하지 않는다.
- **이중 방어 원칙:** 프론트 가드와 메뉴 숨김은 UX일 뿐이다. `/admin/*`의 실제 차단은 서버의 `require_admin`이 한다. 프론트에서 막았다고 서버 검사를 빼지 말 것.
- **커밋은 사용자가 직접 한다.** 각 태스크 마지막의 커밋 단계는 **제안 메시지**다. 임의로 `git commit`을 실행하지 말고 사용자에게 알린다.
- 모든 명령은 **프로젝트 루트**(`d:\workspace\ok2020\studio`)에서 실행한다.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `web/src/lib/nav.ts` (신규) | 메뉴 단일 정의 + `navTitle()`. 사이드바와 상단바가 함께 읽는다. |
| `web/src/routes/RequireAdmin.tsx` (신규) | admin이 아니면 `/dashboard`로 |
| `web/src/components/layout/Sidebar.tsx` (신규) | `NAV` + `user.role` → 메뉴 렌더, 활성 표시 |
| `web/src/components/layout/Topbar.tsx` (신규) | 현재 경로 → 페이지 제목 + 우측 `UserMenu` |
| `web/src/components/layout/UserMenu.tsx` (신규) | 이메일 · role 표시 + 로그아웃 |
| `web/src/layouts/AppLayout.tsx` (신규) | 셸 배치 + `<Outlet/>` |
| `web/src/components/Placeholder.tsx` (신규) | "준비 중" 카드 — 빈 페이지 공용 |
| `web/src/pages/Projects.tsx`, `Settings.tsx` (신규) | 플레이스홀더 |
| `web/src/pages/admin/{Approvals,AdminUsers,AdminProjects,AdminSystem}.tsx` (신규) | 플레이스홀더 |
| `web/src/pages/Dashboard.tsx` (수정) | 헤더·로그아웃을 셸에 넘기고 본문만 남긴다 |
| `web/src/App.tsx` (수정) | 라우트 중첩(`RequireAuth → AppLayout → 페이지`) |

---

## Task 1: 메뉴 정의와 admin 가드

화면이 없는 기반 두 개다. 여기서 정한 이름과 타입을 이후 태스크가 그대로 쓴다.

**Files:**
- Create: `web/src/lib/nav.ts`
- Create: `web/src/routes/RequireAdmin.tsx`

**Interfaces:**
- Consumes: `web/src/lib/auth.tsx`의 `useAuth()` — `{ user: User | null, ... }`, `User.role: 'MEMBER' | 'ADMIN'`
- Produces:
  - `type NavItem = { path: string; label: string; icon: string; adminOnly?: boolean }`
  - `const NAV: NavItem[]`
  - `function navTitle(pathname: string): string`
  - `function RequireAdmin(): JSX.Element` — `<Outlet/>` 기반 라우트 가드

- [ ] **Step 1: `web/src/lib/nav.ts` 생성**

```ts
export type NavItem = {
  path: string
  label: string
  icon: string
  adminOnly?: boolean
}

// 메뉴는 여기에만 적는다. 사이드바(무엇을 보여줄지)와 상단바(지금 어디인지)가
// 같은 배열을 읽으므로, 라벨이 두 곳에서 어긋날 수 없다.
export const NAV: NavItem[] = [
  { path: '/dashboard', label: '대시보드', icon: '📊' },
  { path: '/projects', label: '프로젝트', icon: '🎬' },
  { path: '/settings', label: '설정', icon: '⚙️' },
  { path: '/admin/approvals', label: '가입 승인', icon: '🛡️', adminOnly: true },
  { path: '/admin/users', label: '사용자 관리', icon: '👥', adminOnly: true },
  { path: '/admin/projects', label: '전체 프로젝트', icon: '🗂️', adminOnly: true },
  { path: '/admin/system', label: '시스템 설정', icon: '🔧', adminOnly: true },
]

export function navTitle(pathname: string): string {
  return NAV.find((item) => item.path === pathname)?.label ?? ''
}
```

- [ ] **Step 2: `web/src/routes/RequireAdmin.tsx` 생성**

`RequireAuth.tsx`와 같은 모양이다. `RequireAuth` 안쪽에 중첩되므로 이 시점에 `user`는 이미 존재하지만, 옵셔널 체이닝으로 방어한다.

```tsx
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// 이 가드는 UX일 뿐이다. /admin/*의 실제 차단은 서버의 require_admin이 강제한다.
export function RequireAdmin() {
  const { user } = useAuth()

  if (user?.role !== 'ADMIN') {
    return <Navigate to="/dashboard" replace />
  }
  return <Outlet />
}
```

- [ ] **Step 3: 린트·빌드로 타입 확인**

Run: `npm run lint` 그리고 `npm run build`
Expected: 둘 다 통과. (아직 아무도 이 파일들을 import하지 않으므로 화면 변화는 없다.)

- [ ] **Step 4: 커밋 (사용자에게 제안)**

```
기능: 레이아웃 메뉴 정의(nav.ts)와 관리자 라우트 가드 추가
```

---

## Task 2: 셸 컴포넌트와 대시보드 배선

셸을 만들고 `/dashboard`를 그 안에 넣는다. **이 태스크가 끝나면 브라우저에서 사이드바와 상단바가 실제로 보인다.**

**Files:**
- Create: `web/src/components/layout/Sidebar.tsx`
- Create: `web/src/components/layout/Topbar.tsx`
- Create: `web/src/components/layout/UserMenu.tsx`
- Create: `web/src/layouts/AppLayout.tsx`
- Create: `web/src/components/Placeholder.tsx`
- Modify: `web/src/pages/Dashboard.tsx` (전체 교체)
- Modify: `web/src/App.tsx` (라우트 중첩)

**Interfaces:**
- Consumes: Task 1의 `NAV`, `NavItem`, `navTitle()`. 기존 `useAuth()`의 `user`, `logout()`.
- Produces:
  - `function AppLayout(): JSX.Element` — `<Outlet/>`를 품는 부모 라우트 컴포넌트
  - `function Placeholder({ note }: { note: string }): JSX.Element` — Task 3이 재사용

- [ ] **Step 1: `web/src/components/layout/Sidebar.tsx` 생성**

관리자 그룹은 접이식이 아니다. 구분선 + "관리자" 소제목 아래에 항상 펼친다.

```tsx
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../lib/auth'
import { NAV, type NavItem } from '../../lib/nav'

function NavItemLink({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.path}
      className={({ isActive }) =>
        `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
          isActive ? 'bg-slate-900 font-medium text-white' : 'text-slate-700 hover:bg-slate-100'
        }`
      }
    >
      <span aria-hidden>{item.icon}</span>
      {item.label}
    </NavLink>
  )
}

export function Sidebar() {
  const { user } = useAuth()
  const common = NAV.filter((item) => !item.adminOnly)
  // 메뉴를 숨기는 것은 UX일 뿐이다. 보안은 서버의 require_admin이 강제한다.
  const admin = user?.role === 'ADMIN' ? NAV.filter((item) => item.adminOnly) : []

  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="px-5 py-4 text-lg font-semibold text-slate-900">Studio</div>
      <nav className="flex flex-col gap-1 px-3">
        {common.map((item) => (
          <NavItemLink key={item.path} item={item} />
        ))}
        {admin.length > 0 && (
          <>
            <div className="mt-4 border-t border-slate-200 px-3 pt-4 pb-1 text-xs font-medium text-slate-500">
              관리자
            </div>
            {admin.map((item) => (
              <NavItemLink key={item.path} item={item} />
            ))}
          </>
        )}
      </nav>
    </aside>
  )
}
```

- [ ] **Step 2: `web/src/components/layout/UserMenu.tsx` 생성**

기존 `Dashboard.tsx`가 갖고 있던 로그아웃 로직이 여기로 온다. 항목이 로그아웃 하나뿐이라 드롭다운을 두지 않는다.

기존 `components/Button.tsx`는 `w-full`로 스타일되어 있어 상단바에서 늘어난다(그래서 `Dashboard.tsx`가 `<div className="w-auto">`로 감싸고 있었다). 상단바에서는 그 래핑 대신 자체 버튼을 쓴다.

```tsx
import { useState } from 'react'
import { useAuth } from '../../lib/auth'

export function UserMenu() {
  const { user, logout } = useAuth()
  const [pending, setPending] = useState(false)

  const onLogout = async () => {
    setPending(true)
    try {
      await logout()
      // user가 null이 되면 RequireAuth가 /login으로 보낸다. 여기서 navigate하지 않는다.
    } catch {
      // 요청이 실패해도 logout()이 로컬 세션은 이미 정리한다.
      // 여기서는 미처리 거부(unhandled rejection)로 새지 않도록 삼키기만 한다.
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-slate-600">
        {user?.email} · {user?.role}
      </span>
      <button
        onClick={onLogout}
        disabled={pending}
        className="rounded-md border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {pending ? '처리 중…' : '로그아웃'}
      </button>
    </div>
  )
}
```

- [ ] **Step 3: `web/src/components/layout/Topbar.tsx` 생성**

```tsx
import { useLocation } from 'react-router-dom'
import { navTitle } from '../../lib/nav'
import { UserMenu } from './UserMenu'

export function Topbar() {
  const { pathname } = useLocation()

  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <h1 className="text-base font-semibold text-slate-900">{navTitle(pathname)}</h1>
      <UserMenu />
    </header>
  )
}
```

- [ ] **Step 4: `web/src/layouts/AppLayout.tsx` 생성**

```tsx
import { Outlet } from 'react-router-dom'
import { Sidebar } from '../components/layout/Sidebar'
import { Topbar } from '../components/layout/Topbar'

// 로그인 후 화면들이 공유하는 껍데기. 라우트의 부모로 두어, 페이지를 옮겨 다녀도
// 리마운트되지 않게 한다(사이드바가 깜빡이지 않는다).
export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      {/* min-w-0: 콘텐츠가 넓어져도 사이드바를 밀어내지 않는다. */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: `web/src/components/Placeholder.tsx` 생성**

```tsx
// 아직 콘텐츠가 없는 화면의 자리. 셸이 동작하는지 눈으로 확인하는 용도이기도 하다.
export function Placeholder({ note }: { note: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
      {note}
    </div>
  )
}
```

- [ ] **Step 6: `web/src/pages/Dashboard.tsx` 교체**

헤더와 로그아웃은 이제 셸의 책임이다. 대시보드는 본문만 남긴다.

```tsx
import { Placeholder } from '../components/Placeholder'

export function Dashboard() {
  return <Placeholder note="대시보드 콘텐츠는 다음 단계에서 만듭니다." />
}
```

- [ ] **Step 7: `web/src/App.tsx` 수정 — `/dashboard`를 셸 안으로**

`RequireAuth` 안쪽에 `AppLayout`을 부모 라우트로 넣는다. `/login`·`/register`·`/pending`은 셸 **밖에** 그대로 둔다.

```tsx
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './layouts/AppLayout'
import { AuthProvider, useAuth } from './lib/auth'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { PendingApproval } from './pages/PendingApproval'
import { Register } from './pages/Register'
import { RequireAuth } from './routes/RequireAuth'
import { RequireGuest } from './routes/RequireGuest'

function Routing() {
  const { loading } = useAuth()

  // 세션 복원(GET /auth/me)이 끝나기 전에 라우트를 그리면, user가 아직 null이라
  // 가드가 로그인된 사용자를 순간적으로 /login으로 튕긴다(새로고침 깜빡임).
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        불러오는 중…
      </div>
    )
  }

  return (
    <Routes>
      <Route element={<RequireGuest />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>
      <Route path="/pending" element={<PendingApproval />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
        </Route>
      </Route>
      {/* 알 수 없는 경로는 /dashboard로. 미로그인이면 RequireAuth가 /login으로 보낸다. */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routing />
      </AuthProvider>
    </BrowserRouter>
  )
}
```

- [ ] **Step 8: 린트·빌드**

Run: `npm run lint` 그리고 `npm run build`
Expected: 둘 다 통과.

- [ ] **Step 9: 브라우저 확인**

Run: `npm run dev` → http://localhost:5173 (샘플 계정: `npm run seed:sample`로 만든 계정, 비밀번호 `password123`)

| 확인 | 기대 |
|------|------|
| 로그인 후 `/dashboard` | 좌측에 "Studio" 로고와 대시보드·프로젝트·설정 메뉴, 상단바에 "대시보드" 제목과 우측 `이메일 · ROLE` + 로그아웃 버튼 |
| admin 계정으로 로그인 | 구분선 아래 "관리자" 소제목과 4개 메뉴가 **추가로** 보인다 |
| member 계정으로 로그인 | 관리자 메뉴가 **보이지 않는다** |
| 대시보드 메뉴 | 활성 상태(어두운 배경)로 강조돼 있다 |
| 로그아웃 | `/login`으로 이동하고, 그 화면에는 사이드바가 **없다** |

> 이 시점에 프로젝트·설정·관리자 메뉴를 클릭하면 해당 라우트가 아직 없어 `*` 규칙에 걸려 `/dashboard`로 되돌아온다. 정상이다 — Task 3에서 연결한다.

- [ ] **Step 10: 커밋 (사용자에게 제안)**

```
기능: 로그인 후 공통 레이아웃(사이드바 + 상단바) 추가
```

---

## Task 3: 플레이스홀더 페이지와 나머지 라우트

메뉴 6개를 실제 페이지에 연결하고 admin 가드를 건다. **이 태스크가 끝나면 모든 메뉴가 동작한다.**

**Files:**
- Create: `web/src/pages/Projects.tsx`
- Create: `web/src/pages/Settings.tsx`
- Create: `web/src/pages/admin/Approvals.tsx`
- Create: `web/src/pages/admin/AdminUsers.tsx`
- Create: `web/src/pages/admin/AdminProjects.tsx`
- Create: `web/src/pages/admin/AdminSystem.tsx`
- Modify: `web/src/App.tsx` (라우트 6개 + `RequireAdmin` 추가)

**Interfaces:**
- Consumes: Task 2의 `Placeholder({ note })`, Task 1의 `RequireAdmin`
- Produces: 각 파일이 같은 이름의 컴포넌트를 named export 한다 (`Projects`, `Settings`, `Approvals`, `AdminUsers`, `AdminProjects`, `AdminSystem`).

> **이름 주의:** 관리자 쪽은 파일명과 export명을 `AdminUsers`/`AdminProjects`로 맞춘다. 일반 `Projects` 페이지와 이름이 충돌하지 않게 하려는 것이다.

- [ ] **Step 1: 일반 페이지 2개 생성**

`web/src/pages/Projects.tsx`:

```tsx
import { Placeholder } from '../components/Placeholder'

export function Projects() {
  return <Placeholder note="프로젝트 목록은 다음 단계에서 만듭니다." />
}
```

`web/src/pages/Settings.tsx`:

```tsx
import { Placeholder } from '../components/Placeholder'

export function Settings() {
  return <Placeholder note="설정 화면은 다음 단계에서 만듭니다." />
}
```

- [ ] **Step 2: 관리자 페이지 4개 생성**

경로가 한 단계 깊으므로 import가 `../../`다.

`web/src/pages/admin/Approvals.tsx`:

```tsx
import { Placeholder } from '../../components/Placeholder'

export function Approvals() {
  return <Placeholder note="가입 승인 목록은 다음 단계에서 만듭니다." />
}
```

`web/src/pages/admin/AdminUsers.tsx`:

```tsx
import { Placeholder } from '../../components/Placeholder'

export function AdminUsers() {
  return <Placeholder note="사용자 관리 화면은 다음 단계에서 만듭니다." />
}
```

`web/src/pages/admin/AdminProjects.tsx`:

```tsx
import { Placeholder } from '../../components/Placeholder'

export function AdminProjects() {
  return <Placeholder note="전체 프로젝트 화면은 다음 단계에서 만듭니다." />
}
```

`web/src/pages/admin/AdminSystem.tsx`:

```tsx
import { Placeholder } from '../../components/Placeholder'

export function AdminSystem() {
  return <Placeholder note="시스템 설정 화면은 다음 단계에서 만듭니다." />
}
```

- [ ] **Step 3: `web/src/App.tsx`의 `Routing()`에 라우트 연결**

import 6개와 `RequireAdmin`을 추가하고, `AppLayout` 하위에 라우트를 넣는다. 파일 전체는 아래와 같아진다.

```tsx
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './layouts/AppLayout'
import { AuthProvider, useAuth } from './lib/auth'
import { AdminProjects } from './pages/admin/AdminProjects'
import { AdminSystem } from './pages/admin/AdminSystem'
import { AdminUsers } from './pages/admin/AdminUsers'
import { Approvals } from './pages/admin/Approvals'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { PendingApproval } from './pages/PendingApproval'
import { Projects } from './pages/Projects'
import { Register } from './pages/Register'
import { Settings } from './pages/Settings'
import { RequireAdmin } from './routes/RequireAdmin'
import { RequireAuth } from './routes/RequireAuth'
import { RequireGuest } from './routes/RequireGuest'

function Routing() {
  const { loading } = useAuth()

  // 세션 복원(GET /auth/me)이 끝나기 전에 라우트를 그리면, user가 아직 null이라
  // 가드가 로그인된 사용자를 순간적으로 /login으로 튕긴다(새로고침 깜빡임).
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        불러오는 중…
      </div>
    )
  }

  return (
    <Routes>
      <Route element={<RequireGuest />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>
      <Route path="/pending" element={<PendingApproval />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/settings" element={<Settings />} />
          <Route element={<RequireAdmin />}>
            <Route path="/admin/approvals" element={<Approvals />} />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/admin/projects" element={<AdminProjects />} />
            <Route path="/admin/system" element={<AdminSystem />} />
          </Route>
        </Route>
      </Route>
      {/* 알 수 없는 경로는 /dashboard로. 미로그인이면 RequireAuth가 /login으로 보낸다. */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routing />
      </AuthProvider>
    </BrowserRouter>
  )
}
```

- [ ] **Step 4: 린트·빌드**

Run: `npm run lint` 그리고 `npm run build`
Expected: 둘 다 통과.

- [ ] **Step 5: 전체 수동 검증 (설계 문서 5장)**

Run: `npm run dev` → http://localhost:5173. **member 계정과 admin 계정 둘 다** 확인한다.

| # | 확인 | 기대 |
|---|------|------|
| 1 | member로 로그인 | 사이드바에 관리자 메뉴가 **보이지 않는다** |
| 2 | member 상태로 주소창에 `/admin/users` 입력 | `/dashboard`로 막힌다 |
| 3 | admin으로 로그인 | 관리자 4개 메뉴가 보이고, 각각 클릭 시 진입된다 |
| 4 | 메뉴 이동 | 상단바 제목이 바뀌고(예: "가입 승인"), 현재 메뉴가 활성 표시된다 |
| 5 | 메뉴 이동 | 사이드바가 깜빡이지 않는다 (셸이 리마운트되지 않음) |
| 6 | 상단바 로그아웃 | `/login`으로 간다 |
| 7 | 셸 안에서 새로고침 (예: `/settings`) | 그 페이지가 유지된다 (`/login`으로 튕기지 않음) |
| 8 | `/login` 화면 | 사이드바가 **없다** |

> **2번이 실패하면**(관리자 화면이 열리면) `RequireAdmin`의 role 비교가 소문자일 가능성이 높다. role은 `'ADMIN'` 대문자다.
> **admin 계정이 없다면** README의 "최초 관리자 만들기" 절차대로 DB에서 승격시킨다:
> `docker compose exec db psql -U studio -d studio -c "UPDATE users SET role='ADMIN', status='ACTIVE' WHERE email='...';"`

- [ ] **Step 6: 커밋 (사용자에게 제안)**

```
기능: 프로젝트·설정·관리자 화면 라우트 연결 (플레이스홀더)
```

---

## Self-Review 결과

- **스펙 커버리지:** 설계 문서 2장(nav.ts) → Task 1 / 3장(컴포넌트 구조·시각 규칙) → Task 2 / 4장(라우팅·RequireAdmin) → Task 2 Step 7 + Task 3 Step 3 / 5장(검증 8항목) → Task 3 Step 5. 비범위(배지, 반응형, `/projects/{id}`, 자동화 테스트)는 어떤 태스크에도 없다 — 의도한 것.
- **타입 일관성:** `NavItem`/`NAV`/`navTitle`(Task 1) → Sidebar·Topbar(Task 2)에서 동일 이름으로 사용. `Placeholder({ note })`(Task 2) → 6개 페이지(Task 3)에서 동일 시그니처로 사용. 관리자 페이지는 파일명 = export명(`AdminUsers` 등)으로 통일.
- **플레이스홀더 없음:** 모든 코드 단계에 실제 코드가 들어 있다.
