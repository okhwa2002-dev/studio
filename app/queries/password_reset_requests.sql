-- name: insert_reset_request<!
-- created_at을 명시해서 넣는다. 판정에 쓴 시각과 기록되는 시각이 같아야 하고,
-- 테스트가 과거 요청을 만들 때 같은 쿼리를 쓸 수 있어야 한다.
INSERT INTO password_reset_requests (email, client_ip, created_at, updated_at)
VALUES (:email, :client_ip, :created_at, :updated_at)
RETURNING id;

-- name: count_recent_reset_requests^
-- rate limit 세 축을 한 번의 스캔으로 센다.
--
-- 바깥 WHERE가 email/client_ip 인덱스를 타도록 좁혀 두었으므로, email_window와
-- ip_window의 FILTER에서는 created_at 조건을 반복하지 않는다 — 바깥에서 이미
-- 걸러졌다. 쿨다운만 더 좁은 창이라 한 번 더 건다(cooldown_since >= window_since가
-- 항상 성립하므로 집합이 어긋나지 않는다).
--
-- client_ip가 NULL이면 SQL에서 client_ip = NULL이 어떤 행과도 매치되지 않아
-- IP 축이 저절로 꺼진다 — 식별할 수 없는 것을 제한하지 않는다는 뜻이고,
-- 이를 위한 분기를 파이썬에 두지 않는다.
SELECT
    COUNT(*) FILTER (WHERE email = :email AND created_at > :cooldown_since) AS email_cooldown,
    COUNT(*) FILTER (WHERE email = :email)                                  AS email_window,
    COUNT(*) FILTER (WHERE client_ip = :client_ip)                          AS ip_window
FROM password_reset_requests
WHERE (email = :email OR client_ip = :client_ip)
  AND created_at > :window_since;
