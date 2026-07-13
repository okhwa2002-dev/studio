# 인증 프론트 화면 설계 (Design Spec)

- **작성일:** 2026-07-13
- **범위:** 로그인 · 회원가입 · 가입 대기 안내 + 로그인 후 빈 대시보드 · 라우트 가드
- **선행:** 백엔드 인증 API 완료 (`docs/superpowers/plans/2026-07-10-plan2-auth.md`)
- **상위 설계:** `docs/superpowers/specs/2026-07-09-studio-design.md` (5장 통합 UI 구조)

---

## 1. 목표 & 범위

### 목표
인증 흐름이 **끝까지 도는 최소 단위**의 프론트엔드를 만든다.
회원가입 → 가입 대기 안내 → (관리자 승인) → 로그인 → 인증이 필요한 화면 진입 → 새로고침해도 로그인 유지 → 로그아웃.

### 범위에 포함
| 항목 | 내용 |
|------|------|
| 백엔드 | `GET /auth/me` 라우트 1개 추가 |
| 프론트 | `web/` 신규 생성 (Vite + React + TypeScript + Tailwind) |
| 화면 | `/login`, `/register`, `/pending`, `/dashboard`(빈 화면) |
| 인증 기반 | `AuthContext`, fetch 래퍼(401 자동 갱신), 라우트 가드 |

### 비범위 (이번엔 하지 않음)
- 관리자 승인 화면(`/admin/approvals`) — 다음 단계. 이번 단계에서 승인은 DB/스크립트로 처리한다.
- 사이드바 · 대시보드 실제 콘텐츠 · 프로젝트 화면
- 프론트 자동화 테스트(Vitest/Playwright) — 화면이 더 늘어난 뒤 도입
- 비밀번호 재설정, 이메일 인증, 소셜 로그인
- CORS 미들웨어 (Vite 프록시로 동일 출처가 되므로 불필요)

---

## 2. 백엔드 보완: `GET /auth/me`

### 왜 필요한가
인증 토큰은 **httpOnly 쿠키**에 담긴다. 이는 XSS로부터 토큰을 지키기 위한 의도된 설계이며, 그 대가로 **JS가 쿠키를 읽을 수 없다**. 따라서 프론트는 "지금 로그인돼 있는가, 누구인가"를 스스로 알아낼 방법이 없고, 서버에 물어봐야 한다. 이 질문에 답하는 엔드포인트가 현재 없다.

### 구현
`app/auth/router.py`에 추가한다. 기존 `current_user` 의존성이 이미 쿠키 검증 · 사용자 조회 · `status != active` 차단 · `password_hash` 제거까지 모두 수행하므로, 라우트는 그 결과를 골라 담기만 한다.

```python
@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return {"id": user["id"], "email": user["email"], "role": user["role"]}
```

- 인증되지 않았거나 토큰이 유효하지 않으면 `current_user`가 **401**을 던진다. 프론트는 이 401을 "비로그인"으로 해석한다.
- 응답 필드는 프론트가 실제로 쓰는 것만 노출한다(`id`, `email`, `role`). `password_hash`는 물론, 감사 컬럼·`approved_by` 등도 내보내지 않는다.

### 테스트 (pytest, 기존 통합 테스트 방식)
| 케이스 | 기대 |
|--------|------|
| 쿠키 없이 호출 | 401 |
| 유효하지 않은 토큰 | 401 |
| 로그인 후 호출 | 200, `{id, email, role}` |
| 응답 본문 | `password_hash` 키가 없음 |

---

## 3. 프론트 구조

### 스택
| 항목 | 선택 | 이유 |
|------|------|------|
| 빌드 | Vite | 상위 설계 확정 |
| 언어 | TypeScript | API 응답·User 모델을 타입으로 계약화 |
| 스타일 | Tailwind CSS | 화면이 늘어나도 스타일이 방대해지지 않음 |
| 라우팅 | React Router | 표준 |
| 상태 | React Context + fetch 래퍼 | 지금 규모(사용자 1개 상태)에 라이브러리는 과잉 |

### 디렉토리
```
web/
├─ index.html
├─ package.json
├─ vite.config.ts          # 프록시 설정
├─ tailwind.config.js
├─ tsconfig.json
└─ src/
   ├─ main.tsx             # 진입점
   ├─ App.tsx              # 라우터 + AuthProvider
   ├─ index.css            # Tailwind 지시자
   ├─ lib/
   │  ├─ api.ts            # fetch 래퍼 (아래 4장)
   │  └─ auth.tsx          # AuthContext / AuthProvider / useAuth
   ├─ routes/
   │  ├─ RequireAuth.tsx   # 미로그인 → /login
   │  └─ RequireGuest.tsx  # 로그인 상태로 인증 화면 접근 → /dashboard
   ├─ pages/
   │  ├─ Login.tsx
   │  ├─ Register.tsx
   │  ├─ PendingApproval.tsx
   │  └─ Dashboard.tsx
   └─ components/
      ├─ TextField.tsx     # label + input + 에러 메시지
      ├─ Button.tsx        # 로딩(pending) 상태 포함
      └─ FormError.tsx     # 폼 상단 서버 에러 배너
```

각 단위의 책임은 하나다. `api.ts`는 HTTP만 안다(인증 개념 없음). `auth.tsx`는 "현재 사용자"만 안다(화면 없음). 페이지는 폼과 표시만 안다(토큰 갱신 로직 없음).

### 프론트-백엔드 연결: Vite 프록시
```ts
// vite.config.ts
server: {
  proxy: {
    '/auth':   'http://localhost:8000',
    '/admin':  'http://localhost:8000',
    '/health': 'http://localhost:8000',
  },
}
```
브라우저 입장에서 프론트와 API가 **동일 출처**(`localhost:5173`)가 된다. 그 결과:
- CORS 설정이 필요 없다 (`CORSMiddleware`를 추가하지 않는다).
- 쿠키가 크로스 사이트가 아니므로 `SameSite=Lax`로 그대로 동작한다. `SameSite=None; Secure`가 필요 없다.
- 운영 배포 시에도 FastAPI가 빌드 결과물(`web/dist`)을 서빙하면 동일 출처가 유지된다 — 개발과 운영의 인증 조건이 같아진다.

**트레이드오프:** 프론트를 별도 도메인/CDN에 배포하려면 그때 CORS + CSRF 방어를 추가해야 한다. 로컬 PC를 서버로 쓰는 현 단계에서는 그 비용을 미루는 것이 맞다.

---

## 4. 인증 기반 (lib/api.ts, lib/auth.tsx)

### `api.ts` — fetch 래퍼
책임: HTTP 호출, 쿠키 동봉, 에러 정규화, 401 시 토큰 갱신 후 1회 재시도.

```ts
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message) }
}

async function request<T>(path: string, init?: RequestInit, retry = true): Promise<T>
```

- 모든 요청에 `credentials: 'include'` — 쿠키를 실어 보낸다.
- 응답이 실패면 본문 `{code, message}`(백엔드 전역 에러 형식)를 파싱해 `ApiError`로 던진다. 본문이 JSON이 아니면 기본 메시지로 대체한다.
- **401 자동 갱신:** 401을 받으면 `POST /auth/refresh`를 호출하고, 성공하면 **원래 요청을 딱 한 번** 재시도한다.
  - 재시도는 1회로 제한한다(`retry` 플래그). 무한 루프 방지.
  - `/auth/refresh`와 `/auth/login` 자체의 401은 갱신을 시도하지 않는다. 갱신이 갱신을 부르는 재귀를 막는다.
  - 갱신도 실패하면 원래의 401을 그대로 던진다 → 호출자(AuthContext)가 "로그아웃 상태"로 처리한다.

### `auth.tsx` — AuthContext
```ts
type User = { id: number; email: string; role: 'member' | 'admin' }

type AuthState = {
  user: User | null
  loading: boolean          // 최초 /auth/me 확인 중
  login(email, password): Promise<void>
  register(email, password): Promise<void>
  logout(): Promise<void>
}
```

- **마운트 시 `GET /auth/me`를 한 번 호출**해 세션을 복원한다. 200이면 `user` 설정, 401이면 `user = null`. 완료될 때까지 `loading = true`.
- `login()`은 `POST /auth/login`의 응답(`{id, email, role}`)을 그대로 `user`에 넣는다. 별도로 `/auth/me`를 또 부르지 않는다.
- `logout()`은 `POST /auth/logout` 후 `user = null`.
- `register()`는 사용자를 로그인시키지 않는다. 서버가 `status: pending`으로 만들기 때문에 애초에 로그인이 불가능하다.

### 앱 부팅 시 깜빡임 방지
`loading === true`인 동안에는 **어떤 라우트도 렌더하지 않고** 로딩 화면을 보여준다. 이 처리를 빼면, 새로고침할 때마다 `/auth/me` 응답이 오기 전의 `user = null` 상태를 가드가 읽고 로그인된 사용자를 순간적으로 `/login`으로 튕긴다.

### 라우트 가드
| 가드 | 조건 | 동작 |
|------|------|------|
| `RequireAuth` | `user === null` | `/login`으로 리다이렉트, 원래 가려던 경로를 `location.state`에 기억 → 로그인 성공 후 그곳으로 복귀 |
| `RequireGuest` | `user !== null` | 로그인 상태로 `/login`·`/register` 접근 시 `/dashboard`로 |

**이중 방어 원칙 유지:** 가드는 UX일 뿐이다. 보안은 서버의 `current_user`/`require_admin`이 강제한다.

---

## 5. 화면별 동작

### `/login` — 로그인
- 입력: 이메일, 비밀번호. 제출 중 버튼 비활성화(중복 제출 방지).
- 성공 → `user` 설정 후 원래 가려던 경로 또는 `/dashboard`로.
- **401** → 폼 상단에 서버 메시지 그대로 표시("이메일 또는 비밀번호가 올바르지 않습니다."). 서버가 계정 열거 방지를 위해 의도적으로 메시지를 통일했으므로, **프론트가 이를 세분화하지 않는다.**
- **403** → `/pending`으로 이동. 서버는 승인 대기·거절·비활성을 모두 403 하나로 응답하므로 프론트도 구분하지 않고 "승인 대기 안내" 화면으로 보낸다.
- 하단에 회원가입 링크.

### `/register` — 회원가입
- 입력: 이메일, 비밀번호, 비밀번호 확인.
- 클라이언트 검증(최소): 이메일 형식, 비밀번호 8자 이상, 확인 일치. 검증은 UX 보조일 뿐 신뢰 경계가 아니다.
- 성공(201) → 로그인시키지 않고 `/pending`으로.
- **409** → "이미 등록된 이메일입니다."(서버 메시지)
- 하단에 로그인 링크.

### `/pending` — 가입 대기 안내
- "관리자 승인 후 로그인할 수 있습니다" 안내와 로그인 화면 링크.
- 폴링하지 않는 정적 화면이다. 승인 여부는 사용자가 다시 로그인해 보면 알 수 있다.

### `/dashboard` — 대시보드 (빈 화면)
- `RequireAuth` 뒤에 위치.
- 현재 사용자의 이메일과 role 표시, 로그아웃 버튼. 그 외 콘텐츠 없음.
- 앞으로 프로젝트 목록·사이드바가 들어올 자리다.

### 라우트 표
| 경로 | 가드 | 화면 |
|------|------|------|
| `/login` | RequireGuest | Login |
| `/register` | RequireGuest | Register |
| `/pending` | 없음 | PendingApproval |
| `/dashboard` | RequireAuth | Dashboard |
| `/` | — | `/dashboard`로 리다이렉트 |
| 그 외 | — | `/dashboard`로 리다이렉트 (가드가 알아서 `/login`으로 보냄) |

---

## 6. 에러 처리

| 계층 | 방식 |
|------|------|
| 서버 | 전역 핸들러가 항상 `{code, message}` JSON으로 응답 (기존 규칙) |
| `api.ts` | 실패 응답 → `ApiError(status, code, message)`로 정규화 |
| 페이지 | `ApiError.status`로 분기(401/403/409), 사용자에게는 `message`를 그대로 표시 |
| 네트워크 오류 | "서버에 연결할 수 없습니다." 고정 메시지 |

**원칙:** 프론트는 사용자용 에러 문구를 자체 생성하지 않고 서버 메시지를 표시한다. 문구가 서버 한 곳에서 관리되고, 계정 열거 방지 같은 보안 의도가 프론트에서 무너지지 않는다.

---

## 7. 검증 방법

### 자동화
`GET /auth/me`의 pytest 통합 테스트(2장 표)를 **먼저 작성**하고 구현한다.

### 수동 (브라우저)
프론트는 이번 단계에서 자동화 테스트를 붙이지 않는다. 대신 아래 흐름을 브라우저에서 직접 확인한다.

1. `/register`에서 가입 → `/pending`으로 이동하는가
2. 그 계정으로 `/login` 시도 → 403 → `/pending`으로 가는가
3. DB에서 해당 사용자를 `status='active'`로 변경 (`UPDATE users SET status='active' WHERE email=...`)
4. 다시 `/login` → `/dashboard` 진입, 이메일·role이 표시되는가
5. **새로고침** → 로그인 상태가 유지되고, `/login`으로 튕기는 깜빡임이 없는가
6. 로그아웃 → `/login`으로 가고, 주소창에 `/dashboard`를 직접 쳐도 다시 `/login`으로 막히는가
7. 틀린 비밀번호로 로그인 → 통일된 401 메시지가 뜨는가

**근거:** 화면 4개, 자동화 테스트 하네스 도입 비용이 검증 가치를 넘어선다. E2E(Playwright)는 상위 설계에서도 선택 사항이며, 관리자 승인 화면까지 붙어 "가입→승인→로그인" 전 흐름이 UI로 완성된 뒤에 도입하는 것이 효율적이다.

---

## 8. 실행 방법 (README에 추가)

```
# 터미널 1 — API
uv run uvicorn app.main:app --reload      # :8000

# 터미널 2 — 프론트
cd web && npm install && npm run dev      # :5173
```
브라우저에서 http://localhost:5173 접속. API 호출은 Vite 프록시가 :8000으로 넘긴다.

---

## 9. 다음 단계 (이번 범위 밖)

1. `/admin/approvals` — 가입 승인 대기 목록·승인·거절 (백엔드 API는 이미 있음)
2. role 기반 사이드바 레이아웃 (상위 설계 5장)
3. 프로젝트 목록·생성 화면
