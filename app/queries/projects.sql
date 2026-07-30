-- name: insert_project<!
INSERT INTO projects (owner_id, title, topic, status, current_stage, settings,
                      created_at, updated_at, created_by, updated_by)
VALUES (:owner_id, :title, :topic, :status, :current_stage, :settings::jsonb,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: find_project_by_id^
-- 삭제된 프로젝트는 없는 것으로 취급한다 → 상세·SSE·에셋이 모두 404가 되고,
-- 같은 쿼리를 쓰는 워커도 삭제된 프로젝트의 단계를 조용히 포기한다(worker.run_one).
-- 정리 잡은 삭제된 행을 찾아야 하므로 이 쿼리 대신 list_purgeable_projects를 쓴다.
SELECT id, owner_id, title, topic, status, current_stage, settings,
       created_at, updated_at
FROM projects
WHERE id = :id AND deleted_at IS NULL;

-- name: list_projects_by_owner
SELECT id, owner_id, title, topic, status, current_stage, created_at, updated_at
FROM projects
WHERE owner_id = :owner_id AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC;

-- name: list_all_projects
-- 관리자 전체 프로젝트 화면용. 소유자 이름·이메일을 조인해 한 번에 내려준다.
SELECT p.id, p.owner_id, p.title, p.topic, p.status, p.current_stage, p.created_at,
       u.name AS owner_name, u.email AS owner_email
FROM projects p
JOIN users u ON u.id = p.owner_id
WHERE p.deleted_at IS NULL
ORDER BY p.created_at DESC, p.id DESC;

-- name: count_projects_by_status_for_owner
-- 대시보드용: 내 프로젝트를 상태별로 센다.
SELECT status, COUNT(*) AS n
FROM projects
WHERE owner_id = :owner_id AND deleted_at IS NULL
GROUP BY status;

-- name: list_owner_attention_projects
-- 대시보드 "조치 필요": 단계가 검토 필요(NEEDS_REVIEW)거나 실패(FAILED)인 내 프로젝트.
-- 최근 갱신순 상위 N. 한 프로젝트에 두 상태가 겹칠 수 있어 bool_or로 사유를 함께 준다.
SELECT p.id, p.title, p.current_stage,
       bool_or(s.status = 'NEEDS_REVIEW') AS needs_review,
       bool_or(s.status = 'FAILED') AS failed
FROM projects p
JOIN stages s ON s.project_id = p.id
WHERE p.owner_id = :owner_id AND p.deleted_at IS NULL
  AND s.status IN ('NEEDS_REVIEW', 'FAILED')
GROUP BY p.id, p.title, p.current_stage, p.updated_at
ORDER BY p.updated_at DESC, p.id DESC
LIMIT :limit;

-- name: count_projects_by_status
-- 대시보드 관리자 섹션용: 소유자 무관 전체 프로젝트를 상태별로 센다.
SELECT status, COUNT(*) AS n
FROM projects
WHERE deleted_at IS NULL
GROUP BY status;

-- name: count_active_stages^
-- 삭제 전 확인용: 워커가 손대고 있는 단계 수. RUNNING은 실행 중, QUEUED는 곧 실행된다.
-- 이 쿼리가 stages.sql이 아니라 여기 있는 것은 프로젝트 삭제 판정에만 쓰이기 때문이다.
SELECT COUNT(*) AS n
FROM stages
WHERE project_id = :project_id AND status IN ('RUNNING', 'QUEUED');

-- name: soft_delete_project!
-- deleted_at IS NULL 조건은 멱등성을 위한 것이다(이미 지운 것을 다시 지워도 시각이 안 바뀐다).
UPDATE projects
SET deleted_at = :deleted_at,
    deleted_by = :deleted_by,
    updated_at = :deleted_at,
    updated_by = :deleted_by
WHERE id = :id AND deleted_at IS NULL;

-- name: list_purgeable_projects
-- 소프트 삭제 후 보관 기간이 지난 프로젝트. 정리 잡만 쓴다
-- (다른 조회는 deleted_at IS NULL로 삭제된 것을 아예 보지 않는다).
SELECT id FROM projects
WHERE deleted_at IS NOT NULL AND deleted_at < :before
ORDER BY id;

-- name: delete_assets_by_project!
-- FK에 ON DELETE CASCADE가 없어서 자식부터 직접 지운다.
-- assets는 stage_id로만 프로젝트에 매달려 있어 서브쿼리로 찾는다.
DELETE FROM assets
WHERE stage_id IN (SELECT id FROM stages WHERE project_id = :project_id);

-- name: delete_stages_by_project!
DELETE FROM stages WHERE project_id = :project_id;

-- name: delete_project!
DELETE FROM projects WHERE id = :id;

-- name: update_project_status!
UPDATE projects
SET status = :status,
    current_stage = :current_stage,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
