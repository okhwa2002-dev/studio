# render 단계 구현 계획 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** voice(mp3) + captions(단어별 srt)를 받아 9:16 mp4를 합성하는 `render` 단계를 파이프라인 마지막 단계로 추가한다.

**Architecture:** 기존 단계(voice·captions)와 동형. `utils/ffmpeg.py`(순수 커맨드 조립 + 실행)를 slideshow provider가 주입받아 쓴다. ffmpeg는 `imageio-ffmpeg`가 동봉한 정적 바이너리를 사용한다. 단어별 SRT를 ffmpeg `subtitles` 필터로 화면 중앙에 한 단어씩 번인한다.

**Tech Stack:** Python 3.12 · FastAPI · imageio-ffmpeg(정적 ffmpeg) · pytest · Vite/React(TS)

**설계 문서:** [../specs/2026-07-21-render-stage-design.md](../specs/2026-07-21-render-stage-design.md)

## Global Constraints

- 3계층 의존성은 항상 아래로만: `providers → core → utils`. `utils/ffmpeg.py`는 도메인(Provider 등)을 import하지 않는다.
- 캔버스 해상도: **1080×1920** (9:16). 배경 기본색 `#0f172a`(slate-900). 자막 폰트 `Malgun Gothic`, 크기 `96`. 모두 config로 변경 가능.
- 저장 경로 규약: `projects/{project_id}/{stage}/파일`. 저장소 접근은 반드시 `app.utils.storage` 경유(직접 open 금지).
- StrEnum 코드값 규약: `StageName`은 소문자, `AssetKind`/상태값은 대문자.
- 테스트는 실제 ffmpeg를 실행하지 않는다(주입된 fake runner). 실제 실행은 선택적 smoke(Task 8)에서만.
- 테스트 실행: `uv run pytest`. 커밋 메시지는 한국어 관례(`기능:`/`test:` 등 기존 로그 스타일)를 따른다.

---

## File Structure

**백엔드**
- `app/constants.py` (수정) — `StageName.RENDER`, `AssetKind.VIDEO`
- `app/config.py` (수정) — `render_provider`, `render_bg_color`, `render_font`, `render_font_size`
- `app/utils/ffmpeg.py` (신규) — `build_slideshow_cmd()`(순수) + `run()`(subprocess 실행)
- `app/providers/render/__init__.py` (신규, 빈 파일)
- `app/providers/render/input.py` (신규) — voice mp3 / captions srt 경로 해결
- `app/providers/render/slideshow.py` (신규) — `SlideshowRender`
- `app/providers/render/fake.py` (신규) — `FakeRender`
- `app/providers/base.py` (수정) — REGISTRY에 render import·등록
- `app/core/pipeline.py` (수정) — `STAGE_ORDER`에 `"render"`
- `app/api/projects.py` (수정) — `_MEDIA_TYPES`에 VIDEO
- `pyproject.toml` (수정) — `imageio-ffmpeg` 의존성
- `tests/conftest.py` (수정) — `RENDER_PROVIDER=fake`

**프론트엔드**
- `web/src/lib/projects.ts` (수정) — `RenderOutput`, `hasRender`, `STAGE_LABEL`
- `web/src/pages/projects/ProjectDetail.tsx` (수정) — `RenderView`

---

## Task 1: 상수 · 설정 추가

**Files:**
- Modify: `app/constants.py`
- Modify: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `StageName.RENDER == "render"`, `AssetKind.VIDEO == "VIDEO"`; `Settings.render_provider/render_bg_color/render_font/render_font_size`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_config.py`의 `test_settings_loads_from_env` 아래에 추가

```python
def test_render_settings_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    s = config_module.get_settings()
    assert s.render_provider == "slideshow"
    assert s.render_bg_color == "#0f172a"
    assert s.render_font == "Malgun Gothic"
    assert s.render_font_size == 96
```

그리고 `tests/test_pipeline_state_machine.py`의 `test_stage_order`를 갱신:

```python
def test_stage_order():
    assert STAGE_ORDER == ["script", "voice", "captions", "render"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_config.py::test_render_settings_defaults tests/test_pipeline_state_machine.py::test_stage_order -v`
Expected: FAIL (`AttributeError: render_provider` / STAGE_ORDER 불일치)

- [ ] **Step 3: 상수 추가** — `app/constants.py`

`StageName`에 한 줄 추가:
```python
class StageName(StrEnum):
    SCRIPT = "script"
    VOICE = "voice"
    CAPTIONS = "captions"
    RENDER = "render"
```

`AssetKind`에 한 줄 추가:
```python
class AssetKind(StrEnum):
    AUDIO = "AUDIO"
    SRT = "SRT"
    VIDEO = "VIDEO"
```

- [ ] **Step 4: 설정 추가** — `app/config.py`의 `Settings` 안, `whisper_model` 아래에

```python
    whisper_model: str = "small"
    render_provider: str = "slideshow"
    render_bg_color: str = "#0f172a"
    render_font: str = "Malgun Gothic"
    render_font_size: int = 96
```

- [ ] **Step 5: STAGE_ORDER 갱신** — `app/core/pipeline.py`

```python
STAGE_ORDER: list[str] = ["script", "voice", "captions", "render"]
```
(윗줄의 `# render 미구현` 주석은 삭제)

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/test_config.py tests/test_pipeline_state_machine.py -v`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add app/constants.py app/config.py app/core/pipeline.py tests/test_config.py tests/test_pipeline_state_machine.py
git commit -m "기능: render 단계 상수·설정 추가 및 STAGE_ORDER 연결"
```

---

## Task 2: ffmpeg 헬퍼 (`utils/ffmpeg.py`)

**Files:**
- Modify: `pyproject.toml`
- Create: `app/utils/ffmpeg.py`
- Test: `tests/test_ffmpeg.py`

**Interfaces:**
- Produces:
  - `build_slideshow_cmd(*, exe: str, bg_color: str, audio_abs: str, srt_rel: str, out_rel: str, width: int, height: int, font: str, font_size: int) -> list[str]`
  - `async def run(cmd: list[str], cwd: str) -> None` — 실패 시 `RuntimeError`
  - `def ffmpeg_exe() -> str` — 번들 바이너리 절대경로

- [ ] **Step 1: 의존성 추가**

Run: `uv add imageio-ffmpeg`
Expected: `pyproject.toml` dependencies에 `imageio-ffmpeg>=...` 추가, `uv.lock` 갱신

- [ ] **Step 2: 실패 테스트 작성** — `tests/test_ffmpeg.py` (신규)

```python
from app.utils.ffmpeg import build_slideshow_cmd


def _cmd():
    return build_slideshow_cmd(
        exe="/bin/ffmpeg",
        bg_color="#0f172a",
        audio_abs="/abs/voice.mp3",
        srt_rel="projects/7/captions/captions.srt",
        out_rel="projects/7/render/render.mp4",
        width=1080,
        height=1920,
        font="Malgun Gothic",
        font_size=96,
    )


def test_cmd_starts_with_exe_and_overwrites():
    cmd = _cmd()
    assert cmd[0] == "/bin/ffmpeg"
    assert "-y" in cmd


def test_cmd_has_color_source_at_target_resolution():
    cmd = " ".join(_cmd())
    assert "color=c=#0f172a:s=1080x1920" in cmd


def test_cmd_takes_audio_by_absolute_path():
    assert "/abs/voice.mp3" in _cmd()


def test_cmd_burns_relative_srt_with_forward_slashes():
    # 드라이브 문자 충돌을 피하려 자막은 상대경로·슬래시로 넘긴다
    vf = _cmd()[_cmd().index("-vf") + 1]
    assert "subtitles=projects/7/captions/captions.srt" in vf
    assert "Fontname=Malgun Gothic" in vf
    assert "Fontsize=96" in vf
    assert "Alignment=5" in vf


def test_cmd_matches_audio_length_and_web_pixfmt():
    cmd = _cmd()
    assert "-shortest" in cmd
    assert "yuv420p" in cmd
    assert cmd[-1] == "projects/7/render/render.mp4"
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_ffmpeg.py -v`
Expected: FAIL (`ModuleNotFoundError: app.utils.ffmpeg`)

- [ ] **Step 4: 구현** — `app/utils/ffmpeg.py` (신규)

```python
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
    style = (
        f"Fontname={font},Fontsize={font_size},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=3,Shadow=0,Alignment=5"
    )
    vf = f"subtitles={srt_rel}:force_style='{style}'"
    return [
        exe, "-y",
        "-f", "lavfi", "-i", f"color=c={bg_color}:s={width}x{height}",
        "-i", audio_abs,
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        out_rel,
    ]


async def run(cmd: list[str], cwd: str) -> None:
    """ffmpeg를 실행한다. 0이 아닌 종료코드면 RuntimeError. 블로킹이라 스레드로 비켜준다."""

    def _run() -> tuple[int, str]:
        import subprocess

        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return proc.returncode, proc.stderr

    code, stderr = await asyncio.to_thread(_run)
    if code != 0:
        raise RuntimeError(f"ffmpeg 실패(code={code}): {stderr[-500:]}")
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_ffmpeg.py -v`
Expected: PASS (5개)

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml uv.lock app/utils/ffmpeg.py tests/test_ffmpeg.py
git commit -m "기능: 9:16 자막 번인 ffmpeg 커맨드 빌더·실행 헬퍼(utils/ffmpeg)"
```

---

## Task 3: render 입력 경로 해결 (`render/input.py`)

**Files:**
- Create: `app/providers/render/__init__.py` (빈 파일)
- Create: `app/providers/render/input.py`
- Test: `tests/test_render_input.py`

**Interfaces:**
- Consumes: `StageContext.input_assets` (`{StageName: [{kind, path, meta}]}`)
- Produces:
  - `input_audio_path(ctx) -> str` — voice AUDIO 상대경로, 없으면 `AppError(409, "VOICE_ASSET_MISSING")`
  - `input_srt_path(ctx) -> str` — captions SRT 상대경로, 없으면 `AppError(409, "CAPTIONS_ASSET_MISSING")`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_render_input.py` (신규)

```python
import pytest

from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.providers.render.input import input_audio_path, input_srt_path
from app.utils.errors import AppError

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/5/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/5/captions/captions.srt", "meta": {}}],
}


def _ctx(assets):
    return StageContext(topic="t", input_assets=assets, workdir="projects/5/render")


def test_resolves_audio_and_srt_relative_paths():
    ctx = _ctx(_ASSETS)
    assert input_audio_path(ctx) == "projects/5/voice/voice.mp3"
    assert input_srt_path(ctx) == "projects/5/captions/captions.srt"


def test_missing_voice_raises():
    with pytest.raises(AppError) as exc:
        input_audio_path(_ctx({StageName.CAPTIONS: _ASSETS[StageName.CAPTIONS]}))
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_missing_srt_raises():
    with pytest.raises(AppError) as exc:
        input_srt_path(_ctx({StageName.VOICE: _ASSETS[StageName.VOICE]}))
    assert exc.value.code == "CAPTIONS_ASSET_MISSING"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_render_input.py -v`
Expected: FAIL (`ModuleNotFoundError: app.providers.render`)

- [ ] **Step 3: 구현**

`app/providers/render/__init__.py` — 빈 파일 생성.

`app/providers/render/input.py`:
```python
from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.utils.errors import AppError


def _find(ctx: StageContext, stage: str, kind: str) -> str | None:
    for asset in ctx.input_assets.get(stage, []):
        if asset["kind"] == kind:
            return asset["path"]
    return None


def input_audio_path(ctx: StageContext) -> str:
    """render의 입력인 voice mp3의 저장소 상대 경로. 없으면 AppError → FAILED."""
    path = _find(ctx, StageName.VOICE, AssetKind.AUDIO)
    if path is None:
        raise AppError(409, "VOICE_ASSET_MISSING", "음성 파일이 없습니다. voice 단계를 먼저 실행해 주세요.")
    return path


def input_srt_path(ctx: StageContext) -> str:
    """render의 입력인 captions srt의 저장소 상대 경로. 없으면 AppError → FAILED."""
    path = _find(ctx, StageName.CAPTIONS, AssetKind.SRT)
    if path is None:
        raise AppError(409, "CAPTIONS_ASSET_MISSING", "자막 파일이 없습니다. captions 단계를 먼저 실행해 주세요.")
    return path
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_render_input.py -v`
Expected: PASS (3개)

- [ ] **Step 5: 커밋**

```bash
git add app/providers/render/__init__.py app/providers/render/input.py tests/test_render_input.py
git commit -m "기능: render 입력(voice mp3·captions srt) 경로 해결기"
```

---

## Task 4: FakeRender + 레지스트리 연결 + conftest

**Files:**
- Create: `app/providers/render/fake.py`
- Modify: `app/providers/base.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_provider_render_fake.py`

**Interfaces:**
- Consumes: `input_audio_path`, `input_srt_path` (Task 3), `StageResult` 계약
- Produces: `FakeRender` (stage="render", name="fake"); `REGISTRY["render"]["fake"]`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_render_fake.py` (신규)

```python
import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.render.fake import FakeRender
from app.utils import storage
from app.utils.errors import AppError

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/8/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/8/captions/captions.srt", "meta": {}}],
}


def _ctx():
    return StageContext(topic="t", input_assets=_ASSETS, workdir="projects/8/render")


@pytest.mark.asyncio
async def test_fake_writes_mp4_and_output(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await FakeRender().run(_ctx())

    written = (tmp_path / "projects/8/render/render.mp4").read_bytes()
    assert len(written) > 0
    assert result.assets[0]["kind"] == AssetKind.VIDEO
    assert result.assets[0]["path"] == "projects/8/render/render.mp4"
    assert result.output["width"] == 1080
    assert result.output["height"] == 1920


@pytest.mark.asyncio
async def test_fake_validates_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", input_assets={}, workdir="projects/8/render")
    with pytest.raises(AppError) as exc:
        await FakeRender().run(ctx)
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_registry_has_render_fake():
    assert REGISTRY["render"]["fake"] is FakeRender
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_provider_render_fake.py -v`
Expected: FAIL (`ModuleNotFoundError: app.providers.render.fake`)

- [ ] **Step 3: 구현** — `app/providers/render/fake.py`

```python
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.render.input import input_audio_path, input_srt_path
from app.utils import storage

_FILENAME = "render.mp4"
_WIDTH, _HEIGHT = 1080, 1920


class FakeRender(Provider):
    """ffmpeg 없이 결정적 더미 mp4를 만드는 개발/테스트용 provider."""

    stage = "render"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        # 실제로 합성하진 않지만 입력 계약은 진짜 provider와 똑같이 검증한다.
        input_audio_path(ctx)
        input_srt_path(ctx)
        data = (f"FAKE-VIDEO[{ctx.attempt}]").encode("utf-8")
        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, data)
        return StageResult(
            output={"provider": "fake", "width": _WIDTH, "height": _HEIGHT, "size_bytes": size},
            assets=[{"kind": AssetKind.VIDEO, "path": rel, "meta": {"size_bytes": size}}],
        )
```

- [ ] **Step 4: 레지스트리 연결** — `app/providers/base.py`

import 블록에 추가:
```python
from app.providers.render.fake import FakeRender  # noqa: E402
```
REGISTRY에 render 줄 추가(captions 아래):
```python
    "captions": {"fake": FakeCaptions, "whisper": WhisperCaptions},
    "render": {"fake": FakeRender},
```

- [ ] **Step 5: conftest에 render fake 강제** — `tests/conftest.py`의 env 블록에 추가

```python
os.environ["CAPTIONS_PROVIDER"] = "fake"  # 통합 테스트는 실제 whisper 모델 없이 fake로
os.environ["RENDER_PROVIDER"] = "fake"  # 통합 테스트는 실제 ffmpeg 없이 fake로
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/test_provider_render_fake.py -v`
Expected: PASS (3개)

- [ ] **Step 7: 커밋**

```bash
git add app/providers/render/fake.py app/providers/base.py tests/conftest.py tests/test_provider_render_fake.py
git commit -m "기능: FakeRender provider 추가·레지스트리 연결(파이프라인 fake 관통)"
```

---

## Task 5: SlideshowRender

**Files:**
- Create: `app/providers/render/slideshow.py`
- Modify: `app/providers/base.py`
- Test: `tests/test_provider_render_slideshow.py`

**Interfaces:**
- Consumes: `input_audio_path`, `input_srt_path` (Task 3); `app.utils.ffmpeg.build_slideshow_cmd/run/ffmpeg_exe` (Task 2); `Settings.render_bg_color/render_font/render_font_size`
- Produces: `SlideshowRender(runner=None, exe=None)` (stage="render", name="slideshow"); `REGISTRY["render"]["slideshow"]`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_render_slideshow.py` (신규)

```python
import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.render.slideshow import SlideshowRender
from app.utils import storage
from app.utils.errors import AppError

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/9/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/9/captions/captions.srt", "meta": {}}],
}
_INPUTS = {"captions": {"duration_sec": 3.5}}

_calls: list[dict] = []


async def _fake_runner(cmd, cwd):
    _calls.append({"cmd": cmd, "cwd": cwd})
    # 진짜 ffmpeg가 out_rel(마지막 인자)에 쓰듯, 파일을 남겨 provider가 크기를 잰다.
    storage.write_bytes(cmd[-1], b"MP4-bytes")


@pytest.fixture(autouse=True)
def _reset():
    _calls.clear()


def _ctx():
    return StageContext(topic="t", inputs=_INPUTS, input_assets=_ASSETS, workdir="projects/9/render")


@pytest.mark.asyncio
async def test_run_invokes_ffmpeg_and_records_video_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    provider = SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg")
    result = await provider.run(_ctx())

    assert result.assets[0]["kind"] == AssetKind.VIDEO
    assert result.assets[0]["path"] == "projects/9/render/render.mp4"
    assert result.output["width"] == 1080
    assert result.output["height"] == 1920
    assert result.output["duration_sec"] == 3.5
    assert result.output["size_bytes"] == len(b"MP4-bytes")


@pytest.mark.asyncio
async def test_run_uses_storage_root_as_cwd_and_relative_srt(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg").run(_ctx())

    call = _calls[0]
    assert call["cwd"] == str(tmp_path)  # 상대경로 필터를 위해 루트에서 실행
    vf = call["cmd"][call["cmd"].index("-vf") + 1]
    assert "subtitles=projects/9/captions/captions.srt" in vf
    # 오디오는 절대경로 입력
    assert str(tmp_path / "projects/9/voice/voice.mp3") in call["cmd"]


@pytest.mark.asyncio
async def test_missing_srt_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs=_INPUTS,
                       input_assets={StageName.VOICE: _ASSETS[StageName.VOICE]},
                       workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg").run(ctx)
    assert exc.value.code == "CAPTIONS_ASSET_MISSING"


def test_registry_has_render_slideshow():
    assert REGISTRY["render"]["slideshow"] is SlideshowRender
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_provider_render_slideshow.py -v`
Expected: FAIL (`ModuleNotFoundError: app.providers.render.slideshow`)

- [ ] **Step 3: 구현** — `app/providers/render/slideshow.py`

```python
from app.config import get_settings
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.render.input import input_audio_path, input_srt_path
from app.utils import ffmpeg, storage

_FILENAME = "render.mp4"
_WIDTH, _HEIGHT = 1080, 1920


class SlideshowRender(Provider):
    """단색 배경 + 단어별 자막 번인 + 오디오로 9:16 mp4를 만드는 provider."""

    stage = "render"
    name = "slideshow"

    def __init__(self, runner=None, exe=None):
        # 테스트는 fake runner/exe를 주입해 ffmpeg 없이 검증한다.
        self._runner = runner or ffmpeg.run
        self._exe = exe

    def _exe_path(self) -> str:
        if self._exe is None:
            self._exe = ffmpeg.ffmpeg_exe()
        return self._exe

    async def run(self, ctx: StageContext) -> StageResult:
        settings = get_settings()
        audio_abs = str(storage.resolve(input_audio_path(ctx)))
        srt_rel = input_srt_path(ctx)
        out_rel = f"{ctx.workdir}/{_FILENAME}"

        cmd = ffmpeg.build_slideshow_cmd(
            exe=self._exe_path(),
            bg_color=settings.render_bg_color,
            audio_abs=audio_abs,
            srt_rel=srt_rel,
            out_rel=out_rel,
            width=_WIDTH,
            height=_HEIGHT,
            font=settings.render_font,
            font_size=settings.render_font_size,
        )
        # cwd를 저장소 루트로 둬야 상대경로 자막 필터가 동작한다(Windows ':' 회피).
        await self._runner(cmd, str(storage.resolve(".")))

        size = storage.resolve(out_rel).stat().st_size
        duration = ctx.inputs.get("captions", {}).get("duration_sec")
        return StageResult(
            output={
                "provider": "slideshow",
                "width": _WIDTH,
                "height": _HEIGHT,
                "duration_sec": duration,
                "size_bytes": size,
            },
            assets=[{"kind": AssetKind.VIDEO, "path": out_rel,
                     "meta": {"size_bytes": size, "width": _WIDTH, "height": _HEIGHT}}],
        )
```

- [ ] **Step 4: 레지스트리 연결** — `app/providers/base.py`

import 추가:
```python
from app.providers.render.slideshow import SlideshowRender  # noqa: E402
```
REGISTRY render 줄을 갱신:
```python
    "render": {"fake": FakeRender, "slideshow": SlideshowRender},
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_provider_render_slideshow.py -v`
Expected: PASS (4개)

- [ ] **Step 6: 커밋**

```bash
git add app/providers/render/slideshow.py app/providers/base.py tests/test_provider_render_slideshow.py
git commit -m "기능: SlideshowRender provider(단색 배경+자막 번인 9:16 mp4)"
```

---

## Task 6: API MIME 타입 + 통합 테스트 (fake 관통)

**Files:**
- Modify: `app/api/projects.py:156`
- Test: `tests/test_api_render.py`

**Interfaces:**
- Consumes: 파이프라인 전체(fake providers), `GET /api/projects/{id}/stages/{name}/asset`
- Produces: `_MEDIA_TYPES[AssetKind.VIDEO] == "video/mp4"`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_api_render.py` (신규)

```python
from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User

_PW = "pw12345"


async def _login(client, db_session, email: str) -> User:
    user = User(email=email, password_hash=hash_password(_PW),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": _PW})
    assert resp.status_code == 200
    return user


async def _project_through_captions(client) -> int:
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    for stage in ("script", "voice", "captions"):
        await client.post(f"/api/projects/{pid}/stages/{stage}/run")
        await client.post(f"/api/projects/{pid}/stages/{stage}/approve")
    return pid


async def test_running_render_produces_video(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "render-run@example.com")
    pid = await _project_through_captions(client)

    detail = (await client.post(f"/api/projects/{pid}/stages/render/run")).json()
    render = next(s for s in detail["stages"] if s["name"] == "render")
    assert render["status"] == "NEEDS_REVIEW"
    assert render["output"]["width"] == 1080

    asset = await client.get(f"/api/projects/{pid}/stages/render/asset")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "video/mp4"


async def test_approving_render_completes_the_project(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "render-done@example.com")
    pid = await _project_through_captions(client)

    await client.post(f"/api/projects/{pid}/stages/render/run")
    detail = (await client.post(f"/api/projects/{pid}/stages/render/approve")).json()
    assert detail["project"]["status"] == "DONE"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_api_render.py -v`
Expected: FAIL (asset content-type이 `application/octet-stream` → `video/mp4` 불일치)

- [ ] **Step 3: 구현** — `app/api/projects.py`의 `_MEDIA_TYPES`

```python
_MEDIA_TYPES = {
    AssetKind.AUDIO: "audio/mpeg",
    AssetKind.SRT: "application/x-subrip",
    AssetKind.VIDEO: "video/mp4",
}
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_api_render.py -v`
Expected: PASS (2개)

- [ ] **Step 5: 전체 백엔드 회귀 확인**

Run: `uv run pytest -q`
Expected: PASS (기존 + 신규 전부)

- [ ] **Step 6: 커밋**

```bash
git add app/api/projects.py tests/test_api_render.py
git commit -m "기능: render 산출물 video/mp4 서빙 + 파이프라인 통합 테스트"
```

---

## Task 7: 프론트엔드 RenderView

**Files:**
- Modify: `web/src/lib/projects.ts`
- Modify: `web/src/pages/projects/ProjectDetail.tsx`

**Interfaces:**
- Consumes: `projects.assetUrl(id, 'render', attempt)`, `Stage.output`
- Produces: `RenderOutput` 타입, `hasRender()` 가드, `RenderView` 컴포넌트

- [ ] **Step 1: 타입·가드 추가** — `web/src/lib/projects.ts`

`CaptionsOutput` 아래에 추가:
```typescript
export type RenderOutput = {
  provider: string
  width: number
  height: number
  duration_sec: number | null
  size_bytes: number
}
```
`Stage.output` 유니온에 `| RenderOutput` 추가:
```typescript
  output: ScriptOutput | VoiceOutput | CaptionsOutput | RenderOutput | Record<string, never>
```
파일 끝 가드 함수들 아래에 추가:
```typescript
export function hasRender(output: Stage['output']): output is RenderOutput {
  return 'width' in output
}
```

- [ ] **Step 2: STAGE_LABEL·RenderView 추가** — `web/src/pages/projects/ProjectDetail.tsx`

import에 `hasRender`, `RenderOutput` 반영:
```typescript
import { hasCaptions, hasRender, hasScript, hasVoice, projects, STAGE_BADGE, type ProjectDetail as Detail, type Stage } from '../../lib/projects'
```
`STAGE_LABEL`에 render 추가:
```typescript
const STAGE_LABEL: Record<string, string> = {
  script: '대본 (script)',
  voice: '음성 (voice)',
  captions: '자막 (captions)',
  render: '영상 (render)',
}
```
`CaptionsView` 컴포넌트 아래에 `RenderView` 추가:
```typescript
function RenderView({ projectId, stage }: { projectId: number; stage: Stage }) {
  if (!hasRender(stage.output)) return null
  const url = projects.assetUrl(projectId, stage.name, stage.attempt)
  return (
    <div className="mt-4 space-y-2 rounded-md border border-slate-200 p-4">
      <video controls className="w-full rounded-md bg-black" src={url} />
      <a
        href={url}
        download="render.mp4"
        className="inline-block rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
      >
        mp4 다운로드
      </a>
      <div className="text-xs text-slate-400">
        {stage.output.width}×{stage.output.height}
        {stage.output.duration_sec !== null && ` · ${stage.output.duration_sec.toFixed(1)}초`}
      </div>
    </div>
  )
}
```
`StageCard`의 View 목록에 추가(`<CaptionsView ... />` 아래):
```typescript
          <CaptionsView projectId={projectId} stage={stage} voiceAttempt={voiceAttempt} />
          <RenderView projectId={projectId} stage={stage} />
```

- [ ] **Step 3: 타입체크·빌드 확인**

Run: `cd web && npm run build`
Expected: 타입 에러 없이 빌드 성공

- [ ] **Step 4: 커밋**

```bash
git add web/src/lib/projects.ts web/src/pages/projects/ProjectDetail.tsx
git commit -m "기능: 상세 화면에 render 영상 카드(재생+mp4 다운로드) 추가"
```

---

## Task 8: 실제 렌더 스모크 검증 (선택, 육안 확인)

목적: 번들 ffmpeg로 실제 mp4가 나오는지, **자막 정렬/크기·한글 폰트**가 의도대로인지 육안 확인. CI 필수는 아니며, 로컬에서 1회 수행한다.

**Files:**
- Create: `tests/test_render_smoke.py` (pytest 마커 `slow`, 기본 실행 제외 가능)

- [ ] **Step 1: 스모크 테스트 작성** — `tests/test_render_smoke.py` (신규)

```python
import wave

import pytest

from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.providers.render.slideshow import SlideshowRender
from app.utils import storage


def _write_wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)  # 1초 무음


@pytest.mark.slow
@pytest.mark.asyncio
async def test_real_ffmpeg_produces_playable_mp4(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    _write_wav(tmp_path / "projects/1/voice/voice.mp3")  # 확장자만 mp3, 내용은 wav여도 ffmpeg가 읽음
    storage.write_bytes("projects/1/captions/captions.srt",
                        "1\n00:00:00,000 --> 00:00:01,000\n안녕하세요\n".encode("utf-8"))

    ctx = StageContext(
        topic="t",
        inputs={"captions": {"duration_sec": 1.0}},
        input_assets={
            StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/1/voice/voice.mp3", "meta": {}}],
            StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/1/captions/captions.srt", "meta": {}}],
        },
        workdir="projects/1/render",
    )
    result = await SlideshowRender().run(ctx)  # 실제 번들 ffmpeg 사용

    out = tmp_path / "projects/1/render/render.mp4"
    assert out.exists() and out.stat().st_size > 0
    assert result.assets[0]["kind"] == AssetKind.VIDEO
    print(f"\n[스모크] 생성됨: {out} ({out.stat().st_size} bytes) — 자막·폰트 육안 확인")
```

- [ ] **Step 2: `slow` 마커 등록** — `pyproject.toml`의 `[tool.pytest.ini_options]`에 추가

```toml
markers = ["slow: 실제 ffmpeg 등 느린 통합 테스트 (기본 실행에 포함)"]
```

- [ ] **Step 3: 스모크 실행 + 육안 검증**

Run: `uv run pytest tests/test_render_smoke.py -v -s`
Expected: PASS. 출력된 경로의 mp4를 열어 (1) 9:16 세로, (2) 자막이 화면 중앙, (3) 한글이 □가 아닌 정상 렌더인지 확인.

- [ ] **Step 4: 필요 시 스타일 상수 조정**

자막이 중앙이 아니거나 크기/한글이 어긋나면 `app/config.py`의 `render_font`/`render_font_size` 또는 `app/utils/ffmpeg.py`의 `Alignment`/`Outline` 값을 조정하고 Step 3을 재실행.

- [ ] **Step 5: 커밋**

```bash
git add tests/test_render_smoke.py pyproject.toml
git commit -m "test: 실제 ffmpeg 렌더 스모크(자막·한글 폰트 육안 검증)"
```

---

## 완료 기준 (Definition of Done)

- `uv run pytest -q` 전부 통과 (스모크 포함 실제 mp4 1개 생성 확인)
- 웹에서 프로젝트 생성 → script·voice·captions·render 순차 실행·승인 → 프로젝트 `DONE`
- 상세 화면에서 render 영상 재생 + mp4 다운로드 동작
- 자막이 9:16 화면 중앙에 한 단어씩, 한글이 정상 렌더
