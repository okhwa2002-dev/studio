# 관리자 비밀번호 초기화 설계

- 작성일: 2026-07-30
- 범위: 관리자의 사용자 비밀번호 초기화 + 초기화된 계정의 비밀번호 변경 강제

## 1. 목적과 범위

사용자가 비밀번호를 잊으면 현재는 복구할 방법이 없다. `/auth/change-password`는 현재 비밀번호를 요구하고, 관리자용 재설정 API도 없어서 결국 psql로 내려가야 한다. 관리자가 사용자 관리 화면에서 비밀번호를 초기화할 수 있게 한다.

초기 비밀번호는 고정값 `qwer1234`다. 랜덤 문자 발급은 다음 단계로 미루되, **API 응답이 처음부터 발급된 비밀번호를 담는 형태로** 설계해 그때 프론트를 고치지 않아도 되게 한다.

`qwer1234`는 모두가 아는 값이라 초기화 후 방치되면 그 계정은 이메일만 아는 사람이 바로 들어올 수 있다. 그래서 초기화와 **변경 강제를 한 작업으로 묶는다** — 강제가 없으면 이 기능은 계정을 복구하는 대신 열어두는 셈이 된다.

**하는 것**

- 관리자 → 사용자 상세 팝업에서 비밀번호 초기화
- 초기화된 계정은 비밀번호를 바꾸기 전까지 다른 화면·API를 쓸 수 없다
- 초기화 시 잠김·로그인 실패 횟수 해제, 그 사용자의 기존 세션 전부 폐기

**하지 않는 것**

- 랜덤 임시 비밀번호 — 다음 단계. 응답 형태만 미리 맞춰 둔다
- 이메일·SMS 발송 — 관리자가 사용자에게 직접 전달한다. 메일 발송 인프라가 프로젝트에 없다
- 사용자 스스로 하는 "비밀번호 찾기" — 본인 확인 수단(메일 등)이 필요해 별개 작업이다
- 임시 비밀번호 유효기간 — 초기화 즉시 변경이 강제되므로 기한을 둘 대상이 없다
- 관리자 본인의 비밀번호 초기화 (2-3)
- 초기화 이력 테이블 — `updated_by`로 마지막 처리자만 남긴다. 감사 로그는 프로젝트 전반에 없는 기능이라 이 작업에서 도입하지 않는다

## 2. 데이터 모델

### 2-1. `users.must_change_password` 추가

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `must_change_password` | BOOLEAN NOT NULL `false` | 다음 로그인 시 비밀번호 변경을 강제할지 (관리자 초기화 시 true) |

`app/models/user.py`의 `unlocked_at` 아래, 감사 컬럼 앞에 선언한다(컬럼 순서 규칙: `id` → 업무 컬럼 → 감사 컬럼).

```python
must_change_password: bool = Field(
    default=False,
    sa_column_kwargs={
        "server_default": "false",
        "comment": "관리자 초기화 후 비밀번호 변경 강제 여부 (true=변경 전까지 다른 API 차단)",
    },
)
```

`server_default`를 두는 이유는 `failed_login_count`와 같다 — raw SQL `insert_user`가 이 컬럼을 넘기지 않으므로 DB가 기본값을 채워야 한다. 기존 사용자는 마이그레이션 후 전부 `false`가 된다.

**별도 테이블이나 `password_reset_tokens`를 두지 않는다.** 토큰 기반 재설정은 "사용자가 링크를 받아 스스로" 하는 흐름에 필요한 것이고, 여기서는 관리자가 비밀번호를 직접 정해서 알려준다. 불리언 한 컬럼으로 끝난다.

### 2-2. 초기 비밀번호 상수

`app/auth/security.py`에 둔다.

```python
# 관리자 초기화 시 설정되는 고정 비밀번호. 즉시 변경이 강제되므로(must_change_password)
# 이 값이 계정에 남아 있는 구간은 사용자가 첫 로그인해서 바꾸기 전까지다.
# 추후 랜덤 문자 발급으로 대체한다 — 그때 이 상수 대신 생성 함수를 쓰면
# 호출부(admin_router)와 응답 형태는 그대로 둘 수 있다.
INITIAL_PASSWORD = "qwer1234"
```

`security.py`에 두는 이유: 비밀번호 해싱·토큰 생성이 이미 여기 모여 있고, 랜덤 발급으로 넘어갈 때 생성 함수가 들어갈 자리도 여기다.

**`password_min_len` 정책 검증을 거치지 않는다.** 관리자가 시스템 설정에서 최소 길이를 9 이상으로 올리면 `qwer1234`(8자)는 정책 미달이 된다. 로그인 경로는 길이를 검증하지 않으므로 동작에 문제는 없고, 어차피 즉시 변경이 강제되며 새 비밀번호는 정책을 통과해야 한다. 랜덤 발급으로 넘어갈 때 `min_len`에 맞춰 길이를 정하면 이 어긋남은 사라진다.

### 2-3. 초기화 대상 제한

**관리자 본인은 초기화할 수 없다.** 다른 관리자는 초기화할 수 있다.

본인을 막는 이유는 두 가지다. 자기 비밀번호를 `qwer1234`로 만들 이유가 없고(설정 화면에 변경 기능이 이미 있다), 초기화가 세션을 전부 폐기하므로 본인에게 실행하면 스스로 로그아웃된 뒤 강제 변경 화면에 갇힌다 — 복구는 되지만 실수로 눌렀을 때 겪을 일이 아니다.

다른 관리자를 허용하는 이유: 관리자가 비밀번호를 잃었을 때 psql로 내려가지 않을 유일한 경로다. 관리자 A가 B의 비밀번호를 바꿔 B 계정으로 들어갈 수 있다는 점은 인정하고 넘어간다 — 이미 관리자는 서로의 계정 상태를 바꿀 수 있고(승인·거절·잠금 해제), 관리자 권한 자체가 신뢰 경계다.

**사용자 상태(`PENDING`·`REJECTED`·`DISABLED`)로는 제한하지 않는다.** 그 계정들은 로그인 자체가 막혀 있어 초기화가 무해하고, 상태별로 막으면 "가입 직후 비밀번호를 잊은 대기 사용자"에게 승인 → 초기화 두 단계를 강요하게 된다. 로그인 가능 여부는 `login`과 `current_user`가 이미 `status`로 판정한다.

## 3. 백엔드

### 3-1. 초기화 API — `app/auth/admin_router.py`

| 메서드 | 경로 | 동작 |
|---|---|---|
| POST | `/api/admin/users/{user_id}/reset-password` | 비밀번호를 초기값으로 되돌리고 변경을 강제한다 |

`require_admin` 의존. 같은 파일의 `unlock_user`·`reset_failed_login`과 같은 모양으로 둔다.

처리 순서:

1. `user_id == admin["id"]` → `Errors.bad_request("본인 비밀번호는 이 화면에서 초기화할 수 없습니다. 설정 화면을 이용하세요.")`
2. 대상 조회, 없으면 `Errors.not_found("사용자를 찾을 수 없습니다.")`
3. `await asyncio.to_thread(hash_password, INITIAL_PASSWORD)`
4. `admin_reset_password` 쿼리 실행
5. `revoke_all_for_user` — 그 사용자의 refresh token 전부 폐기
6. commit
7. 응답 `{"id": user_id, "temp_password": INITIAL_PASSWORD, "unlocked_at": now}`

`unlocked_at`을 응답에 담는 이유는 `unlock_user`와 같다 — 화면이 목록을 다시 불러오지 않고 그 행만 갱신하므로, 서버가 정한 시각을 알려주지 않으면 `해제일시` 컬럼이 다음 조회까지 비어 보인다.

**`hash_password`를 `asyncio.to_thread`로 넘긴다.** argon2는 의도적으로 느린 동기 CPU 작업이라 `async def` 안에서 그대로 호출하면 이벤트 루프가 그 시간만큼 멈춘다(SSE ping과 다른 요청까지 함께 밀린다). 기존 login/register 경로에도 같은 문제가 있지만 그 수정은 이 작업의 범위가 아니다 — 새로 쓰는 코드만 올바르게 둔다.

**기존 세션을 폐기하는 이유.** 폐기하지 않으면 이미 로그인된 기기는 옛 access/refresh 토큰으로 계속 돌아다닌다. `current_user`가 매 요청 DB를 조회하므로 게이트(3-3) 자체는 걸리지만, 초기화의 동기가 "계정이 탈취된 것 같다"인 경우 공격자 세션을 끊는 것이 목적이므로 명시적으로 폐기한다. `change-password`가 같은 이유로 이미 그렇게 한다.

**응답에 `temp_password`를 담는다.** 지금은 고정값이라 프론트가 상수로 가질 수도 있지만, 랜덤 발급으로 바뀌면 서버만 아는 값이 된다. 처음부터 응답값을 표시하게 만들어 두면 그때 백엔드 한 줄만 고치면 된다. 평문 비밀번호가 응답 본문에 실리지만, 관리자가 사용자에게 전달해야 하는 값이고 이 프로젝트는 응답 본문을 로그에 남기지 않는다(`LOG_SQL`도 파라미터 값을 제외한다).

### 3-2. `app/queries/users.sql`

`admin_reset_failed_login` 아래에 추가한다.

```sql
-- name: admin_reset_password!
-- 관리자가 비밀번호를 초기값으로 되돌린다. 변경 강제 플래그를 켜고, 잠김·실패 횟수도
-- 함께 푼다 — 비밀번호를 잊어 연속 실패로 잠긴 계정이 가장 흔한 초기화 대상이라,
-- 관리자가 [잠금 해제]를 따로 누르게 할 이유가 없다.
UPDATE users
SET password_hash = :password_hash,
    must_change_password = TRUE,
    failed_login_count = 0,
    locked_at = NULL,
    unlocked_at = :unlocked_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
```

`unlocked_at`도 채운다 — 목록의 `해제일시` 컬럼이 이 값을 읽으므로, 잠긴 계정을 초기화로 풀었을 때 `unlock_user`로 푼 것과 화면에 같이 나타나야 한다.

기존 `update_password`에 한 줄을 더한다.

```sql
-- name: update_password!
-- 본인이 설정 화면(또는 강제 변경 화면)에서 비밀번호를 바꾼다. updated_by는 본인 id다.
-- must_change_password를 함께 내려 강제 변경을 해제한다 — 본인이 비밀번호를 바꾸는
-- 유일한 경로라 여기 한 곳이면 충분하고, 일반 변경에서도 false가 항상 맞는 값이다.
UPDATE users
SET password_hash = :password_hash,
    must_change_password = FALSE,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
```

`find_by_id`·`find_by_email`·`list_by_status`·`list_all`의 SELECT 목록에 `must_change_password`를 추가한다. 앞의 둘은 게이트와 로그인 응답이, 뒤의 둘은 관리자 목록이 이 값을 쓴다.

### 3-3. 변경 강제 게이트 — `app/auth/dependencies.py`

`current_user`가 `must_change_password`인 사용자를 403으로 거절한다. 허용 경로는 세 개다.

```python
# must_change_password 상태에서도 통과시키는 경로.
# - /auth/me: 프론트가 "지금 강제 변경 상태"임을 알아야 화면을 띄울 수 있다
# - /auth/change-password: 유일한 탈출구
# - /auth/logout: 로그아웃은 언제나 막지 않는다
_PASSWORD_CHANGE_ALLOWED = frozenset({
    "/api/auth/me",
    "/api/auth/change-password",
    "/api/auth/logout",
})
```

`current_user`의 `status` 검사 뒤, `password_hash`를 지우기 전에 넣는다.

```python
if row["must_change_password"] and request.url.path not in _PASSWORD_CHANGE_ALLOWED:
    raise AppError(403, "PASSWORD_CHANGE_REQUIRED", "비밀번호를 변경해야 계속할 수 있습니다.")
```

`/auth/policy`(최소 길이 조회)와 `/auth/refresh`는 `current_user`를 쓰지 않으므로 목록에 없어도 통과한다. 강제 변경 화면은 이 둘을 모두 필요로 한다 — 최소 길이 표시와 토큰 갱신.

경로를 `/api` 접두사까지 포함한 절대 경로로 비교한다. `main.py`가 라우터를 `prefix="/api"`로 등록하므로 `request.url.path`에는 접두사가 붙어 있다.

**프론트 라우팅만으로 막지 않는 이유.** `RequireAuth`의 주석이 "가드는 UX일 뿐이고 실제 보안은 서버가 강제한다"고 못 박아 둔 프로젝트다. 게이트가 프론트에만 있으면 API를 직접 호출해 우회할 수 있고, 그러면 "강제"라고 부를 수 없다.

**로그인 자체를 막거나 별도의 변경 전용 토큰을 발급하지 않는다.** 더 엄격하지만 JWT 종류가 둘로 늘고 검증이 분기한다. 게이트 한 곳으로 같은 효과를 얻으므로 이 규모에 맞지 않는다.

### 3-4. 로그인·`/auth/me` 응답

두 응답에 `must_change_password`를 추가한다.

```python
# login
return {"id": ..., "email": ..., "role": ..., "name": ...,
        "must_change_password": row["must_change_password"]}
```

**양쪽 모두 필요하다.** 프론트의 `login`은 응답을 그대로 `setUser`에 쓰고 `/auth/me`를 다시 부르지 않는다(auth.tsx 주석). `/auth/me`만 고치면 로그인 직후에는 플래그가 `undefined`여서 첫 화면에서 게이트가 통과해 버린다.

로그인은 `must_change_password`여도 정상적으로 성공하고 쿠키를 내려준다. 막는 것은 게이트의 몫이다 — 로그인이 실패하면 사용자는 비밀번호를 바꿀 방법이 없다.

### 3-5. `change_password`의 동작 변화

`update_password` 쿼리가 플래그를 내리므로 핸들러 코드는 그대로다. 강제 변경 화면도 이 엔드포인트를 그대로 쓴다 — 사용자는 관리자가 알려준 임시 비밀번호를 `current_password`로 넣는다.

`SAME_PASSWORD` 검사가 여기서 유용하게 작동한다. 임시 비밀번호를 그대로 새 비밀번호로 넣으면 400으로 거절되므로, `qwer1234`를 유지한 채 게이트를 빠져나갈 수 없다.

## 4. 프론트엔드

### 4-1. 타입과 API 클라이언트

`web/src/lib/auth.tsx`의 `User`에 `must_change_password: boolean` 추가.

`web/src/lib/admin.ts`:

```ts
export type AdminUser = {
  // ...기존 필드
  must_change_password: boolean
}

export const adminUsers = {
  // ...기존
  resetPassword: (id: number) =>
    api.post<{ id: number; temp_password: string; unlocked_at: string }>(
      `/admin/users/${id}/reset-password`,
    ),
}
```

### 4-2. 사용자 상세 팝업 — `AdminUsers.tsx`

`UserDetailModal`에 `비밀번호` 행을 추가한다. 자리는 `로그인 실패 횟수` 위, `상태` 아래다 — 계정 정보(이름·이메일·역할·상태·비밀번호)와 잠금 관련 정보(실패 횟수·잠김·해제일시)를 섞지 않는다.

```
┌─ 모달: 회원 상세 ─────────────────────────────┐
│ 이름                                홍길동   │
│ 이메일                    user@example.com   │
│ 역할                                  일반   │
│ 상태                                [활성]   │
│ 비밀번호                          [초기화]   │
│ 로그인 실패 횟수                 3 [초기화]  │
│ 계정 잠김            잠김 (2026-07-30 14:02) │
│ ...                                          │
└──────────────────────────────────────────────┘
```

`[초기화]` 클릭 시 확인 단계를 거친다. 실패 횟수 초기화와 달리 되돌릴 수 없고 사용자를 로그아웃시키기 때문이다. 다른 관리자 화면의 삭제가 `window.confirm`을 쓰므로 같은 방식으로 맞춘다.

> 홍길동(user@example.com)의 비밀번호를 초기화하시겠습니까?
> 이 사용자의 모든 로그인 세션이 종료되고, 다음 로그인 시 새 비밀번호를 설정해야 합니다.

성공하면 같은 행이 발급된 비밀번호로 바뀐다.

```
│ 비밀번호      임시: qwer1234 [복사] ✓ 초기화됨 │
```

값은 응답의 `temp_password`를 그대로 표시한다 — 프론트에 `qwer1234`를 상수로 두지 않는다. 랜덤 발급으로 바뀌면 이 화면은 수정 없이 새 값을 보여준다. `[복사]`는 `navigator.clipboard.writeText`이고, 관리자가 사용자에게 전달할 값이므로 눈으로 옮겨 적게 하지 않는다.

**로그인한 관리자 본인 행에서는 버튼을 감춘다.** 서버가 400으로 막지만, 누를 수 있는 버튼이 항상 실패하면 그것이 버그로 보인다. `useAuth().user.id`와 비교한다.

초기화 성공 시 부모의 `rows`·`selected`를 갱신한다 — 모달 안의 액션인 `resetFailures`가 이미 하는 방식과 같다(목록의 `[잠금 해제]` 버튼은 `load()`로 전체를 다시 불러오지만, 그건 처리된 사용자가 현재 탭에서 빠지는 경우다. 비밀번호 초기화는 상태를 바꾸지 않아 행이 그대로 남으므로 다시 불러올 이유가 없다).

갱신 값은 `{ must_change_password: true, failed_login_count: 0, locked_at: null, unlocked_at: <응답의 unlocked_at> }`이다. 서버가 UPDATE하는 컬럼과 정확히 일치하므로 화면과 DB가 어긋나지 않는다.

목록에 `강제 변경 대기` 같은 컬럼을 추가하지 않는다. 관리 컬럼이 이미 9개고, 이 상태는 사용자가 로그인해서 바꾸면 저절로 사라지는 과도기 값이다. 상세 팝업의 `비밀번호` 행에 `초기화됨 (변경 대기)`로 표시하면 충분하다.

### 4-3. 강제 변경 화면 — `web/src/pages/ChangePasswordRequired.tsx`

```
┌─ 비밀번호 변경 필요 ──────────────────┐
│ 관리자가 비밀번호를 초기화했습니다.   │
│ 계속하려면 새 비밀번호를 설정하세요.  │
│                                       │
│ 임시 비밀번호  [················]     │
│ 새 비밀번호    [················]     │
│ 새 비밀번호 확인 [··············]     │
│                                       │
│           [변경하기]                  │
│           로그아웃                    │
└───────────────────────────────────────┘
```

`AuthCard`를 쓴다 — 사이드바·상단바 없는 전체 화면이다([PendingApproval](../../../web/src/pages/PendingApproval.tsx)과 같은 결). 강제 변경 중에는 다른 메뉴가 눌러도 403만 나므로 보이지 않는 편이 맞다.

폼은 `Settings.tsx`의 `ChangePasswordModal`과 같은 구조다(3개 입력, `usePasswordMinLen`으로 최소 길이 검증, `TextField`, `FormError`). `현재 비밀번호` 라벨만 `임시 비밀번호`로 바꾸고 "관리자가 안내한 비밀번호를 입력하세요" 도움말을 붙인다.

**`ChangePasswordModal`을 공용 컴포넌트로 추출하지 않는다.** 하나는 모달이고 하나는 전체 화면이며, 취소 버튼 유무·성공 후 동작(모달 닫기 vs 대시보드 이동)·라벨·도움말이 다르다. 공용화하면 두 화면의 차이를 전부 props로 받는 컴포넌트가 되어, 지금 두 파일에 나뉘어 있는 것보다 읽기 어려워진다. 폼 구조가 40줄 정도라 중복을 감수한다.

성공하면 서버가 쿠키를 회전해 세션이 유지된다. `/auth/me`를 다시 불러 `user`를 갱신하고(플래그가 `false`로 내려온다) `/dashboard`로 이동한다. `auth.tsx`에 `refresh()`를 추가해 `AuthProvider` 밖에서 `setUser`를 부르지 않게 한다.

`로그아웃` 링크를 둔다 — 관리자에게 임시 비밀번호를 다시 물어봐야 하는 사용자가 화면에 갇히지 않아야 한다.

### 4-4. 라우팅 — `App.tsx`, `RequireAuth.tsx`

`/change-password`를 `RequireAuth` 안, `AppLayout` **밖**에 둔다.

```tsx
<Route element={<RequireAuth />}>
  <Route path="/change-password" element={<ChangePasswordRequired />} />
  <Route element={<AppLayout />}>
    {/* 기존 라우트 */}
  </Route>
</Route>
```

`RequireAuth`가 양방향으로 가드한다.

```tsx
// 강제 변경 상태면 그 화면 외에는 아무 데도 못 간다(서버도 403으로 막는다).
// 반대로 플래그가 내려간 뒤 이 경로에 남아 있으면 대시보드로 돌려보낸다.
const mustChange = user.must_change_password
const atChangePage = location.pathname === '/change-password'
if (mustChange && !atChangePage) return <Navigate to="/change-password" replace />
if (!mustChange && atChangePage) return <Navigate to="/dashboard" replace />
```

로그인 직후 경로는 `/login` → (`RequireGuest`가) `/dashboard` → (`RequireAuth`가) `/change-password`로 두 번 튄다. `RequireGuest`에도 같은 판단을 넣으면 한 번에 갈 수 있지만, 그러면 플래그를 보는 곳이 두 곳이 되어 한쪽만 고치는 실수가 생긴다. 리다이렉트는 네트워크 왕복 없는 렌더 한 번이므로 게이트를 `RequireAuth` 한 곳에만 둔다.

`Login.tsx`는 고치지 않는다 — 로그인 성공 후의 이동은 이미 라우팅이 결정한다.

### 4-5. 신규·수정 파일

| 파일 | 내용 |
|---|---|
| `alembic/versions/*_add_must_change_password.py` | 컬럼 추가 (신규) |
| `app/models/user.py` | `must_change_password` 필드 |
| `app/auth/security.py` | `INITIAL_PASSWORD` 상수 |
| `app/queries/users.sql` | `admin_reset_password` 추가, `update_password` 수정, SELECT 4곳에 컬럼 추가 |
| `app/auth/admin_router.py` | `reset_password` 엔드포인트 |
| `app/auth/dependencies.py` | 강제 변경 게이트 |
| `app/auth/router.py` | `login`·`me` 응답에 플래그 추가 |
| `web/src/lib/auth.tsx` | `User` 타입 + `refresh()` |
| `web/src/lib/admin.ts` | `AdminUser` 타입 + `resetPassword` |
| `web/src/pages/admin/AdminUsers.tsx` | 상세 팝업의 비밀번호 행 |
| `web/src/pages/ChangePasswordRequired.tsx` | 강제 변경 화면 (신규) |
| `web/src/App.tsx` | `/change-password` 라우트 |
| `web/src/routes/RequireAuth.tsx` | 양방향 가드 |
| `docs/schema.sql` | `users` DDL에 컬럼 추가 |

`docs/schema.sql`은 머리말에 "테이블을 추가/변경할 때마다 갱신한다"고 적혀 있고 `users`는 이미 들어 있으므로 컬럼 한 줄을 더한다. 이 파일에 빠져 있는 다른 테이블 backfill은 범위 밖이다.

## 5. 에러 처리

**백엔드** — 도메인 오류는 `Errors.*`/`AppError`로 던지고 `main.py`의 핸들러가 `{code, message}`로 응답한다.

| 상황 | 응답 |
|---|---|
| 본인 초기화 시도 | 400 `BAD_REQUEST` |
| 없는 사용자 | 404 `RESOURCE_NOT_FOUND` |
| MEMBER의 호출 | 403 `FORBIDDEN` (`require_admin`) |
| 강제 변경 중 다른 API 호출 | 403 `PASSWORD_CHANGE_REQUIRED` |

**프론트엔드**

| 상황 | 처리 |
|---|---|
| 초기화 실패 | 상세 팝업 안에 `FormError`, 팝업은 닫지 않음 |
| 강제 변경 실패 | 화면 안에 `FormError` (임시 비밀번호 오입력이 가장 흔하다) |
| 클립보드 복사 실패 | 조용히 넘어간다. 값이 화면에 그대로 보이므로 손으로 옮겨 적을 수 있고, 실패를 알려도 사용자가 할 수 있는 일이 없다 |

`PASSWORD_CHANGE_REQUIRED` 403을 프론트가 전역에서 특별 처리하지 않는다. 라우팅 가드가 그 상태의 사용자를 애초에 다른 화면으로 보내지 않으므로, 이 응답은 정상 흐름에서 나오지 않는다.

## 6. 테스트

**백엔드** (기존 conftest의 testcontainers DB 픽스처 사용)

`tests/test_admin_reset_password.py` (신규)

- 초기화 성공: 200, 응답에 `temp_password`가 있고, 그 값으로 로그인이 성공한다
- 초기화 후 `must_change_password`가 true다
- 잠기고 실패 횟수가 쌓인 계정을 초기화하면 `locked_at`이 NULL, `failed_login_count`가 0, `unlocked_at`이 채워진다
- 초기화가 그 사용자의 기존 refresh token을 모두 폐기한다 (초기화 전 발급한 토큰으로 `/auth/refresh` → 401)
- 다른 사용자의 refresh token은 폐기되지 않는다
- 본인 id로 호출하면 400
- 없는 user_id면 404
- MEMBER 권한이면 403
- `updated_by`에 관리자 id가 남는다

`tests/test_password_change_required.py` (신규)

- `must_change_password`인 사용자의 `/api/projects` 호출 → 403 `PASSWORD_CHANGE_REQUIRED`
- 같은 사용자의 `/api/auth/me` → 200, 응답에 `must_change_password: true`
- 같은 사용자의 `/api/auth/change-password` → 통과
- 같은 사용자의 `/api/auth/logout` → 통과
- 변경 후 `must_change_password`가 false가 되고 `/api/projects`가 다시 열린다
- 임시 비밀번호를 그대로 새 비밀번호로 제출하면 400 `SAME_PASSWORD`이고 플래그가 그대로 true다
- 관리자 계정이 초기화당한 경우 `/api/admin/users`도 403이다 (`require_admin`이 `current_user`를 거치므로 자동이지만, 게이트가 관리자에게도 적용되는지 명시적으로 고정한다)

기존 테스트 수정

- `tests/test_auth_login.py` — 로그인 응답에 `must_change_password`가 포함된다
- `tests/test_auth_me.py` — `/auth/me` 응답에 포함된다
- `tests/test_auth_change_password.py` — 변경이 플래그를 내린다
- `tests/test_admin_users.py` — 목록 응답에 포함된다
- `tests/test_alembic_migration.py` — 새 리비전 추가 후 왕복이 통과하는지 확인 (수정 없음)

**프론트엔드**는 이 프로젝트에 자동화 테스트가 없다. 수동 확인 항목만 남긴다.

- 관리자가 사용자 비밀번호를 초기화 → 임시 비밀번호가 표시되고 복사된다
- 관리자 본인 행의 상세 팝업에는 초기화 버튼이 없다
- 그 사용자로 `qwer1234` 로그인 → 강제 변경 화면이 뜨고, 주소창에 `/dashboard`를 직접 입력해도 되돌아온다
- 강제 변경 화면에 사이드바·상단바가 없다
- 임시 비밀번호를 새 비밀번호로 그대로 넣으면 오류 메시지가 뜬다
- 새 비밀번호로 변경 → 대시보드로 이동하고 이후 정상 이용된다
- 강제 변경 화면에서 로그아웃이 동작한다
- 초기화된 사용자의 다른 기기 세션이 끊긴다 (두 브라우저로 확인)
- 잠긴 계정을 초기화하면 목록의 잠김 뱃지가 사라진다
- 다크모드에서 임시 비밀번호 표시·복사 버튼이 깨지지 않는다

## 7. 구현 순서

1. 모델 + `INITIAL_PASSWORD` 상수 + alembic 리비전 + `docs/schema.sql`
2. `users.sql` 쿼리 (신규 1개, 수정 5개)
3. 초기화 API + `tests/test_admin_reset_password.py`
4. 게이트 + 로그인·`/auth/me` 응답 + `tests/test_password_change_required.py` + 기존 테스트 수정
5. 프론트 타입·API 클라이언트 (`auth.tsx`, `admin.ts`)
6. 강제 변경 화면 + 라우팅 가드
7. 상세 팝업의 초기화 버튼

백엔드를 먼저 끝낸다. 게이트(4)가 프론트보다 앞서야 6·7을 실제 응답으로 확인할 수 있고, 화면(7)을 먼저 만들면 초기화된 계정으로 로그인할 곳이 없어 흐름 전체를 볼 수 없다.
