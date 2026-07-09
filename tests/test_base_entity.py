from sqlalchemy import BigInteger
from sqlmodel import Field

from app.models.base import BaseEntity


class _Sample(BaseEntity, table=True):
    __tablename__ = "sample_task3"
    name: str = Field()


async def test_base_entity_defaults(db_session):
    row = _Sample(name="a")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert isinstance(row.id, int)                 # 정수 자동 증가 PK
    assert row.created_at is not None
    assert row.updated_at is not None
    assert row.created_at.tzinfo is not None        # tz-aware (UTC 저장)
    assert row.created_by is None                    # 기본 nullable
    assert row.updated_by is None


def test_audit_columns_are_bigint_matching_users_pk():
    # created_by/updated_by는 향후 BIGINT인 users.id를 FK로 참조하므로,
    # 컬럼 타입도 BIGINT여야 한다(Integer로 두면 21억을 넘는 id를 참조 못 함).
    table = _Sample.__table__
    assert isinstance(table.c.created_by.type, BigInteger)
    assert isinstance(table.c.updated_by.type, BigInteger)
