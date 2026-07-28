from app.constants import NoticeStatus, YN
from app.models.notice import Notice
from app.models.notice_read import NoticeRead


def test_notice_column_order_is_id_business_then_audit():
    # 테이블 생성 규칙: id, 업무 컬럼, 그다음 생성/수정 감사 컬럼 순서여야 한다.
    assert list(Notice.__table__.columns.keys()) == [
        "id",
        "title",
        "body",
        "status",
        "pinned_yn",
        "popup_yn",
        "starts_at",
        "ends_at",
        "deleted_at",
        "deleted_by",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    ]


def test_notice_defaults_are_draft_and_n():
    notice = Notice(title="제목", body="본문")
    assert notice.status == NoticeStatus.DRAFT
    assert notice.pinned_yn == YN.N
    assert notice.popup_yn == YN.N
    assert notice.starts_at is None
    assert notice.ends_at is None
    assert notice.deleted_at is None


def test_notice_timestamp_columns_are_naive_local_time():
    # 저장 자체가 로컬 벽시계 시간이어야 하므로 컬럼은 timezone-naive여야 한다.
    table = Notice.__table__
    assert table.c.starts_at.type.timezone is False
    assert table.c.ends_at.type.timezone is False
    assert table.c.deleted_at.type.timezone is False


def test_notice_read_column_order_is_id_business_then_audit():
    assert list(NoticeRead.__table__.columns.keys()) == [
        "id",
        "notice_id",
        "user_id",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    ]


def test_notice_read_has_unique_notice_user_constraint():
    # 같은 사용자가 같은 공지를 여러 번 읽어도 행이 하나여야 한다
    # (mark_notice_read의 ON CONFLICT가 이 제약에 걸린다).
    unique_column_sets = {
        tuple(sorted(column.name for column in constraint.columns))
        for constraint in NoticeRead.__table__.constraints
        if type(constraint).__name__ == "UniqueConstraint"
    }
    assert ("notice_id", "user_id") in unique_column_sets
