from app.constants import AssetKind, StageName
from app.models.asset import Asset


def test_stage_name_has_voice():
    assert StageName.VOICE == "voice"


def test_asset_kind_audio():
    assert AssetKind.AUDIO == "AUDIO"


def test_asset_table_columns():
    cols = set(Asset.__table__.columns.keys())
    assert {"id", "stage_id", "kind", "path", "meta"} <= cols
    # 감사 컬럼도 상속돼 있어야 한다
    assert {"created_at", "created_by", "updated_at", "updated_by"} <= cols
    assert Asset.__tablename__ == "assets"
