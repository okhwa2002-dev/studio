-- name: insert_project<!
INSERT INTO projects (owner_id, title, topic, status, current_stage, settings,
                      created_at, updated_at, created_by, updated_by)
VALUES (:owner_id, :title, :topic, :status, :current_stage, :settings::jsonb,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: find_project_by_id^
SELECT id, owner_id, title, topic, status, current_stage, settings,
       created_at, updated_at
FROM projects
WHERE id = :id;

-- name: list_projects_by_owner
SELECT id, owner_id, title, topic, status, current_stage, created_at, updated_at
FROM projects
WHERE owner_id = :owner_id
ORDER BY created_at DESC, id DESC;

-- name: update_project_status!
UPDATE projects
SET status = :status,
    current_stage = :current_stage,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
