-- name: find_by_email^
SELECT id, email, name, password_hash, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at, must_change_password,
       created_at, updated_at, created_by, updated_by
FROM users
WHERE email = :email;

-- name: insert_user<!
INSERT INTO users (email, name, password_hash, role, status, created_at, updated_at)
VALUES (:email, :name, :password_hash, :role, :status, :created_at, :updated_at)
RETURNING id;

-- name: find_by_id^
SELECT id, email, name, password_hash, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at, must_change_password,
       created_at, updated_at, created_by, updated_by
FROM users
WHERE id = :id;

-- name: list_by_status
SELECT id, email, name, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at, must_change_password,
       created_at, updated_at
FROM users
WHERE status = :status
ORDER BY created_at ASC;

-- name: list_all
SELECT id, email, name, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at, must_change_password,
       created_at, updated_at
FROM users
ORDER BY created_at ASC;

-- name: count_users_summary^
-- 대시보드 관리자 섹션용: 활성·승인 대기·잠긴 계정 수를 한 번에 센다.
SELECT
  COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active,
  COUNT(*) FILTER (WHERE status = 'PENDING') AS pending,
  COUNT(*) FILTER (WHERE locked_at IS NOT NULL) AS locked
FROM users;

-- name: update_status!
UPDATE users
SET status = :status,
    approved_at = :approved_at,
    approved_by = :approved_by,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;

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

-- name: admin_reset_password!
-- 관리자가 비밀번호를 초기값으로 되돌린다. 변경 강제 플래그를 켜고, 잠김·실패 횟수도
-- 함께 푼다 — 비밀번호를 잊어 연속 실패로 잠긴 계정이 가장 흔한 초기화 대상이라,
-- 관리자가 [잠금 해제]를 따로 누르게 할 이유가 없다. unlocked_at도 채워서 목록의
-- '해제일시'가 unlock_user로 푼 것과 같이 보이게 한다.
UPDATE users
SET password_hash = :password_hash,
    must_change_password = TRUE,
    failed_login_count = 0,
    locked_at = NULL,
    unlocked_at = :unlocked_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;

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

-- name: admin_reset_failed_login!
-- 관리자가 상세 화면에서 실패 횟수를 0으로 되돌리며 잠김도 함께 해제한다(locked_at = NULL).
-- 로그인 성공 경로의 reset_failed_login과 달리 누가 초기화했는지 updated_by를 남긴다.
UPDATE users
SET failed_login_count = 0,
    locked_at = NULL,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;

-- name: unlock_user!
UPDATE users
SET locked_at = NULL,
    failed_login_count = 0,
    unlocked_at = :unlocked_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
