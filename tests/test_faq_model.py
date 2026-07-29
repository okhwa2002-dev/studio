from app.constants import FaqCategory, FaqStatus
from app.models.faq import Faq


def test_faq_column_order_is_id_business_then_audit():
    # 테이블 생성 규칙: id, 업무 컬럼, 그다음 생성/수정 감사 컬럼 순서여야 한다.
    assert list(Faq.__table__.columns.keys()) == [
        "id",
        "question",
        "answer",
        "category",
        "status",
        "sort_order",
        "deleted_at",
        "deleted_by",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    ]


def test_faq_defaults_are_draft_and_zero_sort_order():
    faq = Faq(question="질문", answer="답변", category=FaqCategory.ETC)
    assert faq.status == FaqStatus.DRAFT
    assert faq.sort_order == 0
    assert faq.deleted_at is None


def test_faq_deleted_at_is_naive_local_time():
    # 저장 자체가 로컬 벽시계 시간이어야 하므로 컬럼은 timezone-naive여야 한다.
    assert Faq.__table__.c.deleted_at.type.timezone is False
