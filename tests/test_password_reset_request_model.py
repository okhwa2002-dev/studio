from app.models.password_reset_request import PasswordResetRequest


def test_column_order_is_id_business_audit():
    """테이블 생성 규칙: id → 업무 컬럼 → 생성/수정 감사 컬럼."""
    assert list(PasswordResetRequest.__table__.columns.keys()) == [
        "id",
        "email",
        "client_ip",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    ]


def test_client_ip_is_nullable():
    """IP를 알 수 없는 요청도 기록해야 한다 — 그래야 이메일 축이 계속 동작한다."""
    assert PasswordResetRequest.__table__.columns["client_ip"].nullable is True
    assert PasswordResetRequest.__table__.columns["email"].nullable is False


def test_email_and_ip_are_indexed():
    """판정 쿼리가 이 두 인덱스로 좁힌다. 없으면 공격 중에 seq scan이 된다."""
    indexed = {
        column.name
        for index in PasswordResetRequest.__table__.indexes
        for column in index.columns
    }
    assert indexed == {"email", "client_ip"}


async def test_audit_columns_are_filled_by_db_default(db_session):
    """created_at/updated_at은 DB server_default가 채운다(Asia/Seoul 벽시계 시각)."""
    row = PasswordResetRequest(email="a@example.com", client_ip="127.0.0.1")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.id is not None
    assert row.created_at is not None
    assert row.updated_at is not None
