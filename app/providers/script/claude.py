from typing import TYPE_CHECKING, Optional

from app.config import get_settings
from app.providers.base import Provider, StageContext, StageResult
from app.providers.script.prompts import system_prompt, user_prompt
from app.providers.script.schema import ScriptDraft
from app.utils.errors import AppError

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

_MODEL = "claude-haiku-4-5"


class ClaudeScript(Provider):
    """Claude(Anthropic)로 대본을 생성하는 provider. 구조화 출력으로 ScriptDraft를 강제한다."""

    stage = "script"
    name = "claude"

    def __init__(self, client: Optional["AsyncAnthropic"] = None):
        self._client = client

    def validate(self, settings: dict) -> None:
        if not get_settings().anthropic_api_key:
            raise AppError(400, "ANTHROPIC_API_KEY_MISSING", "ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    def _get_client(self) -> "AsyncAnthropic":
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    async def run(self, ctx: StageContext) -> StageResult:
        ctx.on_progress(None, "대본을 생성하는 중…")  # LLM 단일 호출이라 진짜 %가 없다
        client = self._get_client()
        message = await client.messages.parse(
            model=_MODEL,
            max_tokens=2048,
            system=system_prompt(),
            messages=[{"role": "user", "content": user_prompt(ctx.topic, ctx.attempt)}],
            output_format=ScriptDraft,
        )
        draft: ScriptDraft = message.parsed_output
        if draft is None:
            raise AppError(502, "SCRIPT_PARSE_FAILED", "대본 생성 결과를 해석하지 못했습니다.")
        return StageResult(output=draft.model_dump())
