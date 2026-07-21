import pytest

from app.utils.ffmpeg import build_slideshow_cmd


def _cmd():
    return build_slideshow_cmd(
        exe="/bin/ffmpeg",
        bg_color="#0f172a",
        audio_abs="/abs/voice.mp3",
        srt_rel="projects/7/captions/captions.srt",
        out_rel="projects/7/render/render.mp4",
        width=1080,
        height=1920,
        font="Malgun Gothic",
        font_size=96,
    )


def test_cmd_starts_with_exe_and_overwrites():
    cmd = _cmd()
    assert cmd[0] == "/bin/ffmpeg"
    assert "-y" in cmd


def test_cmd_has_color_source_at_target_resolution():
    cmd = " ".join(_cmd())
    assert "color=c=#0f172a:s=1080x1920" in cmd


def test_cmd_takes_audio_by_absolute_path():
    assert "/abs/voice.mp3" in _cmd()


def test_cmd_burns_relative_srt_with_forward_slashes():
    # 드라이브 문자 충돌을 피하려 자막은 상대경로·슬래시로 넘긴다
    vf = _cmd()[_cmd().index("-vf") + 1]
    assert "subtitles=projects/7/captions/captions.srt" in vf
    assert "Fontname=Malgun Gothic" in vf
    assert "Fontsize=96" in vf
    assert "Alignment=5" in vf


def test_cmd_matches_audio_length_and_web_pixfmt():
    cmd = _cmd()
    assert "-shortest" in cmd
    assert "yuv420p" in cmd
    assert cmd[-1] == "projects/7/render/render.mp4"


@pytest.mark.asyncio
async def test_run_converts_missing_binary_to_runtimeerror(tmp_path):
    from app.utils.ffmpeg import run

    with pytest.raises(RuntimeError):
        await run(["/no/such/ffmpeg-binary", "-version"], cwd=str(tmp_path))
