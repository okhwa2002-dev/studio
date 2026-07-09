-- name: find_active_by_code(code)^
-- 활성 상태인 에러코드를 code로 조회한다.
SELECT id, code, message, http_status, is_default, is_active,
       created_at, updated_at, created_by, updated_by
FROM error_codes
WHERE code = :code AND is_active = true;

-- name: find_default()^
-- 디폴트로 지정된 활성 에러코드를 조회한다.
SELECT id, code, message, http_status, is_default, is_active,
       created_at, updated_at, created_by, updated_by
FROM error_codes
WHERE is_default = true AND is_active = true
LIMIT 1;
