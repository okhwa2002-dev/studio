import pytest

from app.providers.render.timing import scene_spans
from app.utils.errors import AppError


def _scenes(*narrations):
    return [{"index": i + 1, "narration": n, "on_screen": "x"} for i, n in enumerate(narrations)]


def test_splits_by_narration_length():
    # 글자수 40 / 60 / 50, 전체 150 → 30초를 8 / 12 / 10초로 나눈다
    scenes = _scenes("가" * 40, "나" * 60, "다" * 50)
    spans = scene_spans(scenes, 30.0)

    assert spans[0] == (0.0, 8.0)
    assert spans[1] == (8.0, 20.0)
    assert spans[2] == (20.0, 30.0)


def test_last_span_absorbs_rounding_and_ends_exactly_at_duration():
    # 3등분이 딱 안 떨어지는 길이 — 마지막 씬이 오차를 흡수해야 합이 정확히 맞는다
    spans = scene_spans(_scenes("가", "나", "다"), 10.0)
    assert spans[-1][1] == 10.0
    assert sum(end - start for start, end in spans) == pytest.approx(10.0)


def test_spans_are_contiguous():
    spans = scene_spans(_scenes("가" * 3, "나" * 7), 12.0)
    assert spans[0][1] == spans[1][0]   # 틈도 겹침도 없어야 concat 길이가 맞는다


def test_single_scene_takes_whole_duration():
    assert scene_spans(_scenes("가나다"), 7.5) == [(0.0, 7.5)]


def test_all_empty_narration_falls_back_to_even_split():
    # 0 나눗셈 방지. 대본이 비어도 실패 대신 균등 분할로 진행한다.
    spans = scene_spans(_scenes("", "  ", ""), 9.0)
    assert spans[0] == (0.0, 3.0)
    assert spans[1] == (3.0, 6.0)
    assert spans[2] == (6.0, 9.0)


def test_no_scenes_raises_script_scenes_missing():
    with pytest.raises(AppError) as exc:
        scene_spans([], 10.0)
    assert exc.value.code == "SCRIPT_SCENES_MISSING"


@pytest.mark.parametrize("duration", [None, 0, -1.0])
def test_missing_duration_raises_captions_duration_missing(duration):
    with pytest.raises(AppError) as exc:
        scene_spans(_scenes("가"), duration)
    assert exc.value.code == "CAPTIONS_DURATION_MISSING"
