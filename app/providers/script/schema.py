import math

from pydantic import BaseModel


class ScriptScene(BaseModel):
    index: int
    narration: str   # voice가 읽을 나레이션
    on_screen: str   # 화면에 표시할 짧은 자막/키워드


class ScriptDraft(BaseModel):
    title: str
    hook: str
    scenes: list[ScriptScene]
    estimated_duration_sec: int


# 한국어 TTS의 대략적인 낭독 속도. estimated_duration_sec는 아무 단계도 읽지 않는
# 표시 전용 값이라 정밀할 필요가 없고, 사용자가 장면을 지웠을 때 값이 따라 줄기만 하면 된다.
CHARS_PER_SEC = 5.0


def build_draft(title: str, hook: str, scenes: list[tuple[str, str]]) -> ScriptDraft:
    """사람이 편집한 대본을 정상형 ScriptDraft로 조립한다.

    scenes는 (narration, on_screen) 순서쌍의 리스트이며 **그 순서가 곧 낭독 순서**다
    (voice의 narration_text가 배열 순서로 이어붙인다).

    index를 클라이언트에서 받지 않고 여기서 1..N으로 매기는 이유: 실제 순서를 정하는
    것은 배열 순서이므로, 받은 번호를 믿으면 화면 번호와 낭독 순서가 어긋날 수 있다.
    순서 변경·삭제 후 번호가 비거나 중복되는 것도 이걸로 함께 막힌다.

    estimated_duration_sec도 다시 계산한다 — 4장면을 2장면으로 줄였는데 AI가 낸
    "45초"가 그대로 남으면 화면이 거짓말을 한다.
    """
    trimmed = [(narration.strip(), on_screen.strip()) for narration, on_screen in scenes]
    total_chars = sum(len(narration) for narration, _ in trimmed)
    return ScriptDraft(
        title=title.strip(),
        hook=hook.strip(),
        scenes=[
            ScriptScene(index=i, narration=narration, on_screen=on_screen)
            for i, (narration, on_screen) in enumerate(trimmed, start=1)
        ],
        # 0초는 화면에 뜻이 없으므로 최소 1초.
        estimated_duration_sec=max(1, math.ceil(total_chars / CHARS_PER_SEC)),
    )
