"""편집 요청 → 정상형 ScriptDraft 조립 (app/providers/script/schema.build_draft)

index 재매김과 길이 계산이 이 기능의 유일한 비자명한 로직이라 HTTP 없이 따로 검증한다.
"""

import math

from app.providers.script.schema import CHARS_PER_SEC, build_draft


def test_index_is_renumbered_from_one_in_array_order():
    """실제 낭독 순서는 배열 순서가 정한다(narration_text가 그 순서로 이어붙인다).
    그래서 index는 표시용이고, 서버가 배열 순서대로 1..N을 다시 매긴다.
    """
    draft = build_draft("제목", "훅", [("첫째", "a"), ("둘째", "b"), ("셋째", "c")])

    assert [s.index for s in draft.scenes] == [1, 2, 3]
    assert [s.narration for s in draft.scenes] == ["첫째", "둘째", "셋째"]


def test_duration_is_derived_from_narration_length():
    # 나레이션 총 50자 → 초당 CHARS_PER_SEC자로 나눈 값
    narration = "가" * 50
    draft = build_draft("제목", "훅", [(narration, "")])

    assert draft.estimated_duration_sec == math.ceil(50 / CHARS_PER_SEC)


def test_duration_sums_across_scenes():
    draft = build_draft("제목", "훅", [("가" * 30, ""), ("가" * 20, "")])

    assert draft.estimated_duration_sec == math.ceil(50 / CHARS_PER_SEC)


def test_duration_is_at_least_one_second():
    """짧은 나레이션이 0초로 내려가지 않는다 — 0초는 화면에 뜻이 없다."""
    draft = build_draft("제목", "훅", [("짧다", "")])

    assert draft.estimated_duration_sec >= 1


def test_strings_are_stripped():
    draft = build_draft("  제목  ", "  훅  ", [("  나레이션  ", "  화면  ")])

    assert draft.title == "제목"
    assert draft.hook == "훅"
    assert draft.scenes[0].narration == "나레이션"
    assert draft.scenes[0].on_screen == "화면"


def test_blank_on_screen_is_kept_as_empty_string():
    """on_screen은 비어도 안전하다 — 스톡 검색이 topic으로 폴백한다."""
    draft = build_draft("제목", "훅", [("나레이션", "   ")])

    assert draft.scenes[0].on_screen == ""


def test_result_dumps_to_the_same_shape_as_ai_output():
    """DB에 들어가는 모양이 AI 생성본과 같아야 한다 — 하위 단계가 두 경로를 구분하지 않는다."""
    dumped = build_draft("제목", "훅", [("나레이션", "화면")]).model_dump()

    assert set(dumped) == {"title", "hook", "scenes", "estimated_duration_sec"}
    assert set(dumped["scenes"][0]) == {"index", "narration", "on_screen"}
