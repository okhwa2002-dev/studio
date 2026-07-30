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

-- name: delete_expired_refresh_tokens!
-- 정리 잡이 쓴다. 조건에 revoked_at을 넣으면 안 된다 — refresh의 탈취 경보(폐기된 토큰이
-- 재사용되면 그 사용자의 모든 세션을 끊는다)가 폐기된 행을 찾아야 동작하기 때문이다.
-- 만료 후에는 그 토큰으로 새 세션을 받을 수 없으니 지워도 안전하다.
DELETE FROM refresh_tokens WHERE expires_at < :now;
