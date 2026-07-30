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

-- name: count_stages_health^
-- 대시보드 관리자 섹션용: 파이프라인 건강도(실행 중·실패·검토 필요 단계 수).
SELECT
  COUNT(*) FILTER (WHERE status = 'RUNNING') AS running,
  COUNT(*) FILTER (WHERE status = 'FAILED') AS failed,
  COUNT(*) FILTER (WHERE status = 'NEEDS_REVIEW') AS needs_review
FROM stages;

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

-- name: update_stage_output_cas<!
-- 사람이 고친 대본을 저장한다. status는 바꾸지 않는다 — 수정은 상태 전이가 아니라
-- 검토 중 내용 변경이고, 저장 후에도 여전히 승인 대기다.
--
-- 상태 술어(AND status = :expected_status)가 진짜 가드다. 요청 진입 시 읽은 상태는
-- 낡을 수 있다(다른 탭에서 승인, auto_run의 자동 승인 순간, 저장 더블클릭). 술어 없이
-- UPDATE하면 이미 승인돼 음성 생성이 시작된 대본을 덮어써 음성과 대본이 어긋난다.
UPDATE stages
SET output = :output::jsonb,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND status = :expected_status
RETURNING id;

-- name: find_stage_by_id^
SELECT id, project_id, name, provider, status, output, error, attempt,
       started_at, finished_at, created_at, updated_at
FROM stages
WHERE id = :id;

-- name: queue_stage<!
-- PENDING/FAILED일 때만 QUEUED로 선점한다. 영향 행이 0이면(RETURNING 없음) 이미 큐에
-- 들어갔거나 실행 가능한 상태가 아니라는 뜻 — 중복 실행 요청 가드.
-- 재시도로 다시 큐에 들어가는 것이므로 지난 실패 메시지는 지운다.
UPDATE stages
SET status = :status,
    error = NULL,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND status IN ('PENDING', 'FAILED')
RETURNING id;

-- name: claim_stage_run<!
-- QUEUED일 때만 RUNNING으로 선점한다. 큐에 같은 stage_id가 두 번 들어가도 두 번째
-- claim은 0행을 반환하고 조용히 버려진다 — 워커 동시성 가드.
UPDATE stages
SET status = :status,
    started_at = :started_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND status = 'QUEUED'
RETURNING id;

-- name: approve_stage_cas<!
-- NEEDS_REVIEW일 때만 승인한다. 상태 술어가 없으면 동시 승인자 둘이 각자 다음 단계를
-- 등록해 같은 단계 행이 두 개 생기거나, 사용자가 방금 요청한 재생성을 덮어쓴다.
UPDATE stages
SET status = :status, updated_at = :updated_at, updated_by = :updated_by
WHERE id = :id AND status = 'NEEDS_REVIEW'
RETURNING id;

-- name: reset_stage_for_regenerate<!
-- NEEDS_REVIEW일 때만 되돌린다. 상태 술어가 없으면 이미 실행 중(RUNNING)인 단계를
-- 덮어써 같은 단계가 두 번 실행되고 산출물이 서로를 지운다.
UPDATE stages
SET status = :status, output = :output::jsonb, error = NULL, attempt = :attempt,
    started_at = NULL, finished_at = NULL, updated_at = :updated_at, updated_by = :updated_by
WHERE id = :id AND status = 'NEEDS_REVIEW'
RETURNING id;

-- name: fail_running_stages!
-- 앱이 죽으면서 RUNNING으로 남은 고아를 기동 시 정리한다. 중간 산출물 상태를 알 수
-- 없으므로 되살리지 않고 실패로 확정한다 — 사용자가 재시도할 수 있다.
-- updated_by는 사람 행위자가 없으므로 건드리지 않는다.
UPDATE stages
SET status = 'FAILED',
    error = :error,
    finished_at = :finished_at,
    updated_at = :updated_at
WHERE status = 'RUNNING';

-- name: list_queued_stage_ids
-- 기동 시 큐에 다시 넣을 대상. QUEUED는 아직 시작 전이므로 재투입이 안전하다.
SELECT id FROM stages WHERE status = 'QUEUED' ORDER BY id ASC;
