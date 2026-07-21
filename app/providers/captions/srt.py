_MIN_DURATION = 0.05  # 길이 0인 큐는 재생기가 거부한다 — 최소 50ms를 보장한다


def _timecode(seconds: float) -> str:
    """초 → SRT 타임코드 HH:MM:SS,mmm."""
    ms = max(int(round(seconds * 1000)), 0)
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def to_srt(words: list[dict]) -> str:
    """단어별 타임스탬프를 SRT로 직렬화한다. 큐 1개 = 단어 1개.

    words: [{"w": 단어, "s": 시작초, "e": 종료초}, ...]
    단어 사이의 빈틈은 메우지 않는다(무음은 무음 그대로).
    """
    blocks = []
    for number, word in enumerate(words, start=1):
        start = max(word["s"], 0.0)
        end = max(word["e"], start + _MIN_DURATION)
        blocks.append(f"{number}\n{_timecode(start)} --> {_timecode(end)}\n{word['w']}\n")
    return "\n".join(blocks)
