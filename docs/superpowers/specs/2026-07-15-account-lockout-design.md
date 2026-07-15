# 계정 잠금 관리 설계 (Design Spec)

- **작성일:** 2026-07-15
- **범위:** 연속 로그인 실패 시 계정 잠금(관리자 수동 해제) + 관리자 화면 표시·해제
- **선행:** 인증 백엔드/프론트 완료, 사용자 관리 목록 화면 완료 (`docs/superpowers/specs/2026-07-15-admin-users-list-design.md`)
- **상위 설계:** `docs/superpowers/specs/2026-07-09-studio-design.md`

---

## 1. 목표 & 범위

### 목표
연속 로그인 실패를 세어 임계치(기본 5회)에서 계정을 잠그고, 관리자가 사용자 관리 화면에서 잠김 상태를 보고 수동으로 해제할 수 있게 한다.

### 확정된 결정
| 항목 | 결정 |
|------|------|
| 해제 방식 | **관리자 수동 해제만** (시간 기반 자동 해제 없음) |
| "해제일시" 의미 | 관리자가 잠금을 푼 시각 (감사 기록) |
| 임계치 | 연속 실패 **5회** (설정값 `failed_login_limit`으로 조정 가능) |
| 잠금과 상태 | **직교(orthogonal).** ACTIVE이면서 잠긴 상태가 가능. 별도 필드로 관리(status에 잠금 값을 넣지 않음). |
| 범위 | 백엔드(스키마·로그인 로직·해제 API) + 관리자 UI(표시·해제 버튼) |

### 비범위 (YAGNI)
- 시간 기반 자동 해제, 관리자 예약 해제
- IP 기반 잠금·레이트리밋, CAPTCHA
- 사용자 셀프 서비스 해제(이메일 링크 등)
- 잠금/해제 이벤트 별도 감사 로그 테이블 (컬럼으로만 기록)

---

## 2. 데이터 모델 (`app/models/user.py`)

`User`에 컬럼 3개 추가. 잠금은 status와 별개다.

| 컬럼 | 타입 | 제약/기본 | 의미 |
|------|------|-----------|------|
| `failed_login_count` | `int` | NOT NULL, default 0 | 연속 로그인 실패 횟수. 성공 시 0으로 리셋. |
| `locked_at` | `datetime` | NULL | 잠긴 시각. **NULL = 안 잠김, 값 있음 = 잠김.** 잠김여부는 이 값으로 파생한다. |
| `unlocked_at` | `datetime` | NULL | 관리자가 마지막으로 잠금을 푼 시각(해제일시, 감사용). |

- **별도 `is_locked` 불리언을 두지 않는다** — `locked_at IS NOT NULL`로 파생해 진실의 출처를 하나로 유지한다.
- 날짜 컬럼은 기존 감사 컬럼과 같은 규칙: `DateTime(timezone=False)`, 로컬 벽시계(`now_local()`)로 저장.
- 모델 선언 위치: 기존 업무 컬럼(`approved_by`) 다음, 감사 컬럼(`created_at` 등) 앞. 컬럼 순서 규칙(id → 업무 → 감사)을 지킨다.

### 설정 (`app/config.py`)
```python
failed_login_limit: int = 5
```

### 마이그레이션 (alembic, 수기 작성)
```python
def upgrade():
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0', comment='연속 로그인 실패 횟수'))
    op.add_column('users', sa.Column('locked_at', sa.DateTime(), nullable=True, comment='계정 잠긴 시각 (NULL=안 잠김)'))
    op.add_column('users', sa.Column('unlocked_at', sa.DateTime(), nullable=True, comment='관리자가 잠금 해제한 시각'))

def downgrade():
    op.drop_column('users', 'unlocked_at')
    op.drop_column('users', 'locked_at')
    op.drop_column('users', 'failed_login_count')
```
- `failed_login_count`는 `server_default='0'`으로 기존 행을 0으로 채운다.

---

## 3. 로그인 흐름 변경 (`app/auth/router.py`의 `login`)

현재 순서(비밀번호 검증 → status 확인 → 토큰 발급)에 잠금 로직을 끼운다. `find_by_email`이 이미 반환하도록 컬럼을 넓힌다(4장).

### 분기
1. **이메일 없음** → 기존과 동일: 더미 해시로 `verify_password` 호출(타이밍 방어) 후 통일 401. (셀 수 있는 계정이 없으므로 카운트 없음.)
2. **비밀번호 틀림** →
   - `new_count = row["failed_login_count"] + 1`
   - `locked_at`을 계산: 이미 잠겼으면(`row["locked_at"]` 있음) 그대로 유지, 아니면 `new_count >= failed_login_limit`일 때 `now`, 그 외 `None`.
   - `record_failed_login(id, failed_login_count=new_count, locked_at=<계산값>, updated_at=now)` 한 번의 UPDATE. commit.
   - **항상 통일된 401** 반환("이메일 또는 비밀번호가 올바르지 않습니다.").
3. **비밀번호 맞음 + 잠김(`row["locked_at"]` 있음)** → 토큰 발급 없이 **423 Locked**("계정이 잠겼습니다. 관리자에게 문의하세요."). 카운트·잠금 변경 없음.
4. **비밀번호 맞음 + status ≠ ACTIVE** → 기존 403(승인 대기/비활성).
5. **비밀번호 맞음 + 안 잠김 + ACTIVE** → 성공. `failed_login_count > 0`이면 `reset_failed_login(id, updated_at=now)`로 0 리셋. 토큰 발급.

### 보안 원칙
- **비밀번호가 틀리면 잠김 여부와 무관하게 항상 통일된 401이다.** 따라서 비밀번호를 찍어보는 공격자는 계정 존재/잠김을 응답으로 구분할 수 없다. 잠김 메시지(423)는 **비밀번호가 맞는 진짜 사용자에게만** 노출된다.
- 기존 타이밍 사이드채널 방어(더미 해시)는 유지한다. `row is None or not verify_password(...)`처럼 단축 평가로 합치지 않는다(기존 주석의 경고 유지).
- **알려진 트레이드오프(설계서에 명시):** "존재하는 계정 + 오답"은 이제 UPDATE 한 번을 더 수행하므로 "존재하지 않는 이메일"과 미세한 시간 차이가 생긴다. 계정 잠금 기능의 일반적 비용이며, argon2 검증 비용이 지배적이라 실질 위험이 낮다고 판단해 수용한다.

### 에러 헬퍼 추가 (`app/utils/errors.py`)
```python
@staticmethod
def locked(message: str = "계정이 잠겼습니다. 관리자에게 문의하세요.") -> AppError:
    return AppError(423, "ACCOUNT_LOCKED", message)
```
전역 핸들러가 `AppError.status_code`(423)와 `{code, message}`를 그대로 응답한다(기존 규칙).

---

## 4. 쿼리 (`app/queries/users.sql`)

### 기존 쿼리에 컬럼 추가
- `find_by_email`, `find_by_id`: 로그인 로직이 읽도록 `failed_login_count, locked_at, unlocked_at`을 SELECT 목록에 추가.
- `list_by_status`: 관리자 화면이 표시하도록 같은 세 컬럼 추가.

### 신규 쿼리
```sql
-- name: record_failed_login!
UPDATE users
SET failed_login_count = :failed_login_count,
    locked_at = :locked_at,
    updated_at = :updated_at
WHERE id = :id;

-- name: reset_failed_login!
UPDATE users
SET failed_login_count = 0,
    updated_at = :updated_at
WHERE id = :id;

-- name: unlock_user!
UPDATE users
SET locked_at = NULL,
    failed_login_count = 0,
    unlocked_at = :unlocked_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
```
- `record_failed_login`은 실패 카운트와 `locked_at`을 함께 세팅한다. 앱이 값을 계산해 넘긴다(잠금 임계 도달 시 `locked_at=now`, 아니면 기존값 유지).

---

## 5. 관리자 해제 API (`app/auth/admin_router.py`)

```python
@router.post("/{user_id}/unlock")
async def unlock_user(user_id: int, db = Depends(get_db), admin = Depends(require_admin)):
    conn = await raw_connection(db)
    row = await queries.find_by_id(conn, id=user_id)
    if row is None:
        raise Errors.not_found("사용자를 찾을 수 없습니다.")
    now = now_local()
    await queries.unlock_user(conn, id=user_id, unlocked_at=now, updated_at=now, updated_by=admin["id"])
    await db.commit()
    return {"id": user_id, "unlocked_at": now}
```
- 기존 `approve`/`reject`와 같은 형태·같은 가드(`require_admin`). 이중 방어 유지.
- 존재하지 않는 사용자는 404. 이미 안 잠긴 사용자를 풀어도 무해(멱등에 가까움).

---

## 6. 프론트엔드

### `lib/admin.ts`
- `AdminUser`에 필드 추가:
  ```ts
  failed_login_count: number
  locked_at: string | null
  unlocked_at: string | null
  ```
- `adminUsers`에 `unlock` 추가:
  ```ts
  unlock: (id: number) => api.post<{ id: number; unlocked_at: string }>(`/admin/users/${id}/unlock`),
  ```

### `pages/admin/AdminUsers.tsx`
- 표에 열 3개 추가:
  | 헤더 | 내용 |
  |------|------|
  | 실패 | `failed_login_count` (숫자; 0이면 `-`) |
  | 잠김 | `locked_at`이 있으면 🔒 "잠김" 배지(빨강), 없으면 `-` |
  | 해제일시 | `unlocked_at` 있으면 `formatDate`, 없으면 `-`, `align: 'right'` |
- **액션 열을 "관리"로 일반화**(기존엔 PENDING 탭에서만 승인/거절):
  - `status === 'PENDING'` 행 → 승인 / 거절 버튼(기존)
  - `locked_at`이 있는 행 → **"잠금 해제"** 버튼(어느 탭이든 잠겼으면)
  - 그 외 → 빈 셀
  - 즉 액션 열은 항상 존재하고, 셀 내용이 행 상태에 따라 달라진다.
- 해제 처리: `adminUsers.unlock(id)` 성공 → 현재 탭 재조회(`load()`). 처리 중 버튼 비활성화(`actingId` 재사용).

### `pages/Login.tsx` — **변경 없음**
현재 `catch`는 403만 `/pending`으로 보내고, 그 외 `ApiError`는 `e.message`를 인라인 표시한다. 423 잠김 응답은 이 else 분기가 그대로 처리해 서버 메시지("계정이 잠겼습니다…")를 폼 상단에 보여준다. 별도 분기가 필요 없다.

---

## 7. 검증

### pytest (백엔드, 기존 통합 테스트 방식)
| # | 케이스 | 기대 |
|---|--------|------|
| 1 | ACTIVE 계정에 틀린 비밀번호 5회 | 5번째 후 `locked_at` 설정, `failed_login_count=5`. 매 응답은 통일 401. |
| 2 | 잠긴 계정 + 올바른 비밀번호 | 423, 토큰 미발급 |
| 3 | 잠긴 계정 + 틀린 비밀번호 | 여전히 통일 401 (계정 잠김이 응답으로 드러나지 않음) |
| 4 | 실패 몇 회 후 올바른 비밀번호(잠기기 전) | 성공, `failed_login_count=0`으로 리셋 |
| 5 | 관리자 `POST /admin/users/{id}/unlock` | `locked_at=NULL, failed_login_count=0, unlocked_at` 설정. 이후 로그인 성공 |
| 6 | 비관리자가 unlock 호출 | 403 |
| 7 | 존재하지 않는 user_id unlock | 404 |
| 8 | 임계치 설정(`failed_login_limit`)이 반영되는가 | 값을 낮춰 그 횟수에서 잠기는지 |

### 브라우저 수동
- 목록에 실패 횟수·잠김 배지·해제일시가 보이는가
- 잠긴 계정(테스트로 5회 실패시켜 만든)에 "잠금 해제" 버튼이 뜨고, 눌러 해제되면 배지가 사라지는가
- 해제 후 그 계정으로 로그인되는가
- 잠긴 상태에서 올바른 비밀번호로 로그인 시도 → 로그인 화면에 잠김 메시지가 뜨는가

---

## 8. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `app/models/user.py` | 컬럼 3개 추가 |
| `app/config.py` | `failed_login_limit: int = 5` |
| `alembic/versions/<new>.py` | 컬럼 3개 add/drop |
| `app/utils/errors.py` | `Errors.locked` (423) |
| `app/queries/users.sql` | 기존 3개 SELECT 확장 + 신규 쿼리 3개 |
| `app/auth/router.py` | `login`에 잠금 로직 |
| `app/auth/admin_router.py` | `unlock_user` 엔드포인트 |
| `web/src/lib/admin.ts` | `AdminUser` 필드 + `adminUsers.unlock` |
| `web/src/pages/admin/AdminUsers.tsx` | 열 3개 + 잠금 해제 액션 |
| `tests/...` | 로그인 잠금 + unlock 통합 테스트 |

---

## 9. 다음 단계 (범위 밖)
1. 잠금/해제 이벤트 감사 로그(별도 테이블)
2. 시간 기반 자동 해제 옵션
3. 관리자에게 "잠김 N" 알림 배지(사이드바)
