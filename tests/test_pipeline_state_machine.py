from app.constants import StageStatus
from app.core.pipeline import STAGE_ORDER, can_transition


def test_stage_order():
    assert STAGE_ORDER == ["script", "voice", "captions", "render"]


def test_allowed_transitions():
    assert can_transition(StageStatus.PENDING, StageStatus.RUNNING)
    assert can_transition(StageStatus.RUNNING, StageStatus.NEEDS_REVIEW)
    assert can_transition(StageStatus.RUNNING, StageStatus.FAILED)
    assert can_transition(StageStatus.NEEDS_REVIEW, StageStatus.APPROVED)
    assert can_transition(StageStatus.NEEDS_REVIEW, StageStatus.PENDING)  # 재생성
    assert can_transition(StageStatus.FAILED, StageStatus.PENDING)  # 재시도


def test_denied_transitions():
    assert not can_transition(StageStatus.PENDING, StageStatus.APPROVED)
    assert not can_transition(StageStatus.APPROVED, StageStatus.RUNNING)
    assert not can_transition(StageStatus.NEEDS_REVIEW, StageStatus.RUNNING)
    assert not can_transition(StageStatus.RUNNING, StageStatus.APPROVED)
