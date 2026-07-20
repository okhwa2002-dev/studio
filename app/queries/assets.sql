-- name: insert_asset<!
INSERT INTO assets (stage_id, kind, path, meta,
                    created_at, updated_at, created_by, updated_by)
VALUES (:stage_id, :kind, :path, :meta::jsonb,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: list_assets_by_stage
SELECT id, stage_id, kind, path, meta, created_at, updated_at
FROM assets
WHERE stage_id = :stage_id
ORDER BY id ASC;

-- name: find_asset_by_stage^
SELECT id, stage_id, kind, path, meta, created_at, updated_at
FROM assets
WHERE stage_id = :stage_id
ORDER BY id DESC
LIMIT 1;

-- name: delete_assets_by_stage!
DELETE FROM assets WHERE stage_id = :stage_id;
