"""실제 네트워크·ffmpeg를 쓰는 느린 검증. 키가 없으면 통째로 skip한다."""

import subprocess

import pytest

from app.config import get_settings
from app.utils import ffmpeg, storage
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pexels import PexelsSource
from app.utils.stock.pixabay import PixabaySource

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [VIDEO, PHOTO])
async def test_pexels_real_search_returns_usable_clips(kind):
    if not get_settings().pexels_api_key:
        pytest.skip("PEXELS_API_KEY 없음")

    clips = await PexelsSource().search("도시", kind)

    assert clips, "Pexels가 0건을 돌려줬다 — 엔드포인트/파라미터를 확인할 것"
    assert all(c.url.startswith("http") for c in clips)
    assert all(c.kind == kind for c in clips)
    assert all(c.id for c in clips)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [VIDEO, PHOTO])
async def test_pixabay_real_search_returns_usable_clips(kind):
    if not get_settings().pixabay_api_key:
        pytest.skip("PIXABAY_API_KEY 없음")

    clips = await PixabaySource().search("도시", kind)

    assert clips, "Pixabay가 0건을 돌려줬다 — 응답 필드 모양을 확인할 것"
    assert all(c.url.startswith("http") for c in clips)
    assert all(c.kind == kind for c in clips)


@pytest.mark.asyncio
async def test_real_ffmpeg_concats_scenes_with_subtitles(monkeypatch, tmp_path):
    """로컬에서 만든 소재 2개 + 무음 오디오 + srt로 실제 mp4를 합성한다.

    네트워크를 타지 않으므로 키 없이도 돈다. concat 필터 정합(fps·SAR·pix_fmt)과
    Windows 상대경로 자막이 실제로 통과하는지가 검증 대상이다.
    """
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    exe = ffmpeg.ffmpeg_exe()
    workdir = "projects/1/render"
    sources_dir = f"{workdir}/sources"
    storage.resolve(sources_dir).mkdir(parents=True, exist_ok=True)

    # 씬 소재: 파란 영상 1개 + 빨간 정지 이미지 1개 (일부러 가로 규격으로 만들어 crop을 검증)
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1280x720:d=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(storage.resolve(f"{sources_dir}/scene1.mp4"))], check=True,
                   capture_output=True)
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "color=c=red:s=1280x720:d=1",
                    "-frames:v", "1",
                    str(storage.resolve(f"{sources_dir}/scene2.jpg"))], check=True,
                   capture_output=True)
    # 나레이션 대신 무음 4초
    audio_rel = f"{workdir}/voice.mp3"
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "4",
                    str(storage.resolve(audio_rel))], check=True, capture_output=True)
    srt_rel = f"{workdir}/captions.srt"
    storage.write_bytes(srt_rel,
                        "1\n00:00:00,000 --> 00:00:02,000\n안녕하세요\n\n"
                        "2\n00:00:02,000 --> 00:00:04,000\n반갑습니다\n".encode("utf-8"))

    out_rel = f"{workdir}/render.mp4"
    cmd = ffmpeg.build_stock_cmd(
        exe=exe,
        scenes=[{"path": f"{sources_dir}/scene1.mp4", "kind": "video", "seconds": 2.0},
                {"path": f"{sources_dir}/scene2.jpg", "kind": "photo", "seconds": 2.0}],
        audio_abs=str(storage.resolve(audio_rel)),
        srt_rel=srt_rel,
        out_rel=out_rel,
        width=1080, height=1920,
        font=get_settings().render_font, font_size=get_settings().render_font_size,
    )
    await ffmpeg.run(cmd, str(tmp_path))

    out = storage.resolve(out_rel)
    assert out.exists() and out.stat().st_size > 0
    print(f"[스모크] 합성 결과: {out} ({out.stat().st_size} bytes)")
