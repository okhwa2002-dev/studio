from sqlmodel import SQLModel

import app.models  # noqa: F401  (모든 모델을 metadata에 등록)
from app.constants import ProjectStatus, StageName, StageStatus
from app.models.project import Project
from app.models.stage import Stage


def test_status_constants_are_uppercase():
    assert ProjectStatus.DRAFT == "DRAFT"
    assert ProjectStatus.DONE == "DONE"
    assert StageStatus.NEEDS_REVIEW == "NEEDS_REVIEW"
    assert StageName.SCRIPT == "script"  # 단계명은 레지스트리 키와 맞춰 소문자


def test_project_and_stage_tables_registered():
    tables = SQLModel.metadata.tables
    assert "projects" in tables
    assert "stages" in tables


def test_project_defaults():
    p = Project(owner_id=1, title="t", topic="주제")
    assert p.status == ProjectStatus.DRAFT
    assert p.current_stage == StageName.SCRIPT
    assert p.settings == {}


def test_stage_defaults():
    s = Stage(project_id=1, name=StageName.SCRIPT, provider="fake")
    assert s.status == StageStatus.PENDING
    assert s.output == {}
    assert s.attempt == 0
