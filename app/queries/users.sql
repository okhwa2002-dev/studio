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

-- name: update_status!
UPDATE users
SET status = :status,
    approved_at = :approved_at,
    approved_by = :approved_by,
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

-- name: unlock_user!
UPDATE users
SET locked_at = NULL,
    failed_login_count = 0,
    unlocked_at = :unlocked_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
