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

-- name: count_projects_by_status_for_owner
-- 대시보드용: 내 프로젝트를 상태별로 센다.
SELECT status, COUNT(*) AS n
FROM projects
WHERE owner_id = :owner_id
GROUP BY status;

-- name: list_owner_attention_projects
-- 대시보드 "조치 필요": 단계가 검토 필요(NEEDS_REVIEW)거나 실패(FAILED)인 내 프로젝트.
-- 최근 갱신순 상위 N. 한 프로젝트에 두 상태가 겹칠 수 있어 bool_or로 사유를 함께 준다.
SELECT p.id, p.title, p.current_stage,
       bool_or(s.status = 'NEEDS_REVIEW') AS needs_review,
       bool_or(s.status = 'FAILED') AS failed
FROM projects p
JOIN stages s ON s.project_id = p.id
WHERE p.owner_id = :owner_id AND s.status IN ('NEEDS_REVIEW', 'FAILED')
GROUP BY p.id, p.title, p.current_stage, p.updated_at
ORDER BY p.updated_at DESC, p.id DESC
LIMIT :limit;

-- name: count_projects_by_status
-- 대시보드 관리자 섹션용: 소유자 무관 전체 프로젝트를 상태별로 센다.
SELECT status, COUNT(*) AS n
FROM projects
GROUP BY status;

-- name: update_project_status!
UPDATE projects
SET status = :status,
    current_stage = :current_stage,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
