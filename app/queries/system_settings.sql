-- name: select_all_settings
-- 관리자가 기본값에서 바꾼 항목 전부. 행이 없으면 전부 .env 기본값이라는 뜻이다.
SELECT key, value
FROM system_settings;

-- name: upsert_setting!
-- 같은 키가 이미 있으면 값만 갱신한다(UNIQUE(key)).
INSERT INTO system_settings (key, value, created_at, updated_at, created_by, updated_by)
VALUES (:key, :value, :now, :now, :actor_id, :actor_id)
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = EXCLUDED.updated_at,
    updated_by = EXCLUDED.updated_by;

-- name: delete_setting!
-- 값이 기본값으로 돌아가면 행을 지운다. 그래야 이후 .env 변경이 그대로 반영된다.
DELETE FROM system_settings
WHERE key = :key;
