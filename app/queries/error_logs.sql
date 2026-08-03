-- name: upsert_error_log<!
-- 같은 지문이면 행을 늘리지 않고 count만 올린다. message·context는 마지막 발생 값으로
-- 덮어쓴다 — 대표 예시 하나면 원인을 좁히는 데 충분하고, 전부 보존하면 지문으로 묶은
-- 의미가 없어진다.
--
-- updated_at을 명시적으로 넣는다. updated_at_field()의 onupdate는 SQLAlchemy ORM
-- 갱신에만 걸리고 이 원시 쿼리에는 적용되지 않는다.
INSERT INTO error_logs
    (fingerprint, source, exc_type, location, message, context, count, created_at, updated_at)
VALUES
    (:fingerprint, :source, :exc_type, :location, :message, :context, 1, :now, :now)
ON CONFLICT (fingerprint) DO UPDATE SET
    count      = error_logs.count + 1,
    message    = EXCLUDED.message,
    context    = EXCLUDED.context,
    updated_at = EXCLUDED.updated_at
RETURNING id;

-- name: delete_old_error_logs!
-- 기준이 updated_at(마지막 발생)인 것이 핵심이다. created_at으로 지우면 오래전에
-- 처음 났지만 지금도 나고 있는 에러가 사라진다 — 가장 오래 방치된, 그래서 가장 봐야 할
-- 항목이 먼저 지워지는 셈이다.
DELETE FROM error_logs WHERE updated_at < :before;
