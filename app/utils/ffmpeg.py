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
    # Alignment=10 = 화면 정중앙. 번들 libass는 레거시 SSA 넘버링을 쓴다
    # (5는 좌상단, 10이 중앙) — 실제 렌더로 검증한 값이므로 5로 되돌리지 말 것.
    style = (
        f"Fontname={font},Fontsize={font_size},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=3,Shadow=0,Alignment=10"
    )
    vf = f"subtitles={srt_rel}:force_style='{style}'"
    return [
        exe, "-y",
        "-progress", "pipe:1",   # 진행 상황을 stdout으로 — 아래 run()이 파싱한다
        "-f", "lavfi", "-i", f"color=c={bg_color}:s={width}x{height}",
        "-i", audio_abs,
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        out_rel,
    ]


def parse_progress_percent(line: str, total_sec: float | None) -> float | None:
    """ffmpeg -progress 한 줄에서 진행률(0~100)을 뽑는다. 진행 정보가 아니면 None."""
    key, _, value = line.partition("=")
    if key.strip() != "out_time_us" or not total_sec:
        return None
    try:
        elapsed_sec = int(value.strip()) / 1_000_000
    except ValueError:
        return None  # 시작 직후엔 N/A가 온다
    return max(0.0, min(100.0, elapsed_sec / total_sec * 100))


async def run(cmd: list[str], cwd: str, on_progress=None, total_sec: float | None = None) -> None:
    """ffmpeg를 실행한다. 0이 아닌 종료코드면 RuntimeError. 블로킹이라 스레드로 비켜준다."""

    def _run() -> tuple[int, str]:
        import logging
        import subprocess
        from collections import deque

        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd,
                stdout=subprocess.PIPE,
                # stderr를 따로 파이프로 받으면, stdout을 다 읽는 동안 ffmpeg의 방대한
                # 로그가 stderr 버퍼를 채워 서로 막힌다(교착). 한 스트림으로 합쳐 읽는다.
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            raise RuntimeError(f"ffmpeg 실행 불가: {exc}") from exc

        tail: deque[str] = deque(maxlen=40)  # 실패 메시지로 쓸 마지막 로그
        try:
            for line in proc.stdout:
                tail.append(line.rstrip())
                percent = parse_progress_percent(line, total_sec)
                if percent is not None and on_progress is not None:
                    try:
                        on_progress(percent, "영상 합성 중…")
                    except Exception:
                        # 진행률 보고는 부가 기능, 렌더(mp4)가 본체다. 프로덕션에서
                        # on_progress는 loop.call_soon_threadsafe를 거치는데 워커
                        # 종료 중이면 루프가 닫혀 RuntimeError가 난다 — 그런 일로
                        # 사용자가 기다리는 렌더까지 죽이지 않고 로그만 남긴 뒤
                        # 읽기를 계속한다.
                        logging.getLogger(__name__).exception(
                            "on_progress 콜백 실패 — 진행률만 놓치고 렌더는 계속"
                        )
        except BaseException:
            # 콜백이 아닌 다른 이유로 읽기 루프 자체가 죽으면, 아무도 안 읽는 ffmpeg가
            # 혼자 끝까지 돌아 좀비/고아로 남는다. 강제 종료하고 그래도 반드시
            # 회수(wait)와 fd 정리는 한다.
            proc.kill()
            proc.wait()
            proc.stdout.close()
            raise
        proc.stdout.close()
        return proc.wait(), "\n".join(tail)

    code, log = await asyncio.to_thread(_run)
    if code != 0:
        raise RuntimeError(f"ffmpeg 실패(code={code}): {log}")
