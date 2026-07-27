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

-- name: list_all_projects
-- 관리자 전체 프로젝트 화면용. 소유자 이름·이메일을 조인해 한 번에 내려준다.
SELECT p.id, p.owner_id, p.title, p.topic, p.status, p.current_stage, p.created_at,
       u.name AS owner_name, u.email AS owner_email
FROM projects p
JOIN users u ON u.id = p.owner_id
ORDER BY p.created_at DESC, p.id DESC;

-- name: update_project_status!
UPDATE projects
SET status = :status,
    current_stage = :current_stage,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
