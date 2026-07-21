import asyncio


def ffmpeg_exe() -> str:
    """imageio-ffmpeg가 동봉한 정적 ffmpeg 바이너리 절대경로."""
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def build_slideshow_cmd(
    *,
    exe: str,
    bg_color: str,
    audio_abs: str,
    srt_rel: str,
    out_rel: str,
    width: int,
    height: int,
    font: str,
    font_size: int,
) -> list[str]:
    """9:16 단색 배경 + 오디오 + 단어별 자막 번인 mp4를 만드는 ffmpeg 인자.

    자막(srt)·출력은 cwd(저장소 루트) 기준 상대경로다 — 드라이브 문자 ':'가
    subtitles 필터 구분자와 충돌하는 Windows 문제를 회피한다. 오디오는 필터가
    아니라 -i 입력이라 절대경로여도 안전하다.
    """
    style = (
        f"Fontname={font},Fontsize={font_size},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=3,Shadow=0,Alignment=5"
    )
    vf = f"subtitles={srt_rel}:force_style='{style}'"
    return [
        exe, "-y",
        "-f", "lavfi", "-i", f"color=c={bg_color}:s={width}x{height}",
        "-i", audio_abs,
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        out_rel,
    ]


async def run(cmd: list[str], cwd: str) -> None:
    """ffmpeg를 실행한다. 0이 아닌 종료코드면 RuntimeError. 블로킹이라 스레드로 비켜준다."""

    def _run() -> tuple[int, str]:
        import subprocess

        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        except OSError as exc:
            raise RuntimeError(f"ffmpeg 실행 불가: {exc}") from exc
        return proc.returncode, proc.stderr

    code, stderr = await asyncio.to_thread(_run)
    if code != 0:
        raise RuntimeError(f"ffmpeg 실패(code={code}): {stderr[-500:]}")
