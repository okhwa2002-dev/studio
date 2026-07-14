# 관리자 시드 제거 설계 (Design Spec)

- **작성일:** 2026-07-13
- **한 줄 요약:** `.env`의 `ADMIN_EMAIL`/`ADMIN_PASSWORD`와 관리자 시드 스크립트를 제거하고, 최초 관리자는 "회원가입 → SQL로 승격"으로 만든다.

---

## 1. 배경 & 목표

### 지금
최초 관리자는 `.env`의 `ADMIN_EMAIL`/`ADMIN_PASSWORD`를 읽는 시드 스크립트(`npm run seed:admin`)로 만든다. 이 방식은:

- **관리자 비밀번호를 `.env`에 평문으로 둔다.** 개발 머신에 남고, `.env.example`의 자리표시자가 그대로 운영 비밀번호가 되기 쉽다.
- **비밀번호를 바꿀 수 없다.** 시드는 멱등해서 계정이 이미 있으면 건너뛴다. `.env`만 고쳐도 DB의 비밀번호는 그대로다 — 이 함정을 아는 사람만 안다.
- **코드가 계속 남는다.** 최초 1회만 쓰는 기능을 위해 설정 필드 2개 · 모듈 2개 · 테스트 3개를 유지한다.

### 목표
설정과 코드에서 관리자 자격증명을 완전히 들어낸다. 최초 관리자는 앱의 실제 가입 경로를 그대로 쓰고, DB에서 한 줄로 승격시킨다.

### 왜 "가입 후 승격"인가
`users.password_hash`는 **argon2 해시**다. psql에서 평문으로 INSERT하면 계정은 생기지만 로그인 검증에 실패한다. 그러므로 순수 SQL만으로 로그인 가능한 계정을 만들려면 해시를 어딘가에서 얻어야 하고, 그러려면 해시 생성 도구를 유지해야 한다.

**회원가입 화면을 거치면 앱이 해시를 만들어준다.** 남는 일은 상태와 권한을 바꾸는 `UPDATE` 한 줄뿐이다. 추가 코드가 0이고, 해시 방식(argon2 파라미터 등)이 나중에 바뀌어도 절차가 깨지지 않는다.

---

## 2. 제거 대상

| 파일 | 조치 |
|------|------|
| `app/config.py` | `admin_email`, `admin_password` 필드 삭제 |
| `app/auth/seed_admin.py` | 파일 삭제 (`ensure_admin_seeded`) |
| `scripts/seed_admin.py` | 파일 삭제 (CLI 진입점) |
| `tests/test_seed_admin.py` | 파일 삭제 (테스트 3개) |
| `package.json` | `seed:admin` 스크립트 삭제 |
| `.env` · `.env.example` | `ADMIN_EMAIL`, `ADMIN_PASSWORD` 줄 삭제 |
| `README.md` | 시드 안내 → 승격 절차로 교체 (본문 + 명령 표) |
| `docs/superpowers/specs/2026-07-09-studio-design.md` | "최초 admin은 시드 스크립트로 생성" 서술(4장)과 설정 목록(7장)을 새 절차로 갱신 |

**건드리지 않는 것:** `docs/superpowers/plans/*`와 이전 스펙 문서들. 그 시점의 결정을 기록한 히스토리이므로 소급 수정하지 않는다.

**샘플 시드(`npm run seed:sample`)는 그대로 둔다.** 개발용 샘플 사용자는 관리자 시드와 별개 기능이며, 이번 변경의 대상이 아니다.

---

## 3. 새 절차 (README에 기록)

```
1. 화면(/register)에서 회원가입한다.
   → 앱이 argon2 해시를 만들어 status=PENDING 으로 저장한다.

2. psql로 승격한다.
   docker compose exec db psql -U studio -d studio \
     -c "UPDATE users SET role='ADMIN', status='ACTIVE' WHERE email='내-이메일';"

3. 로그인한다.
```

2번이 전부다. 이후 가입자는 이 관리자가 화면에서 승인한다.

---

## 4. 기존 계정 처리

현재 DB에는 시드로 만든 `admin@example.com`(비밀번호 `change-me-to-a-strong-admin-password`)이 있다. **그대로 둔다.** 지우면 로그인할 관리자가 없어져 당장 화면을 볼 수 없다. 원할 때 지우고 위 절차로 새로 만들면 된다.

README에 이 사실을 적지 않는다 — 새로 클론하는 사람에게는 존재하지 않는 계정이고, 문서에 남기면 "이 계정을 만들어야 하나?" 하는 혼란만 준다.

---

## 5. 검증

1. **`npm test`** — 남은 테스트가 모두 통과한다 (삭제한 3개 제외).
2. **앱이 실제로 기동한다** — `npm run dev:api`. `.env`에서 두 값을 지웠는데 `config.py`의 필드를 지우지 않으면 설정 로딩 자체가 깨질 수 있다. 이건 테스트로 잡히지 않으므로 반드시 띄워봐야 한다.
3. **로그인이 된다** — 기존 `admin@example.com`으로 로그인해 대시보드가 뜬다(시드 제거가 기존 계정에 영향을 주지 않았음을 확인).
4. **새 절차가 실제로 동작한다** — 샘플 계정 하나(`sample-member1@example.com`, 이미 `ACTIVE`)를 `UPDATE ... SET role='ADMIN'`으로 승격시킨 뒤 그 계정으로 `GET /admin/users`가 200을 받는지 확인하고, 원복한다. 문서에 적은 SQL이 실제로 통하는지 확인하는 것이 목적이다.
