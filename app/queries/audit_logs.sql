-- name: insert_audit_log<!
-- 감사 로그는 append-only다. UPDATE 쿼리를 여기에 추가하지 말 것.
INSERT INTO audit_logs (action, actor_id, actor_email, actor_name, actor_ip,
                        target_type, target_id, target_label,
                        http_method, http_path, success_yn, summary, created_at)
VALUES (:action, :actor_id, :actor_email, :actor_name, :actor_ip,
        :target_type, :target_id, :target_label,
        :http_method, :http_path, :success_yn, :summary, :created_at)
RETURNING id;
