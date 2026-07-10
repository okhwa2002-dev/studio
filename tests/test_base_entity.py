from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)
from app.utils.time import now_local


class _Sample(BaseEntity, table=True):
    __tablename__ = "sample_task3"
    name: str = Field()

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field()
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field()


async def test_base_entity_defaults(db_session):
    row = _Sample(name="a")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert isinstance(row.id, int)                 # 정수 자동 증가 PK
    assert row.created_at is not None
    assert row.updated_at is not None
    assert row.created_by is None                    # 기본 nullable
    assert row.updated_by is None


def test_audit_timestamp_columns_are_naive_local_time():
    # 저장 자체가 로컬 벽시계 시간이어야 하므로, 컬럼은 timezone-naive여야 한다.
    table = _Sample.__table__
    assert table.c.created_at.type.timezone is False
    assert table.c.updated_at.type.timezone is False


async def test_created_at_stores_configured_local_time(db_session):
    before = now_local()

    row = _Sample(name="b")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    after = now_local()

    assert row.created_at.tzinfo is None
    assert before - timedelta(seconds=5) <= row.created_at <= after + timedelta(seconds=5)


async def test_updated_at_changes_on_update(db_session):
    row = _Sample(name="c")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    first_updated = row.updated_at

    row.name = "c2"
    await db_session.commit()
    await db_session.refresh(row)

    assert row.updated_at >= first_updated


def test_audit_columns_are_bigint_matching_users_pk():
    # created_by/updated_by는 향후 BIGINT인 users.id를 FK로 참조하므로,
    # 컬럼 타입도 BIGINT여야 한다(Integer로 두면 21억을 넘는 id를 참조 못 함).
    table = _Sample.__table__
    assert isinstance(table.c.created_by.type, BigInteger)
    assert isinstance(table.c.updated_by.type, BigInteger)


def test_table_column_order_is_id_business_then_audit():
    # 테이블 생성 규칙: id, 업무 컬럼(name), 그다음 생성/수정 감사 컬럼 순서여야 한다.
    columns = list(_Sample.__table__.columns.keys())
    assert columns == ["id", "name", "created_at", "created_by", "updated_at", "updated_by"]
