from app.auth.security import hash_password
from app.constants import FaqCategory, FaqStatus, UserRole, UserStatus
from app.models.user import User


async def _login(client, db_session, email: str, role: str = UserRole.ADMIN) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345"),
        role=role,
        status=UserStatus.ACTIVE,
        name="관리자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


def _payload(**overrides) -> dict:
    payload = {
        "question": "렌더링은 얼마나 걸리나요?",
        "answer": "1분 영상 기준 3~5분입니다.",
        "category": FaqCategory.PRODUCTION,
        "status": FaqStatus.DRAFT,
        "sort_order": 10,
    }
    payload.update(overrides)
    return payload


async def test_create_returns_201_with_id(client, db_session):
    await _login(client, db_session, "faq-create@example.com")

    resp = await client.post("/api/admin/faqs", json=_payload())
    assert resp.status_code == 201
    assert isinstance(resp.json()["id"], int)


async def test_blank_question_returns_422(client, db_session):
    await _login(client, db_session, "faq-blank-q@example.com")

    resp = await client.post("/api/admin/faqs", json=_payload(question="   "))
    assert resp.status_code == 422


async def test_blank_answer_returns_422(client, db_session):
    await _login(client, db_session, "faq-blank-a@example.com")

    resp = await client.post("/api/admin/faqs", json=_payload(answer=" \n "))
    assert resp.status_code == 422


async def test_invalid_category_returns_422(client, db_session):
    await _login(client, db_session, "faq-category@example.com")

    resp = await client.post("/api/admin/faqs", json=_payload(category="BILLING"))
    assert resp.status_code == 422


async def test_negative_sort_order_returns_422(client, db_session):
    await _login(client, db_session, "faq-sort@example.com")

    resp = await client.post("/api/admin/faqs", json=_payload(sort_order=-1))
    assert resp.status_code == 422


async def test_list_includes_author_name(client, db_session):
    await _login(client, db_session, "faq-author@example.com")

    created = await client.post("/api/admin/faqs", json=_payload())
    listed = await client.get("/api/admin/faqs")
    assert listed.status_code == 200
    row = next(r for r in listed.json() if r["id"] == created.json()["id"])
    assert row["created_by_name"] == "관리자"


async def test_list_is_sorted_by_sort_order_then_id(client, db_session):
    await _login(client, db_session, "faq-order@example.com")

    await client.post("/api/admin/faqs", json=_payload(question="C", sort_order=20))
    await client.post("/api/admin/faqs", json=_payload(question="A", sort_order=10))
    await client.post("/api/admin/faqs", json=_payload(question="B", sort_order=10))

    listed = await client.get("/api/admin/faqs")
    # sort_order가 같으면 먼저 등록된 것(id가 작은 것)이 위로 온다.
    assert [r["question"] for r in listed.json()] == ["A", "B", "C"]


async def test_update_changes_all_editable_fields(client, db_session):
    await _login(client, db_session, "faq-update@example.com")
    created = await client.post("/api/admin/faqs", json=_payload())
    faq_id = created.json()["id"]

    resp = await client.patch(
        f"/api/admin/faqs/{faq_id}",
        json=_payload(
            question="수정된 질문",
            answer="수정된 답변",
            category=FaqCategory.ACCOUNT,
            status=FaqStatus.PUBLISHED,
            sort_order=99,
        ),
    )
    assert resp.status_code == 200

    listed = await client.get("/api/admin/faqs")
    row = next(r for r in listed.json() if r["id"] == faq_id)
    assert row["question"] == "수정된 질문"
    assert row["answer"] == "수정된 답변"
    assert row["category"] == FaqCategory.ACCOUNT
    assert row["status"] == FaqStatus.PUBLISHED
    assert row["sort_order"] == 99


async def test_update_unknown_faq_returns_404(client, db_session):
    await _login(client, db_session, "faq-update-404@example.com")

    resp = await client.patch("/api/admin/faqs/999999", json=_payload())
    assert resp.status_code == 404


async def test_delete_keeps_row_but_hides_from_list(client, db_session):
    """소프트 삭제는 행을 지우지 않고 목록에서만 뺀다."""
    await _login(client, db_session, "faq-delete@example.com")
    created = await client.post("/api/admin/faqs", json=_payload(question="지울 FAQ"))
    faq_id = created.json()["id"]

    resp = await client.delete(f"/api/admin/faqs/{faq_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is not None

    listed = await client.get("/api/admin/faqs")
    assert all(r["id"] != faq_id for r in listed.json())

    from sqlalchemy import select

    from app.models.faq import Faq

    result = await db_session.execute(select(Faq).where(Faq.id == faq_id))
    row = result.scalar_one()
    assert row.deleted_at is not None
    assert row.deleted_by is not None


async def test_delete_twice_returns_404(client, db_session):
    await _login(client, db_session, "faq-delete-twice@example.com")
    created = await client.post("/api/admin/faqs", json=_payload())
    faq_id = created.json()["id"]

    assert (await client.delete(f"/api/admin/faqs/{faq_id}")).status_code == 200
    assert (await client.delete(f"/api/admin/faqs/{faq_id}")).status_code == 404


async def test_member_cannot_access_admin_faqs(client, db_session):
    await _login(client, db_session, "member-faqs@example.com", role=UserRole.MEMBER)

    assert (await client.get("/api/admin/faqs")).status_code == 403
    assert (await client.post("/api/admin/faqs", json=_payload())).status_code == 403
    assert (await client.patch("/api/admin/faqs/1", json=_payload())).status_code == 403
    assert (await client.delete("/api/admin/faqs/1")).status_code == 403
