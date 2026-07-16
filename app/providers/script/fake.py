from app.providers.base import Provider, StageContext, StageResult

# 재생성(attempt)마다 톤을 바꿔 산출물이 눈에 띄게 달라지되, 같은 attempt면 항상 동일.
_TONES = ["호기심 자극형", "충격 사실형", "공감 스토리형", "질문 던지기형"]


class FakeScript(Provider):
    """외부 호출 없이 결정적 대본 JSON을 만드는 개발/테스트용 provider."""

    stage = "script"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        tone = _TONES[ctx.attempt % len(_TONES)]
        scenes = [
            {
                "index": i,
                "narration": f"[{tone}] {ctx.topic}에 대한 {i}번째 핵심 포인트입니다.",
                "on_screen": f"{ctx.topic} · 포인트 {i}",
            }
            for i in range(1, 4)
        ]
        output = {
            "title": f"{ctx.topic} — 60초 쇼츠",
            "hook": f"[{tone}] 3초 안에 {ctx.topic}의 반전을 보여드립니다.",
            "scenes": scenes,
            "estimated_duration_sec": 45,
        }
        return StageResult(output=output)
