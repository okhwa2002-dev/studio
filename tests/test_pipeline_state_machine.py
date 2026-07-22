from app.constants import StageStatus
from app.core import pipeline
from app.core.pipeline import STAGE_ORDER, can_transition


def test_stage_order():
    assert STAGE_ORDER == ["script", "voice", "captions", "render"]


def test_allowed_transitions():
    assert can_transition(StageStatus.PENDING, StageStatus.QUEUED)
    assert can_transition(StageStatus.QUEUED, StageStatus.RUNNING)
    assert can_transition(StageStatus.RUNNING, StageStatus.NEEDS_REVIEW)
    assert can_transition(StageStatus.RUNNING, StageStatus.FAILED)
    assert can_transition(StageStatus.NEEDS_REVIEW, StageStatus.APPROVED)
    assert can_transition(StageStatus.NEEDS_REVIEW, StageStatus.PENDING)  # 재생성
    assert can_transition(StageStatus.FAILED, StageStatus.QUEUED)  # 재시도


def test_denied_transitions():
    assert not can_transition(StageStatus.PENDING, StageStatus.APPROVED)
    assert not can_transition(StageStatus.APPROVED, StageStatus.RUNNING)
    assert not can_transition(StageStatus.NEEDS_REVIEW, StageStatus.RUNNING)
    assert not can_transition(StageStatus.RUNNING, StageStatus.APPROVED)


def test_pending_goes_to_queued_not_running():
    # 실행 요청은 곧바로 RUNNING이 아니라 QUEUED로 간다 — 워커가 집기 전 구간을
    # UI가 구분할 수 있어야 하고, [실행] 버튼이 두 번 눌리면 안 된다.
    assert pipeline.can_transition(StageStatus.PENDING, StageStatus.QUEUED)
    assert not pipeline.can_transition(StageStatus.PENDING, StageStatus.RUNNING)


def test_queued_goes_to_running_or_failed():
    assert pipeline.can_transition(StageStatus.QUEUED, StageStatus.RUNNING)
    # 기동 복구 경로: 앱이 죽어 남은 작업을 정리한다.
    assert pipeline.can_transition(StageStatus.QUEUED, StageStatus.FAILED)


def test_failed_retries_straight_into_queue():
    assert pipeline.can_transition(StageStatus.FAILED, StageStatus.QUEUED)
    assert not pipeline.can_transition(StageStatus.FAILED, StageStatus.PENDING)
