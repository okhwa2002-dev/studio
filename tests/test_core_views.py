from app.core import views


def test_stage_event_shape():
    project = {"id": 1, "title": "t", "topic": "주제", "status": "REVIEW",
               "current_stage": "voice", "created_at": None}
    stage = {"id": 9, "name": "voice", "provider": "fake", "status": "RUNNING",
             "output": {}, "error": None, "attempt": 0}
    event = views.stage_event(project, stage)
    assert event["type"] == "stage"
    assert event["project"]["current_stage"] == "voice"
    assert event["stage"]["status"] == "RUNNING"
    # 소유자 id 같은 내부 필드가 새어 나가면 안 된다.
    assert "owner_id" not in event["project"]


def test_progress_event_allows_null_percent():
    # script·voice는 진짜 %가 없다 — null을 그대로 실어 보낸다.
    event = views.progress_event("script", None, "대본을 생성하는 중…")
    assert event == {"type": "progress", "stage": "script",
                     "percent": None, "message": "대본을 생성하는 중…"}
