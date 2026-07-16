-- name: insert_stage<!
INSERT INTO stages (project_id, name, provider, status, output, error, attempt,
                    started_at, finished_at,
                    created_at, updated_at, created_by, updated_by)
VALUES (:project_id, :name, :provider, :status, :output::jsonb, :error, :attempt,
        :started_at, :finished_at,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: find_stage^
SELECT id, project_id, name, provider, status, output, error, attempt,
       started_at, finished_at, created_at, updated_at
FROM stages
WHERE project_id = :project_id AND name = :name;

-- name: list_stages_by_project
SELECT id, project_id, name, provider, status, output, error, attempt,
       started_at, finished_at, created_at, updated_at
FROM stages
WHERE project_id = :project_id
ORDER BY id ASC;

-- name: update_stage_run!
UPDATE stages
SET status = :status,
    output = :output::jsonb,
    error = :error,
    attempt = :attempt,
    started_at = :started_at,
    finished_at = :finished_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;

-- name: update_stage_status!
UPDATE stages
SET status = :status,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
