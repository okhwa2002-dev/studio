# Studio — Plan 3: 인증 프론트 화면 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 회원가입 → 가입 대기 안내 → (승인) → 로그인 → 인증 화면 진입 → 새로고침해도 로그인 유지 → 로그아웃까지, 인증 흐름이 끝까지 도는 최소 프론트엔드를 만든다.

**Architecture:** 백엔드에는 `GET /auth/me` 라우트 하나만 추가한다(기존 `current_user` 의존성 재사용). 프론트는 `web/`에 Vite + React + TypeScript + Tailwind로 신규 생성하고, Vite dev 서버의 프록시로 API(:8000)를 같은 출처처럼 호출한다 — 따라서 **CORS 설정이 필요 없다**. 인증 토큰은 httpOnly 쿠키라 JS가 읽을 수 없으므로, 프론트는 앱 진입 시 `GET /auth/me`를 한 번 호출해 세션을 복원한다.

**Tech Stack:** 기존 백엔드 스택(FastAPI, pytest+testcontainers) + 프론트 신규: Vite 7, React 19, TypeScript, Tailwind CSS v4, React Router v7. 패키지 매니저는 npm.

**설계 문서:** `docs/superpowers/specs/2026-07-13-auth-frontend-design.md`

## Global Constraints

- 프론트 코드는 전부 `web/` 아래에 둔다. 패키지 매니저는 **npm**. Node 20 이상.
- **백엔드에 `CORSMiddleware`를 추가하지 않는다.** Vite 프록시로 동일 출처가 되므로 불필요하며, 추가하면 오히려 크로스 사이트 쿠키 설정 문제가 따라온다.
- **Tailwind는 v4**를 쓴다. v4는 `@tailwindcss/vite` 플러그인 + CSS의 `@import "tailwindcss";` 한 줄로 동작하며 **`tailwind.config.js`·`postcss.config.js`가 필요 없다**. (설계 문서 3장 파일 목록에 적힌 `tailwind.config.js`는 v3 기준이었으므로 만들지 않는다 — 의도된 이탈.)
- **사용자에게 보이는 에러 문구는 프론트가 만들지 않고 서버 응답의 `message`를 그대로 표시한다.** 특히 로그인 401 메시지는 서버가 계정 열거 방지를 위해 의도적으로 통일해 둔 것이므로, "이메일이 없습니다"/"비밀번호가 틀립니다"로 세분화하지 않는다. 예외는 서버에 닿지 못한 네트워크 오류(`"서버에 연결할 수 없습니다."`)와 클라이언트 폼 검증 문구뿐이다.
- 백엔드 API 에러 응답은 항상 `{"code": str, "message": str}` 형식이다(기존 전역 핸들러). 프론트는 이를 `ApiError`로 정규화한다.
- **프론트 자동화 테스트는 이번 Plan에서 도입하지 않는다**(설계 문서 7장). 프론트 각 Task의 검증은 `npm run build`(TypeScript 컴파일 통과) + 브라우저 수동 확인으로 한다. 백엔드 Task 1은 기존대로 pytest TDD를 따른다.
- 커밋은 각 Task 마지막 단계에서 수행한다. 커밋 메시지는 기존 스타일(한글, `기능:`/`수정:`/`변경:` 접두사)을 따른다.
- 이번 Plan에서 **관리자 승인 화면은 만들지 않는다**. 검증 중 사용자 승인이 필요하면 DB에서 직접 `UPDATE users SET status='active' WHERE email='...'`로 처리한다.

---

## File Structure

```
studio/
├─ README.md                       # 프론트 실행 방법 추가 (Task 2)
├─ app/auth/router.py              # GET /auth/me 추가 (Task 1)
├─ tests/test_auth_me.py           # 신규 (Task 1)
└─ web/                            # 신규 (Task 2)
   ├─ package.json
   ├─ vite.config.ts               # React + Tailwind 플러그인, API 프록시
   ├─ tsconfig.json / tsconfig.app.json / tsconfig.node.json
   ├─ index.html
   └─ src/
      ├─ main.tsx                  # 진입점 (Task 2)
      ├─ App.tsx                   # Task 2에서 임시 → Task 3 프로브 → Task 4 라우터
      ├─ index.css                 # Tailwind 로드 (Task 2)
      ├─ lib/
      │  ├─ api.ts                 # fetch 래퍼: 쿠키 동봉·에러 정규화·401 갱신 (Task 3)
      │  └─ auth.tsx               # AuthContext / AuthProvider / useAuth (Task 3)
      ├─ routes/
      │  ├─ RequireAuth.tsx        # 미로그인 → /login (Task 4)
      │  └─ RequireGuest.tsx       # 로그인 상태 → /dashboard (Task 4)
      ├─ components/
      │  ├─ AuthCard.tsx           # 인증 화면 공통 카드 레이아웃 (Task 4)
      │  ├─ TextField.tsx          # label + input + 필드 에러 (Task 4)
      │  ├─ Button.tsx             # 제출 버튼(pending 상태) (Task 4)
      │  └─ FormError.tsx          # 폼 상단 서버 에러 배너 (Task 4)
      └─ pages/
         ├─ Login.tsx              # (Task 4)
         ├─ PendingApproval.tsx    # (Task 4)
         ├─ Dashboard.tsx          # (Task 4)
         └─ Register.tsx           # (Task 5)
```

책임 분리: `api.ts`는 HTTP만 안다(인증 개념 없음). `auth.tsx`는 현재 사용자만 안다(화면 없음). `pages/*`는 폼과 표시만 안다(토큰 갱신 로직 없음). `routes/*`는 리다이렉트만 안다.

---

## Task 1: 백엔드 — `GET /auth/me`

**Files:**
- Modify: `app/auth/router.py` (import 추가 + 라우트 추가)
- Test: `tests/test_auth_me.py` (신규)

**Interfaces:**
- Consumes: 기존 `app.auth.dependencies.current_user` — 쿠키의 `access_token`을 검증하고, 사용자를 조회하고, `status != "active"`면 401을 던지고, `password_hash`를 제거한 `dict`를 반환한다.
- Produces: `GET /auth/me` → 200 `{"id": int, "email": str, "role": "member"|"admin"}` / 비인증 시 401 `{"code","message"}`. Task 3의 `auth.tsx`가 이 응답 형태에 의존한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_auth_me.py` 생성:

```python
from app.auth.security import hash_password
from app.models.user import User


async def _login(client, db_session, email: str, role: str = "member", password: str = "pw12345"):
    user = User(email=email, password_hash=hash_password(password), role=role, status="active")
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200


async def test_me_requires_authentication(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_rejects_invalid_token(client):
    client.cookies.set("access_token", "not-a-jwt")
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(client, db_session):
    await _login(client, db_session, "me@example.com")

    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "me@example.com"
    assert body["role"] == "member"
    assert isinstance(body["id"], int)


async def test_me_returns_admin_role(client, db_session):
    await _login(client, db_session, "me-admin@example.com", role="admin")

    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_me_does_not_leak_password_hash(client, db_session):
    await _login(client, db_session, "me-no-hash@example.com")

    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert "password_hash" not in resp.json()
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_auth_me.py -v`
Expected: FAIL — `/auth/me` 라우트가 없어 404가 나므로 `assert resp.status_code == 200`이 깨진다. (401을 기대하는 두 테스트는 404를 받아 역시 실패한다.)

- [ ] **Step 3: 라우트 구현**

`app/auth/router.py` 상단 import 블록에 추가:

```python
from app.auth.dependencies import current_user
```

파일 맨 끝(`logout` 함수 뒤)에 추가:

```python
@router.get("/me")
async def me(user: dict = Depends(current_user)):
    # current_user가 쿠키 검증·상태 확인·password_hash 제거까지 이미 수행한다.
    # 여기서는 프론트가 실제로 쓰는 필드만 골라 내보낸다(감사 컬럼·approved_by 등 미노출).
    return {"id": user["id"], "email": user["email"], "role": user["role"]}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_auth_me.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 전체 테스트 + 린트**

Run: `uv run pytest -q && uv run ruff check`
Expected: 전체 통과, 린트 에러 없음

- [ ] **Step 6: 커밋**

```bash
git add app/auth/router.py tests/test_auth_me.py
git commit -m "기능: 현재 사용자 조회 API 추가 (GET /auth/me)"
```

---

## Task 2: 프론트 스캐폴딩 (Vite + React + TS + Tailwind + API 프록시)

**Files:**
- Create: `web/` 전체 (Vite 템플릿 생성)
- Modify: `web/vite.config.ts`, `web/src/index.css`, `web/src/App.tsx`, `web/src/main.tsx`
- Modify: `README.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `npm run dev`로 뜨는 :5173 개발 서버. `/auth/*`, `/admin/*`, `/health` 요청이 `http://localhost:8000`으로 프록시된다 → Task 3 이후의 모든 API 호출이 이 프록시에 의존한다.

- [ ] **Step 1: Vite 프로젝트 생성**

프로젝트 루트(`d:\workspace\ok2020\studio`)에서 실행:

```bash
npm create vite@latest web -- --template react-ts
cd web
npm install
```

- [ ] **Step 2: 의존성 추가**

`web/` 안에서 실행:

```bash
npm install react-router-dom
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: Vite 설정 — Tailwind 플러그인 + API 프록시**

`web/vite.config.ts` 전체를 아래로 교체:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 개발 중 프론트(:5173)와 API(:8000)를 같은 출처로 만든다.
// 브라우저 입장에서 동일 출처이므로 CORS 설정이 필요 없고,
// httpOnly + SameSite=Lax 인증 쿠키가 그대로 동작한다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/auth': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 4: Tailwind 로드 + 템플릿 잔재 제거**

`web/src/index.css` 전체를 아래 한 줄로 교체 (Vite 템플릿이 넣어둔 기본 스타일을 전부 지운다):

```css
@import "tailwindcss";
```

`web/src/App.css`와 `web/src/assets/react.svg`를 삭제한다:

```bash
rm web/src/App.css web/src/assets/react.svg
```

`web/src/App.tsx` 전체를 아래로 교체 (Tailwind와 프록시가 동작하는지 눈으로 확인하기 위한 임시 화면 — Task 3에서 교체된다):

```tsx
export default function App() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <p className="rounded-lg bg-white px-6 py-4 text-lg font-semibold text-slate-900 shadow">
        Studio 프론트 스캐폴딩 완료
      </p>
    </div>
  )
}
```

`web/src/main.tsx`가 `./App.css`를 import하고 있지 않은지 확인하고, 있다면 그 줄을 지운다. 최종 형태:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 5: 빌드 확인**

Run: `cd web && npm run build`
Expected: TypeScript 컴파일 통과, `web/dist` 생성. 에러 없음.

- [ ] **Step 6: 브라우저에서 프록시 동작 확인**

터미널 1: `uv run uvicorn app.main:app --reload`
터미널 2: `cd web && npm run dev`

브라우저에서 http://localhost:5173 접속:
- "Studio 프론트 스캐폴딩 완료"가 흰 카드 + 회색 배경으로 보인다 → Tailwind 동작 확인.
- 브라우저 주소창에 http://localhost:5173/health 를 열면 `{"status":"ok"}`가 나온다 → **프록시 동작 확인**. (:8000이 아니라 :5173으로 접속했는데 API 응답이 나와야 한다.)

- [ ] **Step 7: `.gitignore`에 프론트 산출물 추가**

`.gitignore` 끝에 추가:

```
# 프론트
web/node_modules/
web/dist/
```

- [ ] **Step 8: README에 프론트 실행 방법 추가**

`README.md`의 "## 개발 실행" 섹션 마지막(7번 항목 뒤)에 이어서 추가:

```markdown
## 프론트 실행

백엔드가 뜬 상태에서, 별도 터미널에서:

1. 의존성 설치(최초 1회): `cd web && npm install`
2. 개발 서버 실행: `npm run dev`
3. 접속: http://localhost:5173

Vite dev 서버가 `/auth`, `/admin`, `/health` 요청을 `http://localhost:8000`으로 프록시한다.
브라우저 입장에선 동일 출처이므로 CORS 설정 없이 httpOnly 인증 쿠키가 그대로 동작한다.
```

- [ ] **Step 9: 커밋**

```bash
git add web .gitignore README.md
git commit -m "기능: 프론트 스캐폴딩 추가 (Vite + React + TS + Tailwind, API 프록시)"
```

---

## Task 3: 인증 기반 — fetch 래퍼 + AuthContext

**Files:**
- Create: `web/src/lib/api.ts`
- Create: `web/src/lib/auth.tsx`
- Modify: `web/src/App.tsx` (임시 프로브 화면 — Task 4에서 라우터로 교체)

**Interfaces:**
- Consumes: Task 1의 `GET /auth/me` → `{id, email, role}` / 401. 기존 백엔드의 `POST /auth/login` → `{id, email, role}`, `POST /auth/register` → 201 `{id, status}`, `POST /auth/logout`, `POST /auth/refresh`. 에러 응답은 `{code, message}`.
- Produces:
  - `api.ts`: `class ApiError extends Error { status: number; code: string; message: string }`, `export const api = { get<T>(path): Promise<T>, post<T>(path, body?): Promise<T> }`
  - `auth.tsx`: `export type User = { id: number; email: string; role: 'member' | 'admin' }`, `export function AuthProvider({ children }: { children: ReactNode })`, `export function useAuth(): AuthState` where `AuthState = { user: User | null; loading: boolean; login(email, password): Promise<void>; register(email, password): Promise<void>; logout(): Promise<void> }`
  - Task 4·5의 모든 페이지와 가드가 `useAuth()`와 `ApiError`를 이 이름 그대로 사용한다.

- [ ] **Step 1: fetch 래퍼 작성**

`web/src/lib/api.ts` 생성:

```ts
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const UNKNOWN_MESSAGE = '알 수 없는 오류가 발생했습니다.'
const NETWORK_MESSAGE = '서버에 연결할 수 없습니다.'

// 401을 받아도 토큰 갱신을 시도하면 안 되는 경로.
// - /auth/refresh: 갱신이 갱신을 부르는 재귀를 막는다.
// - /auth/login: 비밀번호가 틀린 것이지 토큰이 만료된 게 아니다.
// - /auth/logout: 이미 로그아웃 중이다.
const NO_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout']

async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(path, {
      credentials: 'include', // 인증 쿠키를 함께 보낸다
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    // fetch 자체가 거부된 경우(서버 다운·네트워크 끊김). HTTP 상태가 없다.
    throw new ApiError(0, 'NETWORK_ERROR', NETWORK_MESSAGE)
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { code?: string; message?: string }
    return new ApiError(response.status, body.code ?? 'UNKNOWN_ERROR', body.message ?? UNKNOWN_MESSAGE)
  } catch {
    // 본문이 JSON이 아닌 경우(프록시 오류 등)
    return new ApiError(response.status, 'UNKNOWN_ERROR', UNKNOWN_MESSAGE)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response = await send(path, init)

  if (response.status === 401 && !NO_REFRESH_PATHS.includes(path)) {
    const refreshed = await send('/auth/refresh', { method: 'POST' })
    if (refreshed.ok) {
      // 재시도는 딱 한 번. 재귀하지 않으므로 무한 루프가 생길 수 없다.
      response = await send(path, init)
    }
    // 갱신이 실패하면 원래의 401을 그대로 아래로 흘려보낸다 → 호출자가 로그아웃 상태로 처리.
  }

  if (!response.ok) {
    throw await toApiError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
}
```

- [ ] **Step 2: AuthContext 작성**

`web/src/lib/auth.tsx` 생성:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'

export type User = {
  id: number
  email: string
  role: 'member' | 'admin'
}

type AuthState = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 인증 토큰은 httpOnly 쿠키라 JS가 읽을 수 없다.
    // 따라서 "지금 로그인돼 있는가"는 서버에 물어보는 수밖에 없다.
    api
      .get<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null)) // 401(비로그인)·네트워크 오류 모두 로그아웃 상태로 취급
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    // 로그인 응답이 이미 {id, email, role}이므로 /auth/me를 또 부르지 않는다.
    const loggedIn = await api.post<User>('/auth/login', { email, password })
    setUser(loggedIn)
  }

  const register = async (email: string, password: string) => {
    // 가입 직후 사용자는 status=pending이라 로그인 자체가 불가능하다.
    // 그래서 여기서 user를 세팅하지 않는다. 호출자가 /pending으로 안내한다.
    await api.post<{ id: number; status: string }>('/auth/register', { email, password })
  }

  const logout = async () => {
    await api.post('/auth/logout')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext)
  if (state === null) {
    throw new Error('useAuth는 AuthProvider 안에서만 사용할 수 있습니다.')
  }
  return state
}
```

- [ ] **Step 3: 임시 프로브 화면으로 App 교체**

`web/src/App.tsx` 전체를 아래로 교체. **이 화면은 Task 4에서 라우터로 대체되는 임시 확인용이다.**

```tsx
import { AuthProvider, useAuth } from './lib/auth'

function AuthProbe() {
  const { user, loading, logout } = useAuth()

  if (loading) return <p className="text-slate-500">세션 확인 중…</p>

  return (
    <div className="space-y-3 text-center">
      <p className="text-lg font-semibold text-slate-900">
        {user ? `로그인됨: ${user.email} (${user.role})` : '로그인되지 않음'}
      </p>
      {user && (
        <button onClick={logout} className="rounded-md bg-slate-900 px-3 py-2 text-white">
          로그아웃
        </button>
      )}
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="rounded-lg bg-white px-6 py-4 shadow">
          <AuthProbe />
        </div>
      </div>
    </AuthProvider>
  )
}
```

- [ ] **Step 4: 빌드 확인**

Run: `cd web && npm run build`
Expected: TypeScript 컴파일 통과, 에러 없음

- [ ] **Step 5: 브라우저에서 세션 복원 확인**

백엔드(:8000)와 프론트(:5173)를 모두 띄운 상태에서. (admin 계정이 없다면 먼저 `uv run python scripts/seed_admin.py` 실행)

1. http://localhost:5173 접속 → **"로그인되지 않음"** 표시. DevTools Network 탭에 `/auth/me` 요청이 **401**로 보인다.
2. DevTools 콘솔에서 아래를 실행해 쿠키를 심는다 (`.env`의 `ADMIN_EMAIL`/`ADMIN_PASSWORD` 값 사용):

```js
await fetch('/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'admin@example.com', password: '실제-비밀번호' }),
})
```

3. 페이지를 **새로고침** → **"로그인됨: admin@example.com (admin)"** 표시. `/auth/me`가 200이다. → 세션 복원 동작 확인.
4. "로그아웃" 버튼 클릭 → "로그인되지 않음"으로 바뀐다. 새로고침해도 로그아웃 상태가 유지된다.

- [ ] **Step 6: 커밋**

```bash
git add web/src/lib web/src/App.tsx
git commit -m "기능: 프론트 인증 기반 추가 (fetch 래퍼 + AuthContext, 401 자동 갱신)"
```

---

## Task 4: 로그인 슬라이스 — 공통 컴포넌트 · 로그인 · 대기 안내 · 대시보드 · 라우트 가드

**Files:**
- Create: `web/src/components/AuthCard.tsx`, `web/src/components/TextField.tsx`, `web/src/components/Button.tsx`, `web/src/components/FormError.tsx`
- Create: `web/src/routes/RequireAuth.tsx`, `web/src/routes/RequireGuest.tsx`
- Create: `web/src/pages/Login.tsx`, `web/src/pages/PendingApproval.tsx`, `web/src/pages/Dashboard.tsx`
- Modify: `web/src/App.tsx` (임시 프로브 → 실제 라우터)

**Interfaces:**
- Consumes: Task 3의 `useAuth()` (`{ user, loading, login, logout }`), `ApiError` (`.status`, `.message`), `AuthProvider`.
- Produces:
  - `AuthCard({ title, children })`, `TextField(props & { label, error? })`, `Button(props & { pending? })`, `FormError({ message? })` — Task 5의 `Register.tsx`가 그대로 재사용한다.
  - 라우트: `/login`, `/pending`, `/dashboard`. Task 5가 `/register`를 여기에 추가한다.

- [ ] **Step 1: 공통 컴포넌트 4개 작성**

`web/src/components/AuthCard.tsx`:

```tsx
import type { ReactNode } from 'react'

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="mb-6 text-xl font-semibold text-slate-900">{title}</h1>
        {children}
      </div>
    </div>
  )
}
```

`web/src/components/TextField.tsx`:

```tsx
import type { InputHTMLAttributes } from 'react'

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string
}

export function TextField({ label, error, id, ...rest }: Props) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-slate-900"
        {...rest}
      />
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  )
}
```

`web/src/components/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  pending?: boolean
}

export function Button({ pending, children, disabled, ...rest }: Props) {
  return (
    <button
      // 제출 중에는 비활성화해 중복 제출을 막는다.
      disabled={disabled || pending}
      className="w-full rounded-md bg-slate-900 px-3 py-2 font-medium text-white disabled:opacity-50"
      {...rest}
    >
      {pending ? '처리 중…' : children}
    </button>
  )
}
```

`web/src/components/FormError.tsx`:

```tsx
export function FormError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p>
}
```

- [ ] **Step 2: 라우트 가드 2개 작성**

`web/src/routes/RequireAuth.tsx`:

```tsx
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// 이 가드는 UX일 뿐이다. 실제 보안은 서버의 current_user/require_admin이 강제한다.
export function RequireAuth() {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    // 원래 가려던 경로를 기억해 두고, 로그인 성공 후 그곳으로 돌려보낸다.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
```

`web/src/routes/RequireGuest.tsx`:

```tsx
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export function RequireGuest() {
  const { user } = useAuth()

  if (user) {
    return <Navigate to="/dashboard" replace />
  }
  return <Outlet />
}
```

- [ ] **Step 3: 로그인 페이지 작성**

`web/src/pages/Login.tsx`:

```tsx
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'
import { Button } from '../components/Button'
import { FormError } from '../components/FormError'
import { TextField } from '../components/TextField'
import { ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/dashboard'

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    setPending(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        // 승인 대기·거절·비활성. 서버가 셋을 하나의 403으로 응답하므로 프론트도 구분하지 않는다.
        navigate('/pending', { replace: true })
        return
      }
      // 401 메시지는 서버가 계정 열거 방지를 위해 통일해 둔 문구다. 그대로 보여준다.
      setError(e instanceof ApiError ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthCard title="로그인">
      <form onSubmit={onSubmit} className="space-y-4">
        <FormError message={error} />
        <TextField
          id="email"
          label="이메일"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          id="password"
          label="비밀번호"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" pending={pending}>
          로그인
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        계정이 없으신가요?{' '}
        <Link to="/register" className="font-medium text-slate-900 underline">
          회원가입
        </Link>
      </p>
    </AuthCard>
  )
}
```

- [ ] **Step 4: 가입 대기 안내 페이지 작성**

`web/src/pages/PendingApproval.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'

// 폴링하지 않는 정적 안내 화면이다. 승인 여부는 다시 로그인해 보면 알 수 있다.
export function PendingApproval() {
  return (
    <AuthCard title="승인 대기 중">
      <p className="text-sm leading-relaxed text-slate-700">
        관리자 승인 후 로그인할 수 있습니다. 승인이 완료되면 다시 로그인해 주세요.
      </p>
      <p className="mt-6 text-center text-sm text-slate-600">
        <Link to="/login" className="font-medium text-slate-900 underline">
          로그인 화면으로
        </Link>
      </p>
    </AuthCard>
  )
}
```

- [ ] **Step 5: 대시보드(빈 화면) 작성**

`web/src/pages/Dashboard.tsx`:

```tsx
import { useAuth } from '../lib/auth'

// 앞으로 사이드바와 프로젝트 목록이 들어올 자리다. 지금은 인증 확인용 빈 화면.
export function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <header className="mx-auto flex max-w-3xl items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">대시보드</h1>
          <p className="mt-1 text-sm text-slate-600">
            {user?.email} · {user?.role}
          </p>
        </div>
        <button
          onClick={logout}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700"
        >
          로그아웃
        </button>
      </header>
    </div>
  )
}
```

- [ ] **Step 6: App을 실제 라우터로 교체**

`web/src/App.tsx` 전체를 아래로 교체 (Task 3의 임시 프로브를 버린다):

```tsx
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { PendingApproval } from './pages/PendingApproval'
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
      </Route>
      <Route path="/pending" element={<PendingApproval />} />
      <Route element={<RequireAuth />}>
        <Route path="/dashboard" element={<Dashboard />} />
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

> 이 시점에 `/register` 라우트는 아직 없다. 로그인 화면의 "회원가입" 링크를 누르면 `*` 규칙에 걸려 `/dashboard`(→ `/login`)로 돌아온다. Task 5에서 라우트를 추가하면 정상 동작한다.

- [ ] **Step 7: 빌드 확인**

Run: `cd web && npm run build`
Expected: TypeScript 컴파일 통과, 에러 없음

- [ ] **Step 8: 브라우저에서 로그인 슬라이스 확인**

백엔드(:8000)·프론트(:5173) 실행 상태에서:

1. http://localhost:5173/dashboard 접속 → 로그인 화면(`/login`)으로 리다이렉트된다.
2. 틀린 비밀번호로 로그인 → 폼 상단에 **"이메일 또는 비밀번호가 올바르지 않습니다."** 배너.
3. admin 계정(`scripts/seed_admin.py`로 만든 계정)으로 로그인 → `/dashboard`로 이동하고 이메일·role(admin)이 보인다.
4. **새로고침** → 대시보드에 그대로 머문다. `/login`으로 튕기는 깜빡임이 없다.
5. 로그인 상태에서 주소창에 `/login` 입력 → `/dashboard`로 돌아온다(RequireGuest).
6. 로그아웃 클릭 → `/login`으로 간다. 주소창에 `/dashboard`를 다시 쳐도 `/login`으로 막힌다.

- [ ] **Step 9: 커밋**

```bash
git add web/src
git commit -m "기능: 로그인·대기안내·대시보드 화면과 라우트 가드 추가"
```

---

## Task 5: 회원가입 화면 + 전체 흐름 검증

**Files:**
- Create: `web/src/pages/Register.tsx`
- Modify: `web/src/App.tsx` (`/register` 라우트 추가)

**Interfaces:**
- Consumes: Task 3의 `useAuth().register(email, password)`, `ApiError`. Task 4의 `AuthCard`, `TextField`, `Button`, `FormError`, `RequireGuest`.
- Produces: `/register` 라우트. 가입 성공 시 `/pending`으로 이동한다(로그인시키지 않는다).

- [ ] **Step 1: 회원가입 페이지 작성**

`web/src/pages/Register.tsx`:

```tsx
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'
import { Button } from '../components/Button'
import { FormError } from '../components/FormError'
import { TextField } from '../components/TextField'
import { ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

type FieldErrors = {
  email?: string
  password?: string
  confirm?: string
}

// 클라이언트 검증은 UX 보조일 뿐 신뢰 경계가 아니다. 진짜 검증은 서버가 한다.
function validate(email: string, password: string, confirm: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = '올바른 이메일 형식이 아닙니다.'
  }
  if (password.length < 8) {
    errors.password = '비밀번호는 8자 이상이어야 합니다.'
  }
  if (password !== confirm) {
    errors.confirm = '비밀번호가 일치하지 않습니다.'
  }
  return errors
}

export function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(undefined)

    const errors = validate(email, password, confirm)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return

    setPending(true)
    try {
      await register(email, password)
      // 가입한 사용자는 status=pending이라 로그인할 수 없다. 대기 안내로 보낸다.
      navigate('/pending', { replace: true })
    } catch (e) {
      // 409 = 이미 등록된 이메일. 서버 메시지를 그대로 보여준다.
      setError(e instanceof ApiError ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthCard title="회원가입">
      <form onSubmit={onSubmit} className="space-y-4">
        <FormError message={error} />
        <TextField
          id="email"
          label="이메일"
          type="email"
          autoComplete="email"
          required
          value={email}
          error={fieldErrors.email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          id="password"
          label="비밀번호"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          error={fieldErrors.password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          id="confirm"
          label="비밀번호 확인"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          error={fieldErrors.confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <Button type="submit" pending={pending}>
          가입하기
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        이미 계정이 있으신가요?{' '}
        <Link to="/login" className="font-medium text-slate-900 underline">
          로그인
        </Link>
      </p>
    </AuthCard>
  )
}
```

- [ ] **Step 2: `/register` 라우트 추가**

`web/src/App.tsx`에서 import 블록에 추가:

```tsx
import { Register } from './pages/Register'
```

`RequireGuest` 그룹 안에 라우트를 추가해 아래 형태로 만든다:

```tsx
      <Route element={<RequireGuest />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>
```

- [ ] **Step 3: 빌드 확인**

Run: `cd web && npm run build`
Expected: TypeScript 컴파일 통과, 에러 없음

- [ ] **Step 4: 전체 인증 흐름 수동 검증**

백엔드(:8000)·프론트(:5173) 실행 상태에서 아래를 순서대로 확인한다. 하나라도 실패하면 커밋하지 않는다.

1. `/register`에서 **비밀번호를 7자**로 입력하고 제출 → 필드 아래 "비밀번호는 8자 이상이어야 합니다." → 서버 요청이 나가지 않는다(Network 탭 확인).
2. **비밀번호 확인을 다르게** 입력하고 제출 → "비밀번호가 일치하지 않습니다."
3. 정상 값(`new-user@example.com` / `password123`)으로 가입 → **`/pending`으로 이동**하고 "승인 대기 중" 안내가 보인다.
4. 같은 이메일로 다시 가입 시도 → 폼 상단에 **"이미 등록된 이메일입니다."**(409)
5. 그 계정으로 `/login` 시도 → **`/pending`으로 이동**한다(403 → 대기 안내).
6. DB에서 승인 처리:
   ```bash
   docker compose exec db psql -U postgres -d studio -c "UPDATE users SET status='active' WHERE email='new-user@example.com';"
   ```
   (DB 사용자/DB명은 `docker-compose.yml`·`.env`의 값을 따른다.)
7. 다시 `/login` → **`/dashboard`** 진입, 이메일과 `member` role이 보인다.
8. **새로고침** → 대시보드 유지, 깜빡임 없음.
9. 로그아웃 → `/login`으로 이동. `/dashboard` 직접 접근 시 다시 `/login`으로 막힌다.

- [ ] **Step 5: 백엔드 회귀 확인**

Run: `uv run pytest -q && uv run ruff check`
Expected: 전체 통과 (Task 1에서 추가한 `/auth/me` 포함)

- [ ] **Step 6: 커밋**

```bash
git add web/src
git commit -m "기능: 회원가입 화면 추가 (클라이언트 검증 + 승인 대기 안내 연결)"
```

---

## 완료 조건

- `uv run pytest` 전체 통과, `uv run ruff check` 통과
- `cd web && npm run build` 통과
- Task 5 Step 4의 9개 항목이 브라우저에서 모두 확인됨

## 다음 Plan (이번 범위 밖)

1. `/admin/approvals` — 가입 승인 대기 목록·승인·거절 화면 (백엔드 API는 이미 존재: `GET /admin/users?status=pending`, `POST /admin/users/{id}/approve|reject`)
2. role 기반 사이드바 레이아웃 (설계 문서 5장)
3. 프로젝트 목록·생성 화면
