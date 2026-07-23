from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from app.utils.errors import AppError


def noop_progress(percent: float | None, message: str) -> None:
    """기본 진행률 콜백. provider가 진행률을 안 내도 그냥 돌게 한다."""


@dataclass
class StageContext:
    """단계 실행에 필요한 입력."""

    topic: str
    settings: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)  # 이전 단계 산출물 (script엔 비어있음)
    input_assets: dict = field(default_factory=dict)  # {단계이름: [{kind, path, meta}]} 파일 산출물
    attempt: int = 0  # 재생성 횟수 → provider 출력 변주 seed
    workdir: str = ""  # 저장소 기준 이 단계의 디렉토리 (파일을 만드는 단계만 사용)
    # 진행 상황 보고. percent가 None이면 진짜 진행률이 없다는 뜻(메시지만 쓴다).
    # 워커 스레드에서 호출될 수 있으므로 구현은 스레드 안전해야 한다.
    on_progress: Callable[[float | None, str], None] = noop_progress


@dataclass
class StageResult:
    output: dict  # Stage.output 에 저장될 산출 요약
    assets: list[dict] = field(default_factory=list)  # {kind, path, meta} — core가 Asset으로 기록


class Provider(ABC):
    stage: str
    name: str

    def validate(self, settings: dict) -> None:
        """실행 전 필요한 키·API키 확인. 기본은 no-op."""

    @abstractmethod
    async def run(self, ctx: StageContext) -> StageResult:
        ...


# 새 도구 추가 = 클래스 1개 + 여기 1줄. core는 손대지 않는다.
from app.providers.captions.fake import FakeCaptions  # noqa: E402
from app.providers.captions.whisper import WhisperCaptions  # noqa: E402
from app.providers.render.fake import FakeRender  # noqa: E402
from app.providers.render.slideshow import SlideshowRender  # noqa: E402
from app.providers.render.stock import StockRender  # noqa: E402
from app.providers.script.claude import ClaudeScript  # noqa: E402
from app.providers.script.fake import FakeScript  # noqa: E402
from app.providers.script.openai import OpenAIScript  # noqa: E402
from app.providers.voice.edge_tts import EdgeTTS  # noqa: E402
from app.providers.voice.fake import FakeVoice  # noqa: E402

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript, "openai": OpenAIScript, "claude": ClaudeScript},
    "voice": {"fake": FakeVoice, "edge_tts": EdgeTTS},
    "captions": {"fake": FakeCaptions, "whisper": WhisperCaptions},
    "render": {"fake": FakeRender, "slideshow": SlideshowRender, "stock": StockRender},
}


def get_provider(stage: str, name: str) -> Provider:
    providers = REGISTRY.get(stage, {})
    cls = providers.get(name)
    if cls is None:
        raise AppError(500, "PROVIDER_NOT_FOUND", f"provider를 찾을 수 없습니다: {stage}/{name}")
    return cls()
