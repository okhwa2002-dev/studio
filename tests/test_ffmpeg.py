import subprocess
import sys

import pytest

from app.utils.ffmpeg import build_slideshow_cmd, build_stock_cmd, parse_progress_percent


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
    assert "Alignment=10" in vf  # 레거시 SSA 넘버링에서 중앙 (5는 좌상단)


def test_cmd_matches_audio_length_and_web_pixfmt():
    cmd = _cmd()
    assert "-shortest" in cmd
    assert "yuv420p" in cmd
    assert cmd[-1] == "projects/7/render/render.mp4"


def test_cmd_asks_ffmpeg_for_progress():
    # 진행률을 stdout으로 받아야 파싱할 수 있다.
    cmd = _cmd()
    assert cmd[cmd.index("-progress") + 1] == "pipe:1"


def test_parse_progress_percent_reads_out_time_us():
    assert parse_progress_percent("out_time_us=5000000\n", 10.0) == 50.0


def test_parse_progress_percent_clamps_to_100():
    # -shortest로 끝나는 순간 out_time이 총 길이를 살짝 넘을 수 있다.
    assert parse_progress_percent("out_time_us=11000000\n", 10.0) == 100.0


def test_parse_progress_percent_ignores_other_lines():
    assert parse_progress_percent("frame=120\n", 10.0) is None
    assert parse_progress_percent("out_time_us=N/A\n", 10.0) is None  # 시작 직후엔 N/A가 온다
    # 총 길이를 모르면 %를 낼 수 없다.
    assert parse_progress_percent("out_time_us=5000000\n", None) is None


@pytest.mark.asyncio
async def test_run_converts_missing_binary_to_runtimeerror(tmp_path):
    from app.utils.ffmpeg import run

    with pytest.raises(RuntimeError):
        await run(["/no/such/ffmpeg-binary", "-version"], cwd=str(tmp_path))


@pytest.mark.asyncio
async def test_run_reaps_process_and_keeps_reading_when_on_progress_raises(monkeypatch, tmp_path):
    # 실제 ffmpeg 대신 파이썬으로 "-progress pipe:1" 출력 모양(out_time_us= 줄)만
    # 흉내내는 값싼 가짜 커맨드 — run()의 정리 로직만 검증하면 되므로 충분히 빠르다.
    from app.utils.ffmpeg import run

    script = (
        "import sys\n"
        "for i in range(3):\n"
        "    print(f'out_time_us={i * 1_000_000}')\n"
        "    sys.stdout.flush()\n"
    )
    cmd = [sys.executable, "-c", script]

    # run()이 실제로 wait()까지 마쳐 회수했는지 보려면 만들어진 Popen 인스턴스를
    # 붙잡아야 한다. mock이 아니라 진짜 Popen을 그대로 쓰고 참조만 가로챈다.
    captured: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def _spy_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        captured.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", _spy_popen)

    seen_percents: list[float] = []

    def _raising_on_progress(percent, message):
        seen_percents.append(percent)
        # 프로덕션에서 워커 종료 중 call_soon_threadsafe가 닫힌 루프에 내는
        # RuntimeError를 흉내낸다.
        raise RuntimeError("progress consumer died")

    # 콜백이 매번 터져도 렌더(mp4)가 본체이므로 run()은 예외 없이 정상 종료돼야 한다.
    await run(cmd, cwd=str(tmp_path), on_progress=_raising_on_progress, total_sec=10.0)

    assert len(seen_percents) == 3  # 콜백 실패로 읽기 루프가 멈추지 않고 세 줄 다 처리했다
    assert captured[0].poll() is not None  # wait()으로 회수됨 — 좀비/미회수로 안 남는다


_SCENES = [
    {"path": "projects/9/render/sources/scene1.mp4", "kind": "video", "seconds": 8.0},
    {"path": "projects/9/render/sources/scene2.jpg", "kind": "photo", "seconds": 12.0},
    {"path": "projects/9/render/sources/scene3.mp4", "kind": "video", "seconds": 10.0},
]


def _stock_cmd(scenes=None):
    return build_stock_cmd(
        exe="/bin/ffmpeg",
        scenes=scenes if scenes is not None else _SCENES,
        audio_abs="/abs/storage/projects/9/voice/voice.mp3",
        srt_rel="projects/9/captions/captions.srt",
        out_rel="projects/9/render/render.mp4",
        width=1080, height=1920,
        font="Malgun Gothic", font_size=30,
    )


def test_video_scene_loops_and_is_trimmed_by_input_options():
    # 클립이 씬보다 짧으면 반복, 길면 잘린다 — 필터에 trim이 필요 없어진다
    cmd = _stock_cmd()
    i = cmd.index("projects/9/render/sources/scene1.mp4")
    assert cmd[i - 5:i] == ["-stream_loop", "-1", "-t", "8.000", "-i"]


def test_photo_scene_uses_loop_1():
    cmd = _stock_cmd()
    i = cmd.index("projects/9/render/sources/scene2.jpg")
    assert cmd[i - 5:i] == ["-loop", "1", "-t", "12.000", "-i"]


def test_audio_is_last_input_and_mapped_by_index():
    # 씬 3개면 오디오는 3번 입력. 스톡 클립의 오디오는 map에서 빠져 나레이션만 남는다
    cmd = _stock_cmd()
    assert cmd[cmd.index("/abs/storage/projects/9/voice/voice.mp3") - 1] == "-i"
    assert cmd[cmd.index("-map") + 1] == "[v]"
    assert "3:a" in cmd
    assert "0:a" not in cmd


def _filter_of(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


def test_filter_normalizes_every_scene_then_concats():
    vf = _filter_of(_stock_cmd())
    for i in range(3):
        assert (f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,fps=30,setsar=1,setpts=PTS-STARTPTS[v{i}]") in vf
    assert "[v0][v1][v2]concat=n=3:v=1:a=0[bg]" in vf


def test_subtitles_use_relative_path_and_shared_style():
    # 드라이브 문자 ':'가 subtitles 필터 구분자와 충돌하는 Windows 문제 회피
    vf = _filter_of(_stock_cmd())
    assert "[bg]subtitles=projects/9/captions/captions.srt:force_style=" in vf
    assert "Fontname=Malgun Gothic" in vf
    assert "Fontsize=30" in vf
    assert "Alignment=10" in vf   # slideshow와 같은 정중앙 값


def test_output_is_browser_compatible_h264_and_relative():
    cmd = _stock_cmd()
    assert cmd[-1] == "projects/9/render/render.mp4"
    for flag in ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"):
        assert flag in cmd
    assert cmd[:4] == ["/bin/ffmpeg", "-y", "-progress", "pipe:1"]


def test_single_scene_still_concats():
    vf = _filter_of(_stock_cmd([_SCENES[0]]))
    assert "[v0]concat=n=1:v=1:a=0[bg]" in vf


def test_ten_scenes_stay_well_under_windows_command_limit():
    # 리스크: 필터 문자열이 씬 수에 비례해 길어진다. Windows 한계는 약 32768자.
    scenes = [{"path": f"projects/9/render/sources/scene{i}.mp4", "kind": "video", "seconds": 3.0}
              for i in range(1, 11)]
    assert len(" ".join(_stock_cmd(scenes))) < 8000
