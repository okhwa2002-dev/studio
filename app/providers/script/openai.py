from typing import TYPE_CHECKING, Optional

from app.config import get_settings
from app.providers.base import Provider, StageContext, StageResult
from app.providers.script.prompts import system_prompt, user_prompt
from app.providers.script.schema import ScriptDraft
from app.utils.errors import AppError

if TYPE_CHECKING:
    from openai import AsyncOpenAI

_MODEL = "gpt-4o-mini"


class OpenAIScript(Provider):
    """OpenAI(ChatGPT)로 대본을 생성하는 provider. 구조화 출력으로 ScriptDraft를 강제한다."""

    stage = "script"
    name = "openai"

    def __init__(self, client: Optional["AsyncOpenAI"] = None):
        self._client = client

    def validate(self, settings: dict) -> None:
        if not get_settings().openai_api_key:
            raise AppError(400, "OPENAI_API_KEY_MISSING", "OPENAI_API_KEY가 설정되지 않았습니다.")

    def _get_client(self) -> "AsyncOpenAI":
        if self._client is None:
            # 파일명이 openai.py지만 절대 import라 설치된 openai 패키지를 가져온다.
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        return self._client

    async def run(self, ctx: StageContext) -> StageResult:
        client = self._get_client()
        completion = await client.beta.chat.completions.parse(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": user_prompt(ctx.topic, ctx.attempt)},
            ],
            response_format=ScriptDraft,
        )
        draft: ScriptDraft = completion.choices[0].message.parsed
        if draft is None:
            raise AppError(502, "SCRIPT_PARSE_FAILED", "대본 생성 결과를 해석하지 못했습니다.")
        return StageResult(output=draft.model_dump())
