-- name: insert_refresh_token<!
INSERT INTO refresh_tokens (user_id, token_hash, expires_at, created_at, updated_at)
VALUES (:user_id, :token_hash, :expires_at, :created_at, :updated_at)
RETURNING id;

-- name: find_by_token_hash(token_hash)^
SELECT id, user_id, token_hash, expires_at, revoked_at, created_at, updated_at
FROM refresh_tokens
WHERE token_hash = :token_hash;

-- name: revoke_by_id(id, revoked_at, updated_at)!
UPDATE refresh_tokens
SET revoked_at = :revoked_at, updated_at = :updated_at
WHERE id = :id;

-- name: revoke_all_for_user(user_id, revoked_at, updated_at)!
UPDATE refresh_tokens
SET revoked_at = :revoked_at, updated_at = :updated_at
WHERE user_id = :user_id AND revoked_at IS NULL;
