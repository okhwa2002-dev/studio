from app.utils.errors import AppError


def scene_spans(scenes: list[dict], duration_sec: float | None) -> list[tuple[float, float]]:
    """narration 글자수 비율로 전체 길이를 씬에 배분한다.

    voice는 씬 경계를 남기지 않으므로 정확한 경계를 알 방법이 없다. TTS 속도가
    균일해 글자수 비례로도 오차가 ±0.5초 수준이고, 배경 전환 시점이라 육안에
    드러나지 않는다.

    누적 반올림 오차는 마지막 씬이 흡수해 spans[-1][1] == duration_sec을 보장한다 —
    이게 어긋나면 concat 길이와 오디오 길이가 틀어진다.
    """
    if not scenes:
        raise AppError(409, "SCRIPT_SCENES_MISSING",
                       "대본에 장면이 없습니다. 대본 단계를 다시 실행해 주세요.")
    if not duration_sec or duration_sec <= 0:
        raise AppError(409, "CAPTIONS_DURATION_MISSING",
                       "자막 길이 정보가 없습니다. 자막 단계를 다시 실행해 주세요.")

    lengths = [len((scene.get("narration") or "").strip()) for scene in scenes]
    total = sum(lengths)
    if total == 0:                      # 대본이 비어도 0 나눗셈 없이 균등 분할로 진행
        lengths = [1] * len(scenes)
        total = len(scenes)

    spans: list[tuple[float, float]] = []
    start = 0.0
    for length in lengths[:-1]:
        end = round(start + duration_sec * length / total, 3)
        spans.append((start, end))
        start = end
    spans.append((start, float(duration_sec)))
    return spans
