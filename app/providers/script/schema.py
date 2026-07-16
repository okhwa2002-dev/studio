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
