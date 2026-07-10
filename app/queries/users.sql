-- name: find_by_email^
SELECT id, email, password_hash, role, status, approved_at, approved_by,
       created_at, updated_at, created_by, updated_by
FROM users
WHERE email = :email;

-- name: insert_user<!
INSERT INTO users (email, password_hash, role, status, created_at, updated_at)
VALUES (:email, :password_hash, :role, :status, :created_at, :updated_at)
RETURNING id;
