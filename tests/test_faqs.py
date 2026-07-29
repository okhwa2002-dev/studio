from app.auth.security import hash_password
from app.constants import FaqCategory, FaqStatus, UserStatus
from app.models.faq import Faq
from app.models.user import User
from app.utils.time import now_local


async def _login_member(client, db_session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345"),
        status=UserStatus.ACTIVE,
        name="사용자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


async def _add_faq(db_session, **overrides) -> Faq:
    fields = {
        "question": "질문",
        "answer": "답변",
        "category": FaqCategory.ETC,
        "status": FaqStatus.PUBLISHED,
        "sort_order": 0,
    }
    fields.update(overrides)
    faq = Faq(**fields)
    db_session.add(faq)
    await db_session.commit()
    await db_session.refresh(faq)
    return faq


async def test_list_requires_login(client, db_session):
    resp = await client.get("/api/faqs")
    assert resp.status_code == 401


async def test_list_returns_only_published_faqs(client, db_session):
    """임시저장·삭제된 FAQ는 사용자 목록에 나오지 않는다."""
    await _login_member(client, db_session, "member-faq-list@example.com")

    await _add_faq(db_session, question="게시중")
    await _add_faq(db_session, question="임시저장", status=FaqStatus.DRAFT)
    await _add_faq(db_session, question="삭제됨", deleted_at=now_local())

    resp = await client.get("/api/faqs")
    assert resp.status_code == 200
    assert [row["question"] for row in resp.json()] == ["게시중"]


async def test_list_is_sorted_by_sort_order_then_id(client, db_session):
    await _login_member(client, db_session, "member-faq-order@example.com")

    await _add_faq(db_session, question="C", sort_order=20)
    await _add_faq(db_session, question="A", sort_order=10)
    await _add_faq(db_session, question="B", sort_order=10)

    resp = await client.get("/api/faqs")
    # sort_order가 같으면 먼저 등록된 것(id가 작은 것)이 위로 온다.
    assert [row["question"] for row in resp.json()] == ["A", "B", "C"]


async def test_list_includes_answer_and_category(client, db_session):
    """아코디언은 이미 받은 답변을 펼치는 구조라 목록에 answer가 실려 있어야 한다."""
    await _login_member(client, db_session, "member-faq-fields@example.com")
    await _add_faq(
        db_session,
        question="렌더링은 얼마나 걸리나요?",
        answer="1분 영상 기준\n3~5분입니다.",
        category=FaqCategory.PRODUCTION,
    )

    resp = await client.get("/api/faqs")
    row = resp.json()[0]
    assert row["answer"] == "1분 영상 기준\n3~5분입니다."
    assert row["category"] == FaqCategory.PRODUCTION
