-- name: find_by_email^
SELECT id, email, name, password_hash, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at,
       created_at, updated_at, created_by, updated_by
FROM users
WHERE email = :email;

-- name: insert_user<!
INSERT INTO users (email, name, password_hash, role, status, created_at, updated_at)
VALUES (:email, :name, :password_hash, :role, :status, :created_at, :updated_at)
RETURNING id;

-- name: find_by_id^
SELECT id, email, name, password_hash, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at,
       created_at, updated_at, created_by, updated_by
FROM users
WHERE id = :id;

-- name: list_by_status
SELECT id, email, name, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at,
       created_at, updated_at
FROM users
WHERE status = :status
ORDER BY created_at ASC;

-- name: list_all
SELECT id, email, name, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at,
       created_at, updated_at
FROM users
ORDER BY created_at ASC;

-- name: update_status!
UPDATE users
SET status = :status,
    approved_at = :approved_at,
    approved_by = :approved_by,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;

-- name: update_password!
-- 본인이 설정 화면에서 비밀번호를 바꾼다. updated_by는 본인 id다.
UPDATE users
SET password_hash = :password_hash,
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
