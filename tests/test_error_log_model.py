from app.models.error_log import ErrorLog


def test_column_order_is_id_business_audit():
    """테이블 생성 규칙: id → 업무 컬럼 → 생성/수정 감사 컬럼."""
    assert list(ErrorLog.__table__.columns.keys()) == [
        "id",
        "fingerprint",
        "source",
        "exc_type",
        "location",
        "message",
        "context",
        "count",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    ]


def test_fingerprint_is_unique():
    """UPSERT가 이 유니크 제약 위에서 동작한다 — 없으면 같은 에러가 행마다 쌓인다."""
    indexes = {index.name: index for index in ErrorLog.__table__.indexes}
    assert indexes["ix_error_logs_fingerprint"].unique is True


def test_context_is_nullable_and_others_are_not():
    """context는 호출부가 줄 게 없을 수도 있다(예: 정리 잡 전체 실패)."""
    columns = ErrorLog.__table__.columns
    assert columns["context"].nullable is True
    assert columns["fingerprint"].nullable is False
    assert columns["source"].nullable is False
    assert columns["exc_type"].nullable is False
    assert columns["location"].nullable is False
    assert columns["message"].nullable is False


async def test_count_defaults_to_one(db_session):
    """첫 발생은 1회다. server_default가 없으면 UPSERT의 INSERT 경로가 NULL을 넣는다."""
    row = ErrorLog(
        fingerprint="http:ValueError@core/x.py:1",
        source="http",
        exc_type="ValueError",
        location="core/x.py:1",
        message="터짐",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.count == 1
    assert row.created_at is not None
    assert row.updated_at is not None
