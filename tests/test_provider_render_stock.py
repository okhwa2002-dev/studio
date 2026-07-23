import pytest

from app.config import get_settings
from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.render.stock import StockRender
from app.utils import storage
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO, VIDEO, Clip, StockTooLarge

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/9/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/9/captions/captions.srt", "meta": {}}],
}
_INPUTS = {
    "captions": {"duration_sec": 30.0},
    "script": {"scenes": [
        {"index": 1, "narration": "가" * 40, "on_screen": "서울 야경"},
        {"index": 2, "narration": "나" * 60, "on_screen": "카페"},
        {"index": 3, "narration": "다" * 50, "on_screen": "출근길"},
    ]},
}


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _clip(clip_id, kind=VIDEO):
    return Clip(source="pexels", kind=kind, id=clip_id, url=f"https://cdn/{clip_id}",
                page_url=f"https://page/{clip_id}", author="홍길동", width=1080, height=1920)


class _FakeSource:
    """어떤 검색어든 요청한 종류의 클립을 넉넉히 돌려준다. 씬 3개보다 많아야
    중복 배제·재시도 테스트가 후보를 소진하지 않는다."""

    name = "pexels"

    def __init__(self, hits=None):
        self._hits = hits if hits is not None else [_clip(f"c{i}") for i in range(1, 6)]

    async def search(self, query, kind):
        # 종류가 다르면 0건 — 실제 소스와 같은 계약이라야 폴백 순서가 그대로 재현된다
        return [clip for clip in self._hits if clip.kind == kind]


class _Recorder:
    """runner·downloader 호출을 기록하는 테스트 더블."""

    def __init__(self, download_fails=0):
        self.cmds = []
        self.downloads = []
        self.progress = []
        self._download_fails = download_fails

    async def runner(self, cmd, cwd, on_progress=None, total_sec=None):
        self.cmds.append({"cmd": cmd, "cwd": cwd, "on_progress": on_progress, "total_sec": total_sec})
        if on_progress is not None:
            on_progress(0.0, "영상 합성 중…")
            on_progress(100.0, "영상 합성 중…")
        storage.write_bytes(cmd[-1], b"MP4-bytes")

    async def downloader(self, url, rel, max_bytes, timeout_sec, transport=None):
        self.downloads.append({"url": url, "rel": rel})
        if len(self.downloads) <= self._download_fails:
            raise StockTooLarge("too big")
        storage.write_bytes(rel, b"CLIP")
        return 4


def _ctx(on_progress=None, attempt=0):
    kwargs = {"topic": "도시 여행", "inputs": _INPUTS, "input_assets": _ASSETS,
              "attempt": attempt, "workdir": "projects/9/render"}
    if on_progress is not None:
        kwargs["on_progress"] = on_progress
    return StageContext(**kwargs)


def _provider(rec, sources=None):
    return StockRender(runner=rec.runner, exe="/bin/ffmpeg",
                       sources=sources or [_FakeSource()], downloader=rec.downloader)


# --- 성공 경로 ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_downloads_one_clip_per_scene_and_records_video_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder()
    result = await _provider(rec).run(_ctx())

    assert len(rec.downloads) == 3
    assert [d["rel"] for d in rec.downloads] == [
        "projects/9/render/sources/scene1.mp4",
        "projects/9/render/sources/scene2.mp4",
        "projects/9/render/sources/scene3.mp4",
    ]
    assert result.assets[0]["kind"] == AssetKind.VIDEO
    assert result.assets[0]["path"] == "projects/9/render/render.mp4"
    assert len(result.assets) == 1   # 소재는 asset으로 기록하지 않는다
    assert result.output["provider"] == "stock"
    assert result.output["duration_sec"] == 30.0
    assert result.output["size_bytes"] == len(b"MP4-bytes")


@pytest.mark.asyncio
async def test_run_records_sources_for_attribution(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await _provider(_Recorder()).run(_ctx())

    sources = result.output["sources"]
    assert len(sources) == 3
    assert sources[0] == {
        "scene": 1, "source": "pexels", "kind": VIDEO,
        "query": "서울 야경", "url": "https://page/c1", "author": "홍길동",
    }


@pytest.mark.asyncio
async def test_run_passes_scene_seconds_to_ffmpeg(monkeypatch, tmp_path):
    # 글자수 40/60/50 → 30초를 8/12/10으로. concat 길이가 오디오와 맞아야 한다.
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder()
    await _provider(rec).run(_ctx())

    cmd = rec.cmds[0]["cmd"]
    assert "8.000" in cmd and "12.000" in cmd and "10.000" in cmd
    assert rec.cmds[0]["cwd"] == str(tmp_path)   # 상대경로 자막 필터를 위해 루트에서 실행
    assert rec.cmds[0]["total_sec"] == 30.0


@pytest.mark.asyncio
async def test_photo_clip_is_saved_with_jpg_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder()
    # 영상이 하나도 없어 매체 폴백이 사진으로 내려가는 상황
    photo_source = _FakeSource(hits=[_clip(f"p{i}", PHOTO) for i in range(1, 6)])
    await StockRender(runner=rec.runner, exe="/bin/ffmpeg",
                      sources=[photo_source], downloader=rec.downloader).run(_ctx())

    assert all(d["rel"].endswith(".jpg") for d in rec.downloads)
    # 이미지 씬은 ffmpeg에서 -loop 1로 늘어난다
    assert "-loop" in rec.cmds[0]["cmd"]


@pytest.mark.asyncio
async def test_scenes_do_not_reuse_the_same_clip(monkeypatch, tmp_path):
    # 주의: 이 테스트는 "행복 경로의 출력 모양"만 본다 — used_keys.add가 지워져도
    # 통과할 수 있다(아래 test_used_keys_accumulate_across_scenes 참고). offset이
    # ctx.attempt + scene_index라 씬마다 0,1,2 연속값이 되고, 후보 5건 중 연속
    # 인덱스는 dedup 없이도 서로 달라 URL 3개가 우연히 겹치지 않기 때문이다.
    # dedup 메커니즘 자체를 지키는 건 그 화이트박스 테스트다.
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await _provider(_Recorder()).run(_ctx())

    urls = [s["url"] for s in result.output["sources"]]
    assert len(set(urls)) == 3   # 같은 화면이 반복되면 안 된다


@pytest.mark.asyncio
async def test_used_keys_accumulate_across_scenes(monkeypatch, tmp_path):
    """select_clip에 실제로 넘어가는 used_keys가 씬을 거치며 누적되는지 화이트박스로 확인한다.

    블랙박스로 "URL 3개가 다 다르다"만 보면 안 된다 — offset이 ctx.attempt+scene_index로
    씬마다 0,1,2 연속값이 되어, 후보 5건(fresh) 중 연속 인덱스는 used_keys.add를 지워도
    서로 다른 클립을 가리킬 수 있다. 즉 URL이 겹치지 않는 게 dedup 덕분인지 offset 분산
    덕분인지 그 방식으로는 구분이 안 된다(위 test_scenes_do_not_reuse_the_same_clip 참고).
    그래서 select_clip을 스파이로 감싸 호출마다 used_keys 스냅숏(복사본)을 가로채서,
    이전 씬에서 고른 클립들이 실제로 다음 씬 호출에 배제 대상으로 넘어가는지 직접 본다.
    """
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    from app.providers.render import stock as stock_module

    real_select_clip = stock_module.select_clip
    seen_used_keys = []   # 매 호출 시점의 스냅숏. set(used_keys)로 복사해야 한다 —
                          # 참조를 그대로 저장하면 provider가 이후 계속 mutate해서
                          # 나중엔 전부 최종 상태(3개)로 똑같이 보여 검증이 무의미해진다.

    async def spy_select_clip(sources, queries, used_keys, offset):
        seen_used_keys.append(set(used_keys))
        return await real_select_clip(sources, queries, used_keys, offset)

    monkeypatch.setattr(stock_module, "select_clip", spy_select_clip)

    await _provider(_Recorder()).run(_ctx())

    assert len(seen_used_keys) == 3   # 씬 3개, 다운로드는 모두 성공하니 재시도 없이 1회씩
    assert seen_used_keys[0] == set()      # 첫 씬은 아직 아무 것도 배제되지 않은 상태여야 한다
    assert len(seen_used_keys[1]) == 1     # 씬0에서 고른 클립 1건이 배제 대상에 쌓여 있어야 한다
    assert len(seen_used_keys[2]) == 2     # 씬0+씬1 두 건이 누적돼 있어야 한다
    # add가 사라지면 매 호출이 빈 집합만 보게 되어 아래 진짜 부분집합 연쇄가 깨진다
    assert seen_used_keys[0] < seen_used_keys[1] < seen_used_keys[2]


@pytest.mark.asyncio
async def test_previous_sources_are_cleared_before_run(monkeypatch, tmp_path):
    # 재생성 시 이전 소재가 쌓이면 디스크가 샌다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("projects/9/render/sources/stale.mp4", b"old")
    await _provider(_Recorder()).run(_ctx())

    assert not (tmp_path / "projects/9/render/sources/stale.mp4").exists()


# --- 진행률 -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_progress_is_split_between_download_and_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    seen = []
    await _provider(_Recorder()).run(_ctx(on_progress=lambda p, m: seen.append((p, m))))

    percents = [p for p, _ in seen if p is not None]
    assert percents[0] == 0.0            # 첫 소재 준비
    assert max(percents) == 100.0        # ffmpeg 완료가 100%
    assert any(0 < p <= 40 for p in percents)    # 다운로드 구간
    assert any(40 <= p < 100 for p in percents)  # ffmpeg 구간
    assert "배경 소재 준비 중… (1/3)" in [m for _, m in seen]


# --- 실패 경로 ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_download_falls_back_to_next_candidate(monkeypatch, tmp_path):
    # 첫 후보가 상한 초과여도 다음 후보로 이어간다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder(download_fails=1)
    result = await _provider(rec).run(_ctx())

    assert len(rec.downloads) == 4   # 실패 1 + 성공 3
    assert len(result.output["sources"]) == 3


@pytest.mark.asyncio
async def test_all_download_candidates_failing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder(download_fails=99)
    with pytest.raises(AppError) as exc:
        await _provider(rec).run(_ctx())

    assert exc.value.code == "STOCK_DOWNLOAD_FAILED"


@pytest.mark.asyncio
async def test_missing_captions_duration_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"captions": {}, "script": _INPUTS["script"]},
                       input_assets=_ASSETS, workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await _provider(_Recorder()).run(ctx)

    assert exc.value.code == "CAPTIONS_DURATION_MISSING"


@pytest.mark.asyncio
async def test_missing_script_scenes_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"captions": {"duration_sec": 10.0}},
                       input_assets=_ASSETS, workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await _provider(_Recorder()).run(ctx)

    assert exc.value.code == "SCRIPT_SCENES_MISSING"


@pytest.mark.asyncio
async def test_missing_voice_asset_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs=_INPUTS,
                       input_assets={StageName.CAPTIONS: _ASSETS[StageName.CAPTIONS]},
                       workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await _provider(_Recorder()).run(ctx)

    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_validate_without_any_api_key_raises(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "")
    with pytest.raises(AppError) as exc:
        StockRender().validate({})

    assert exc.value.code == "STOCK_API_KEY_MISSING"


def test_registry_has_render_stock():
    assert REGISTRY["render"]["stock"] is StockRender
