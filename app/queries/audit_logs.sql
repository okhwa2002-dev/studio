-- name: insert_audit_log<!
-- 감사 로그는 append-only다. UPDATE 쿼리를 여기에 추가하지 말 것.
INSERT INTO audit_logs (action, actor_id, actor_email, actor_name, actor_ip,
                        target_type, target_id, target_label,
                        http_method, http_path, success_yn, summary, created_at)
VALUES (:action, :actor_id, :actor_email, :actor_name, :actor_ip,
        :target_type, :target_id, :target_label,
        :http_method, :http_path, :success_yn, :summary, :created_at)
RETURNING id;

-- name: list_audit_logs
-- 목록. WHERE 절이 아래 count_audit_logs와 글자 그대로 같아야 한다 —
-- 어긋나면 페이지 수가 실제 결과와 맞지 않는다.
--
-- q가 아니라 :like 하나만 쓰는 이유: asyncpg는 파라미터 타입을 사용처에서 추론하는데,
-- ":q IS NULL"처럼 NULL 비교에만 쓰인 파라미터는 타입을 정할 수 없어
-- "could not determine data type of parameter" 오류가 난다.
--
-- 그런데 실측해보니 ":action IS NULL OR action = :action"처럼 같은 파라미터를
-- 등호/ILIKE 쪽에서도 쓰는 것만으로는 부족했다 — asyncpg(익스텐디드 프로토콜, 타입
-- 미지정 Parse)로는 action(VARCHAR)·success_yn(CHAR(1))·ILIKE 대상 컬럼 전부에서
-- 동일한 오류가 재현됐다. Postgres가 "IS NULL" 쪽을 통해서는 컬럼 타입으로 좁혀주지
-- 않기 때문이다. 그래서 IS NULL 비교 자리의 파라미터에 ::text로 명시 캐스트를 건다 —
-- 텍스트 계열 컬럼(VARCHAR/CHAR)과는 암시적으로 비교되므로 값 비교 결과는 그대로다.
SELECT id, action, actor_id, actor_email, actor_name, actor_ip,
       target_type, target_id, target_label,
       http_method, http_path, success_yn, summary, created_at
FROM audit_logs
WHERE created_at >= :from_at
  AND created_at <= :to_at
  AND (:action::text IS NULL OR action = :action)
  AND (:success_yn::text IS NULL OR success_yn = :success_yn)
  AND (:like::text IS NULL
       OR actor_email ILIKE :like
       OR actor_name ILIKE :like
       OR target_label ILIKE :like
       OR summary ILIKE :like)
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;

-- name: count_audit_logs^
-- 위 목록과 같은 조건의 전체 건수. 화면의 페이지 수와 "전체 N건"이 이 값을 쓴다.
SELECT COUNT(*) AS n
FROM audit_logs
WHERE created_at >= :from_at
  AND created_at <= :to_at
  AND (:action::text IS NULL OR action = :action)
  AND (:success_yn::text IS NULL OR success_yn = :success_yn)
  AND (:like::text IS NULL
       OR actor_email ILIKE :like
       OR actor_name ILIKE :like
       OR target_label ILIKE :like
       OR summary ILIKE :like);
