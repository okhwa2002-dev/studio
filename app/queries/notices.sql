-- name: insert_notice<!
INSERT INTO notices (title, body, status, pinned_yn, popup_yn, starts_at, ends_at,
                     created_at, updated_at, created_by, updated_by)
VALUES (:title, :body, :status, :pinned_yn, :popup_yn, :starts_at, :ends_at,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: find_notice_by_id^
-- 관리자 수정·삭제 전 존재 확인. 이미 소프트 삭제된 행은 없는 것으로 본다.
SELECT id, title, body, status, pinned_yn, popup_yn, starts_at, ends_at
FROM notices
WHERE id = :id AND deleted_at IS NULL;

-- name: update_notice!
UPDATE notices
SET title = :title,
    body = :body,
    status = :status,
    pinned_yn = :pinned_yn,
    popup_yn = :popup_yn,
    starts_at = :starts_at,
    ends_at = :ends_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND deleted_at IS NULL;

-- name: soft_delete_notice!
-- 행을 지우지 않고 삭제 표시만 남긴다. 이후 관리자·사용자 목록 양쪽에서 빠진다.
UPDATE notices
SET deleted_at = :deleted_at,
    deleted_by = :deleted_by,
    updated_at = :deleted_at,
    updated_by = :deleted_by
WHERE id = :id AND deleted_at IS NULL;

-- name: list_notices_for_admin
-- 관리자 목록. 표시 상태(임시저장·예약·게시중·종료)는 프론트가 status와 기간에서
-- 파생하므로 저장하지 않는다. 임시저장은 starts_at이 NULL이라 정렬에 COALESCE가 필요하다.
SELECT n.id, n.title, n.body, n.status, n.pinned_yn, n.popup_yn,
       n.starts_at, n.ends_at, n.created_at,
       u.name AS created_by_name
FROM notices n
LEFT JOIN users u ON u.id = n.created_by
WHERE n.deleted_at IS NULL
ORDER BY n.pinned_yn DESC, COALESCE(n.starts_at, n.created_at) DESC, n.id DESC;

-- name: list_published_notices
-- 사용자 목록. :now는 앱이 now_local()로 넘긴다 — SQL의 now()는 DB 세션 타임존(UTC)
-- 기준이라 이 프로젝트의 로컬 naive 저장 규칙과 9시간 어긋난다.
-- pinned_yn DESC는 'Y'(0x59) > 'N'(0x4E)이라 고정 공지를 맨 앞으로 보낸다.
SELECT n.id, n.title, n.body, n.pinned_yn, n.starts_at,
       (r.id IS NOT NULL) AS is_read
FROM notices n
LEFT JOIN notice_reads r ON r.notice_id = n.id AND r.user_id = :user_id
WHERE n.deleted_at IS NULL AND n.status = 'PUBLISHED'
  AND n.starts_at <= :now AND (n.ends_at IS NULL OR n.ends_at > :now)
ORDER BY n.pinned_yn DESC, n.starts_at DESC, n.id DESC;

-- name: list_popup_notices
-- 메인 팝업 대상. 읽음 여부와 무관하다 — "오늘 하루 보지 않기"는 브라우저가 기억한다.
SELECT id, title, body, starts_at
FROM notices
WHERE deleted_at IS NULL AND status = 'PUBLISHED' AND popup_yn = 'Y'
  AND starts_at <= :now AND (ends_at IS NULL OR ends_at > :now)
ORDER BY pinned_yn DESC, starts_at DESC, id DESC;

-- name: count_unread_notices^
-- 상단바 배지용. 게시 중인데 내 읽음 기록이 없는 공지의 수.
SELECT COUNT(*) AS n
FROM notices ntc
LEFT JOIN notice_reads r ON r.notice_id = ntc.id AND r.user_id = :user_id
WHERE ntc.deleted_at IS NULL AND ntc.status = 'PUBLISHED'
  AND ntc.starts_at <= :now AND (ntc.ends_at IS NULL OR ntc.ends_at > :now)
  AND r.id IS NULL;

-- name: find_published_notice_by_id^
-- 상세 화면이 한 건을 읽을 때와, 읽음 처리 전 노출 조건을 확인할 때 함께 쓴다.
-- 조건을 벗어난 공지(임시저장·예약·종료·삭제)는 없는 것으로 본다 — 목록에 안 보이는
-- 공지가 URL로는 열리면 안 된다.
SELECT n.id, n.title, n.body, n.pinned_yn, n.starts_at,
       (r.id IS NOT NULL) AS is_read
FROM notices n
LEFT JOIN notice_reads r ON r.notice_id = n.id AND r.user_id = :user_id
WHERE n.id = :id AND n.deleted_at IS NULL AND n.status = 'PUBLISHED'
  AND n.starts_at <= :now AND (n.ends_at IS NULL OR n.ends_at > :now);

-- name: mark_notice_read!
-- 이미 읽은 공지면 아무것도 하지 않는다(UNIQUE(notice_id, user_id)).
-- created_by/updated_by는 읽은 본인이다.
INSERT INTO notice_reads (notice_id, user_id, created_at, updated_at, created_by, updated_by)
VALUES (:notice_id, :user_id, :now, :now, :user_id, :user_id)
ON CONFLICT (notice_id, user_id) DO NOTHING;
