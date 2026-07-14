# 개발용 사용자 샘플 데이터 설계 (Design Spec)

- **작성일:** 2026-07-13
- **한 줄 요약:** 가입 승인 화면(`/admin/approvals`) 개발에 쓸 샘플 사용자 8명을 멱등하게 생성하는 시드 스크립트.
- **선행:** `docs/superpowers/specs/2026-07-13-uppercase-codes-design.md` (코드값 대문자화) — **이 시드보다 먼저 적용한다.**

---

## 1. 목적 & 범위

### 목적
다음 작업인 **가입 승인 화면(`/admin/approvals`)** 을 개발·확인하려면 승인 대기 중인 사용자가 여럿 있어야 한다. 지금 DB에는 관리자 계정 하나뿐이라 화면을 띄워도 볼 것이 없다.

### 범위
- `PENDING` 계정 여러 개 — 대기 목록과 승인/거절 동작을 확인한다.
- `ACTIVE`·`REJECTED` 계정 약간 — 상태 필터(`GET /admin/users?status=`)가 실제로 거르는지 확인한다.
- 재실행해도 안전한 멱등 시드.
- 로컬 DB에서만 동작하는 안전장치.

### 비범위 (YAGNI)
- 개수를 인자로 받는 유연한 생성 (`--pending 12`) — 지금 필요한 건 고정된 소수의 계정이다.
- 페이지네이션 검증용 대량 데이터 — 목록 화면에 페이지네이션이 생길 때 다시 판단한다.
- 프로젝트·단계 등 다른 도메인의 샘플 데이터 — 해당 모델이 생긴 뒤에.
- 샘플 데이터 삭제(cleanup) 명령 — 로컬 DB는 언제든 `docker compose down -v`로 초기화할 수 있다.

---

## 2. 구조 — 기존 `seed_admin` 패턴을 따른다

```
app/auth/seed_sample_users.py   # 핵심 로직 (테스트 가능, 커넥션을 인자로 받는다)
scripts/seed_sample_users.py    # CLI 진입점 (설정 로드 · 세션 생성 · 결과 출력)
```

`app/auth/seed_admin.py`(핵심) + `scripts/seed_admin.py`(진입점)와 정확히 같은 2단 구조다. 핵심 로직이 raw 커넥션을 인자로 받으므로 테스트에서 그대로 호출할 수 있다.

### 핵심 함수

```python
async def ensure_sample_users_seeded(conn) -> int:
    """샘플 사용자를 생성하고 생성한 개수를 반환한다.

    이미 존재하는 이메일은 건너뛴다(재실행해도 안전).
    """
```

멱등성의 근거는 **고정된 이메일**이다. `seed_admin`과 마찬가지로 `queries.find_by_email`로 존재 여부를 확인하고 없을 때만 `queries.insert_user`를 호출한다. 몇 번을 돌려도 중복이 생기지 않고, 이미 승인해 둔 샘플 계정의 상태를 되돌려놓지도 않는다.

---

## 3. 계정 구성

비밀번호는 전부 `password123`이다.

| 이메일 | role | status | 용도 |
|--------|------|--------|------|
| `sample-pending1@example.com` | MEMBER | PENDING | 승인 대기 목록 |
| `sample-pending2@example.com` | MEMBER | PENDING | 〃 |
| `sample-pending3@example.com` | MEMBER | PENDING | 〃 |
| `sample-pending4@example.com` | MEMBER | PENDING | 〃 |
| `sample-pending5@example.com` | MEMBER | PENDING | 〃 |
| `sample-member1@example.com` | MEMBER | ACTIVE | 승인된 일반 사용자 (필터 확인 + 실제 로그인) |
| `sample-member2@example.com` | MEMBER | ACTIVE | 〃 |
| `sample-rejected1@example.com` | MEMBER | REJECTED | 거절된 사용자 (필터 확인) |

`ACTIVE` 계정 둘은 실제로 로그인해서 **일반 사용자 관점**을 확인하는 데 쓴다 — 관리자 메뉴가 보이지 않고, `/admin/*`이 403으로 막히는지.

코드값은 `app/constants.py`의 `UserRole`·`UserStatus`(대문자 StrEnum)를 쓴다. 리터럴을 쓰지 않는다.

---

## 4. 안전장치 — 로컬 DB에서만 실행

이 스크립트는 **비밀번호가 소스에 적힌, 로그인 가능한 계정**을 만든다. 운영 DB에 붙은 채로 실행하면 그대로 백도어가 된다.

`DATABASE_URL`의 호스트가 `localhost` 또는 `127.0.0.1`이 아니면 아무것도 하지 않고 종료한다.

```python
def is_local_database(database_url: str) -> bool:
    """DATABASE_URL이 로컬 호스트를 가리키는지 판별한다."""
    host = urlsplit(database_url).hostname
    return host in ("localhost", "127.0.0.1")
```

- 판별은 **호스트명 파싱**으로 한다. 문자열 `in` 검사(`"localhost" in url`)는 `db.localhost.evil.com` 같은 값에 속는다.
- 새 설정 항목을 추가하지 않는다 — 이미 있는 `DATABASE_URL`만으로 판별되므로 비용이 없다.
- **트레이드오프:** 나중에 스테이징 DB에 샘플을 넣고 싶어지면 이 가드가 막는다. 그때 가서 명시적으로(예: `--force` 인자, 또는 환경 설정) 푸는 것이 맞다. 기본값은 안전한 쪽이어야 한다.

---

## 5. 실행

```
npm run seed:sample
```

관리자 시드도 같이 npm으로 통일한다.

| 명령 | 하는 일 |
|------|---------|
| `npm run seed:admin` | 최초 관리자 계정 (`.env`의 `ADMIN_EMAIL`/`ADMIN_PASSWORD`) |
| `npm run seed:sample` | 샘플 사용자 8명 |

**왜 npm인가:** 이 머신은 Windows 애플리케이션 제어 정책이 셸에서의 `python.exe` 직접 실행을 차단한다(`uv run ...` → `os error 4551`). npm 스크립트를 거치면 정상 실행된다. README가 안내하는 `uv run python scripts/seed_admin.py`는 이 환경에서 동작하지 않으므로 npm 경로를 표준으로 삼고 README도 함께 고친다.

출력 예:
```
샘플 사용자 8명을 생성했습니다. (PENDING 5, ACTIVE 2, REJECTED 1)
비밀번호는 모두 password123 입니다.
```
재실행 시:
```
이미 존재하는 샘플 사용자입니다. 새로 생성한 계정이 없습니다.
```

---

## 6. 테스트

`tests/test_seed_sample_users.py` — 기존 `tests/test_seed_admin.py` 패턴을 따른다.

| 테스트 | 검증 |
|--------|------|
| `test_seeds_eight_sample_users` | 8명이 생성되고 상태 분포가 PENDING 5 / ACTIVE 2 / REJECTED 1 이다 |
| `test_is_idempotent` | 두 번 호출해도 두 번째는 0을 반환하고 사용자 수가 늘지 않는다 |
| `test_sample_users_can_log_in` | `ACTIVE` 샘플 계정으로 `POST /auth/login`이 200을 반환한다 (비밀번호가 실제로 맞는지) |
| `test_is_local_database` | `localhost`/`127.0.0.1`은 True, 원격 호스트와 `db.localhost.evil.com`은 False |

마지막 테스트가 안전장치의 핵심이다 — 문자열 포함 검사로 구현했다면 여기서 걸린다.

---

## 7. 검증 방법

1. `npm test` — 전체 통과 (신규 4개 포함)
2. `npm run seed:sample` — 8명 생성 메시지
3. 한 번 더 `npm run seed:sample` — "새로 생성한 계정이 없습니다"
4. DB 확인:
   ```
   docker compose exec db psql -U studio -d studio -c "SELECT email, role, status FROM users ORDER BY id;"
   ```
   → 관리자 1명 + 샘플 8명, 코드값이 모두 대문자
5. 관리자로 로그인 → (승인 화면이 생긴 뒤) 대기 목록에 5명이 보인다. 지금은 API로 확인:
   ```
   curl -b cookies.txt "http://localhost:5173/admin/users?status=PENDING"
   ```
