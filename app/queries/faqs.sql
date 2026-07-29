-- name: insert_faq<!
INSERT INTO faqs (question, answer, category, status, sort_order,
                  created_at, updated_at, created_by, updated_by)
VALUES (:question, :answer, :category, :status, :sort_order,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: find_faq_by_id^
-- 관리자 수정·삭제 전 존재 확인. 이미 소프트 삭제된 행은 없는 것으로 본다.
SELECT id, question, answer, category, status, sort_order
FROM faqs
WHERE id = :id AND deleted_at IS NULL;

-- name: update_faq!
UPDATE faqs
SET question = :question,
    answer = :answer,
    category = :category,
    status = :status,
    sort_order = :sort_order,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND deleted_at IS NULL;

-- name: soft_delete_faq!
-- 행을 지우지 않고 삭제 표시만 남긴다. 이후 관리자·사용자 목록 양쪽에서 빠진다.
UPDATE faqs
SET deleted_at = :deleted_at,
    deleted_by = :deleted_by,
    updated_at = :deleted_at,
    updated_by = :deleted_by
WHERE id = :id AND deleted_at IS NULL;

-- name: list_faqs_for_admin
-- 관리자 목록. 표시 상태는 status 그대로라 파생 계산이 없다.
-- 정렬은 사용자 목록과 같다 — 관리자가 화면에서 본 순서가 곧 사용자가 보는 순서다.
SELECT f.id, f.question, f.answer, f.category, f.status, f.sort_order, f.created_at,
       u.name AS created_by_name
FROM faqs f
LEFT JOIN users u ON u.id = f.created_by
WHERE f.deleted_at IS NULL
ORDER BY f.sort_order, f.id;

-- name: list_published_faqs
-- 사용자 목록. 노출 조건이 status 하나라 시각 비교가 없다(공지와 달리 :now가 필요 없다).
-- answer까지 함께 준다 — 아코디언이 이미 받은 답변을 펼치는 구조다.
SELECT id, question, answer, category
FROM faqs
WHERE deleted_at IS NULL AND status = 'PUBLISHED'
ORDER BY sort_order, id;
