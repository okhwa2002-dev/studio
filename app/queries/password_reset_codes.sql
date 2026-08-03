-- name: insert_reset_code<!
INSERT INTO password_reset_codes (user_id, code, expires_at, created_at, updated_at)
VALUES (:user_id, :code, :expires_at, :created_at, :updated_at)
RETURNING id;

-- name: find_active_reset_code^
-- 해당 사용자의 미소비 코드 중 가장 최근 것 하나. 만료 여부는 앱에서 판단한다
-- (만료된 코드도 "틀림"과 같은 통일 응답을 줘야 하므로 조회 단계에서 거르지 않는다).
SELECT id, code, expires_at, consumed_at, attempts
FROM password_reset_codes
WHERE user_id = :user_id AND consumed_at IS NULL
ORDER BY id DESC
LIMIT 1;

-- name: increment_reset_attempts!
UPDATE password_reset_codes
SET attempts = attempts + 1,
    updated_at = :updated_at
WHERE id = :id;

-- name: consume_reset_code!
UPDATE password_reset_codes
SET consumed_at = :consumed_at,
    updated_at = :updated_at
WHERE id = :id;

-- name: consume_active_reset_codes_for_user!
-- 새 코드 발급 전, 그 사용자의 미소비 코드를 모두 소비 처리해 활성 코드를 1개로 유지한다.
UPDATE password_reset_codes
SET consumed_at = :consumed_at,
    updated_at = :updated_at
WHERE user_id = :user_id AND consumed_at IS NULL;
