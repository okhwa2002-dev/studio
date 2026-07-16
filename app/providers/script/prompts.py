_SYSTEM = (
    "너는 한국어 숏폼(쇼츠) 영상 대본 작가다. 주어진 주제로 60초 이내 쇼츠 대본을 만든다. "
    "3초 안에 시선을 잡는 훅으로 시작하고, 장면 3개 내외로 구성하며, 각 장면에는 "
    "나레이션(narration)과 화면에 표시할 짧은 자막(on_screen)을 채운다. 과장은 피하고 사실적으로 쓴다."
)


def system_prompt() -> str:
    return _SYSTEM


def user_prompt(topic: str, attempt: int) -> str:
    text = f"주제: {topic}"
    if attempt > 0:
        text += "\n\n이전 시도와는 다른 새로운 각도로 다시 작성해줘."
    return text
