# stock 렌더러 (Pexels·Pixabay 배경) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대본의 `on_screen`으로 Pexels·Pixabay 무료 API에서 씬별 배경 소재를 찾아 자막·나레이션과 합성하는 `render` provider `stock`을 추가한다.

**Architecture:** `app/utils/stock/`은 studio 도메인을 모르는 순수 검색·다운로드 클라이언트(소스마다 `search(query, kind) -> list[Clip]` 하나만 노출), `app/providers/render/`는 도메인 결정(폴백 체인·씬 시간 배분·합성 지휘)을 담는다. 합성은 씬 입력 N개 + 오디오 1개를 단일 `filter_complex`로 정규화·concat·자막 번인하는 ffmpeg 1회 실행이다. `REGISTRY["render"]`에 한 줄 추가하는 것 외에 `app/core/`·`app/models/`·`app/queries/`·마이그레이션은 손대지 않는다.

**Tech Stack:** Python 3.12 · httpx(신규 런타임 의존성) · imageio-ffmpeg(기존) · pytest/pytest-asyncio · React 19 + TypeScript(프론트)

**상위 스펙:** [docs/superpowers/specs/2026-07-22-stock-render-design.md](../specs/2026-07-22-stock-render-design.md)

## 실행 결정 (2026-07-22, 계획서 본문보다 우선한다)

- **브랜치:** `feat/stock-render` (base `ff57362`)
- **커밋은 사용자가 직접 한다.** 각 Task의 "커밋" Step은 **실행하지 않는다** — 서브에이전트는 구현·테스트까지만 하고, 컨트롤러가 Task 완료 시 커밋 명령을 제안한다. Step에 적힌 커밋 메시지는 그 제안의 초안으로만 쓴다.
- **한국어 검색 적중률은 테스트가 아니라 조사다.** Task 10의 `test_korean_query_hit_counts_are_reported`는 만들지 않는다. 대신 일회성 스크립트 `scripts/probe_stock_hitrate.py`로 측정해 결과를 스펙 리스크 3에 기록한다 (Task 10 Step 4 참조).

## Global Constraints

- **`app/core/`·`app/models/`·`app/queries/`·Alembic 마이그레이션을 수정하지 않는다.** 이 기능은 provider 레지스트리 한 줄로 붙는다.
- **단계당 asset 1개 원칙을 지킨다.** 최종 산출물은 `kind=VIDEO`, `path=projects/{id}/render/render.mp4` 하나뿐이다. 내려받은 소재는 asset으로 기록하지 않는다.
- **`RENDER_PROVIDER` 기본값은 `slideshow`를 유지한다.** 키 없이도 기존 흐름이 깨지면 안 된다.
- **모든 사용자 노출 에러 메시지는 한국어**이며 `AppError(status_code, code, message)`로 던진다. `run_claimed_stage`가 FAILED로 흡수한다.
- **자막 스타일·경로 규칙은 slideshow와 동일**하다. 자막·출력은 저장소 기준 상대경로 + 슬래시, 실행 cwd는 저장소 루트(Windows 드라이브 문자 `:` 회피). 오디오만 절대경로.
- **해상도 1080×1920, fps 30, `libx264`/`yuv420p`/`aac`** 고정.
- 테스트는 **네트워크·실제 ffmpeg 없이** 돈다. 예외는 `@pytest.mark.slow`가 붙은 Task 10뿐이며 키가 없으면 skip한다.
- 파이썬 명령은 전부 `uv run` 접두사를 붙인다. 프론트 명령은 `web/`에서 실행한다.

**스펙 대비 계획의 구조 보정 (의도적):** 스펙 2장은 폴백 체인을 `render/stock.py` 안에 뒀지만, 이 계획은 파일 하나에 하나의 책임을 주기 위해 `render/sources.py`(소재 선택)와 `utils/stock/download.py`(다운로드)로 분리한다. 동작은 스펙과 동일하다.

---

## File Structure

| 파일 | 책임 | Task |
|---|---|---|
| `app/config.py` (수정) | 스톡 설정 5개 | 1 |
| `.env.example` (수정) | 위 5개 + 누락된 `RENDER_*`·`WORKER_CONCURRENCY` | 1 |
| `pyproject.toml` (수정) | `httpx`를 런타임 의존성으로 승격 | 1 |
| `app/utils/stock/base.py` (신규) | `Clip` 데이터클래스 · `StockTooLarge` · 종류 상수 | 2 |
| `app/utils/stock/pexels.py` (신규) | Pexels 검색 → `list[Clip]` | 2 |
| `app/utils/stock/pixabay.py` (신규) | Pixabay 검색 → `list[Clip]` | 3 |
| `app/providers/render/timing.py` (신규) | 씬 → `(start, end)` 글자수 비례 배분 | 4 |
| `app/utils/storage.py` (수정) | `clear_dir()` | 5 |
| `app/utils/stock/download.py` (신규) | 상한·타임아웃 있는 스트리밍 다운로드 | 5 |
| `app/providers/render/sources.py` (신규) | 활성 소스 결정 · 검색어 우선순위 · 폴백 체인 | 6 |
| `app/utils/ffmpeg.py` (수정) | `build_stock_cmd()` · `_style()` 공용 추출 | 7 |
| `app/providers/render/stock.py` (신규) | `StockRender` — 전체 지휘 | 8 |
| `app/providers/base.py` (수정) | REGISTRY 한 줄 | 8 |
| `web/src/lib/projects.ts` (수정) | `RenderSource` 타입 | 9 |
| `web/src/pages/projects/ProjectDetail.tsx` (수정) | 출처 목록 표시 | 9 |

---

## Task 1: 설정 · 의존성

**Files:**
- Modify: `app/config.py:19-31`
- Modify: `.env.example`
- Modify: `pyproject.toml:6-30`
- Test: `tests/test_config.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `Settings.pexels_api_key: str`, `Settings.pixabay_api_key: str`, `Settings.stock_sources: list[str]`, `Settings.stock_max_bytes: int`, `Settings.stock_timeout_sec: int`. 이후 모든 태스크가 `get_settings()`로 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config.py` 끝에 추가한다. 기존 테스트들과 같은 `importlib.reload` + `cache_clear` 관례를 따른다 — `get_settings`가 `lru_cache`라 이 두 줄이 없으면 앞 테스트의 캐시를 본다.

```python
def test_stock_settings_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    for key in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "STOCK_SOURCES",
                "STOCK_MAX_BYTES", "STOCK_TIMEOUT_SEC"):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    s = config_module.get_settings()
    assert s.pexels_api_key == ""
    assert s.pixabay_api_key == ""
    assert s.stock_sources == ["pexels", "pixabay"]   # 순서가 폴백 우선순위
    assert s.stock_max_bytes == 52_428_800            # 50MB
    assert s.stock_timeout_sec == 30


def test_stock_sources_parsed_from_json_env(monkeypatch):
    # CORS_ORIGINS와 같은 JSON 배열 표기. 순서를 바꿔 Pixabay를 먼저 쓸 수 있어야 한다.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("STOCK_SOURCES", '["pixabay"]')
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    assert config_module.get_settings().stock_sources == ["pixabay"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_config.py -k stock -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'pexels_api_key'`

- [ ] **Step 3: 설정 추가**

`app/config.py`의 `worker_concurrency` 줄 바로 아래에 추가한다.

```python
    # 스톡 소재(Pexels·Pixabay). 키가 하나도 없으면 stock 렌더러는 validate에서 실패한다.
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    stock_sources: list[str] = ["pexels", "pixabay"]  # 순서가 폴백 우선순위
    stock_max_bytes: int = 52_428_800                 # 씬당 다운로드 상한 50MB
    stock_timeout_sec: int = 30
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (기존 4개 + 신규 2개)

- [ ] **Step 5: `.env.example` 채우기**

현재 `RENDER_*`·`WORKER_CONCURRENCY`가 빠져 있다. 파일 끝(`WHISPER_MODEL=small` 다음)에 이어 붙인다.

```
RENDER_PROVIDER=slideshow
RENDER_BG_COLOR=#0f172a
RENDER_FONT=Malgun Gothic
RENDER_FONT_SIZE=30
# 단계 동시 실행 수. whisper·ffmpeg가 CPU를 포화시켜 기본 1을 권장.
WORKER_CONCURRENCY=1

# 스톡 배경 소재 — RENDER_PROVIDER=stock 일 때만 쓴다. 둘 다 무료 발급.
#   Pexels  https://www.pexels.com/api/   (200 req/hour)
#   Pixabay https://pixabay.com/api/docs/ (100 req/60s)
PEXELS_API_KEY=
PIXABAY_API_KEY=
# 검색 순서 = 폴백 우선순위. 키가 있는 소스만 실제로 쓰인다.
STOCK_SOURCES=["pexels","pixabay"]
STOCK_MAX_BYTES=52428800
STOCK_TIMEOUT_SEC=30
```

- [ ] **Step 6: `httpx`를 런타임 의존성으로 승격**

`pyproject.toml`의 `[project].dependencies` 마지막(`"imageio-ffmpeg>=0.6.0",` 다음)에 추가하고, `[dependency-groups].dev`에서 `"httpx>=0.28",` 줄을 **삭제**한다(중복 방지).

```toml
    "imageio-ffmpeg>=0.6.0",
    "httpx>=0.28",
]
```

- [ ] **Step 7: 의존성 동기화 후 전체 테스트**

Run: `uv sync`
Run: `uv run pytest -q`
Expected: 기존 테스트 전부 PASS. `httpx`가 dev에서 빠져도 테스트가 여전히 import된다(런타임 의존성이 되었으므로).

- [ ] **Step 8: 커밋**

```bash
git add app/config.py .env.example pyproject.toml uv.lock tests/test_config.py
git commit -m "설정: 스톡 소재(Pexels·Pixabay) 설정 추가 + httpx 런타임 승격"
```

---

## Task 2: `Clip` 표현 · Pexels 소스

**Files:**
- Create: `app/utils/stock/__init__.py` (빈 파일)
- Create: `app/utils/stock/base.py`
- Create: `app/utils/stock/pexels.py`
- Test: `tests/test_stock_pexels.py`

**Interfaces:**
- Consumes: `Settings.pexels_api_key` (Task 1)
- Produces:
  - `app.utils.stock.base`: `VIDEO = "video"`, `PHOTO = "photo"`, `Clip` (frozen dataclass: `source, kind, id, url, page_url, author, width, height, duration_sec=None`, property `key -> tuple[str, str]`), `StockTooLarge(Exception)`
  - `app.utils.stock.pexels`: `PexelsSource` — `name = "pexels"`, `__init__(self, get_json=None)`, `async search(self, query: str, kind: str) -> list[Clip]`. HTTP 오류는 **삼키지 않고 그대로 올린다** (호출자인 Task 6의 체인이 잡아 다음 소스로 넘어간다).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_stock_pexels.py`를 만든다.

```python
import httpx
import pytest

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pexels import PexelsSource


@pytest.fixture(autouse=True)
def _fresh_settings():
    # get_settings는 lru_cache라 monkeypatch.setenv가 캐시된 Settings에 반영되지 않는다.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_VIDEO_RESPONSE = {
    "videos": [
        {
            "id": 111,
            "url": "https://www.pexels.com/video/seoul-111/",
            "duration": 12,
            "user": {"name": "홍길동"},
            "video_files": [
                {"link": "https://cdn/small.mp4", "width": 640, "height": 360, "file_type": "video/mp4"},
                {"link": "https://cdn/portrait.mp4", "width": 1080, "height": 1920, "file_type": "video/mp4"},
                {"link": "https://cdn/huge.mp4", "width": 2160, "height": 3840, "file_type": "video/mp4"},
            ],
        }
    ]
}

_PHOTO_RESPONSE = {
    "photos": [
        {
            "id": 222,
            "url": "https://www.pexels.com/photo/cafe-222/",
            "photographer": "김철수",
            "width": 4000,
            "height": 6000,
            "src": {"original": "https://cdn/orig.jpg", "large2x": "https://cdn/large2x.jpg"},
        }
    ]
}


def _stub(payload, spy=None):
    async def _get_json(url, params, headers):
        if spy is not None:
            spy.append({"url": url, "params": params, "headers": headers})
        return payload

    return _get_json


@pytest.mark.asyncio
async def test_video_search_maps_to_clip(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    clips = await PexelsSource(get_json=_stub(_VIDEO_RESPONSE)).search("서울 야경", VIDEO)

    assert len(clips) == 1
    clip = clips[0]
    assert clip.source == "pexels"
    assert clip.kind == VIDEO
    assert clip.id == "111"
    assert clip.page_url == "https://www.pexels.com/video/seoul-111/"
    assert clip.author == "홍길동"
    assert clip.duration_sec == 12.0
    assert clip.key == ("pexels", "111")


@pytest.mark.asyncio
async def test_video_search_prefers_portrait_1080_over_bigger_landscape(monkeypatch):
    # 세로 > 1080 이상 > 작은 파일 순. 4K 세로(huge)보다 딱 맞는 1080 세로를 고른다.
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    clips = await PexelsSource(get_json=_stub(_VIDEO_RESPONSE)).search("서울 야경", VIDEO)
    assert clips[0].url == "https://cdn/portrait.mp4"
    assert (clips[0].width, clips[0].height) == (1080, 1920)


@pytest.mark.asyncio
async def test_video_search_sends_korean_locale_and_portrait(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "secret-key")
    spy = []
    await PexelsSource(get_json=_stub(_VIDEO_RESPONSE, spy)).search("서울 야경", VIDEO)

    call = spy[0]
    assert call["params"]["query"] == "서울 야경"
    assert call["params"]["locale"] == "ko-KR"
    assert call["params"]["orientation"] == "portrait"
    # Pexels는 Bearer가 아니라 키를 그대로 Authorization에 넣는다
    assert call["headers"] == {"Authorization": "secret-key"}


@pytest.mark.asyncio
async def test_photo_search_maps_to_clip(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    clips = await PexelsSource(get_json=_stub(_PHOTO_RESPONSE)).search("카페", PHOTO)

    assert clips[0].kind == PHOTO
    assert clips[0].url == "https://cdn/orig.jpg"   # 원본 우선 — 크롭 여유가 크다
    assert clips[0].author == "김철수"
    assert clips[0].duration_sec is None


@pytest.mark.asyncio
async def test_empty_response_returns_empty_list(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    assert await PexelsSource(get_json=_stub({"videos": []})).search("없는말", VIDEO) == []


@pytest.mark.asyncio
async def test_http_error_propagates(monkeypatch):
    # 소스는 오류를 삼키지 않는다. 소스를 건너뛸지는 폴백 체인(sources.py)이 결정한다.
    monkeypatch.setenv("PEXELS_API_KEY", "k")

    async def _boom(url, params, headers):
        raise httpx.HTTPStatusError("429", request=None, response=None)

    with pytest.raises(httpx.HTTPStatusError):
        await PexelsSource(get_json=_boom).search("q", VIDEO)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_stock_pexels.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.stock'`

- [ ] **Step 3: `app/utils/stock/__init__.py` 생성 (빈 파일)**

```bash
touch app/utils/stock/__init__.py
```

- [ ] **Step 4: `app/utils/stock/base.py` 작성**

```python
from dataclasses import dataclass

VIDEO = "video"
PHOTO = "photo"


class StockTooLarge(Exception):
    """소재가 STOCK_MAX_BYTES를 넘었다. 이 후보만 건너뛰라는 신호."""


@dataclass(frozen=True)
class Clip:
    """소스 중립 스톡 소재 1건. 어느 API에서 왔든 이 모양으로 통일한다."""

    source: str            # "pexels" | "pixabay"
    kind: str              # VIDEO | PHOTO
    id: str                # 소스 내 고유 id
    url: str               # 내려받을 실제 파일 URL
    page_url: str          # 출처 표기용 소스 페이지 링크
    author: str            # 작가명 (없으면 "")
    width: int
    height: int
    duration_sec: float | None = None   # 이미지는 None

    @property
    def key(self) -> tuple[str, str]:
        """씬 간 중복 배제 키. 소스가 달라도 id가 겹칠 수 있어 소스명을 함께 쓴다."""
        return (self.source, self.id)
```

- [ ] **Step 5: `app/utils/stock/pexels.py` 작성**

```python
import httpx

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO, Clip

# 문서상 경로. 스모크(Task 10)에서 404가 나면 "https://api.pexels.com/videos/search"로 바꾼다.
_VIDEO_URL = "https://api.pexels.com/v1/videos/search"
_PHOTO_URL = "https://api.pexels.com/v1/search"
_PER_PAGE = 15
_TIMEOUT_SEC = 15.0
_NAME = "pexels"


async def _get_json(url: str, params: dict, headers: dict) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _best_file(files: list[dict]) -> dict | None:
    """세로 > 짧은 변 1080 이상 > 파일 작은 순. 세로 원본이 있으면 크롭 손실이 없다."""
    usable = [f for f in files if f.get("link") and f.get("width") and f.get("height")]
    if not usable:
        return None

    def score(f: dict) -> tuple[int, int, int]:
        return (
            1 if f["height"] > f["width"] else 0,
            1 if min(f["width"], f["height"]) >= 1080 else 0,
            -(f["width"] * f["height"]),   # 조건이 같으면 작은 파일 (다운로드 절약)
        )

    return max(usable, key=score)


def _video_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("videos") or []:
        file = _best_file(hit.get("video_files") or [])
        if file is None:
            continue
        duration = float(hit.get("duration") or 0)
        clips.append(Clip(
            source=_NAME, kind=VIDEO, id=str(hit.get("id", "")),
            url=file["link"], page_url=hit.get("url", ""),
            author=(hit.get("user") or {}).get("name", ""),
            width=file["width"], height=file["height"],
            duration_sec=duration or None,
        ))
    return clips


def _photo_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("photos") or []:
        src = hit.get("src") or {}
        # 원본 우선 — 9:16으로 크롭할 여유가 크다. 상한 초과는 다운로드 단계가 거른다.
        url = src.get("original") or src.get("large2x")
        if not url:
            continue
        clips.append(Clip(
            source=_NAME, kind=PHOTO, id=str(hit.get("id", "")),
            url=url, page_url=hit.get("url", ""),
            author=hit.get("photographer", ""),
            width=hit.get("width") or 0, height=hit.get("height") or 0,
        ))
    return clips


class PexelsSource:
    """Pexels 무료 API 검색. HTTP 오류는 삼키지 않는다 — 소스를 건너뛸지는 호출자가 정한다."""

    name = _NAME

    def __init__(self, get_json=None):
        # 테스트는 가짜 get_json을 주입해 네트워크 없이 검증한다.
        self._get_json = get_json or _get_json

    async def search(self, query: str, kind: str) -> list[Clip]:
        url = _VIDEO_URL if kind == VIDEO else _PHOTO_URL
        params = {
            "query": query,
            "per_page": _PER_PAGE,
            "orientation": "portrait",
            "locale": "ko-KR",   # 한국어 검색어 공식 지원
        }
        headers = {"Authorization": get_settings().pexels_api_key}
        data = await self._get_json(url, params, headers)
        return _video_clips(data) if kind == VIDEO else _photo_clips(data)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_stock_pexels.py -v`
Expected: PASS (6개)

- [ ] **Step 7: 커밋**

```bash
git add app/utils/stock/ tests/test_stock_pexels.py
git commit -m "기능: Clip 표현과 Pexels 스톡 검색 소스 추가"
```

---

## Task 3: Pixabay 소스

**Files:**
- Create: `app/utils/stock/pixabay.py`
- Test: `tests/test_stock_pixabay.py`

**Interfaces:**
- Consumes: `Clip`, `VIDEO`, `PHOTO` (Task 2), `Settings.pixabay_api_key` (Task 1)
- Produces: `app.utils.stock.pixabay.PixabaySource` — `name = "pixabay"`, `__init__(self, get_json=None)`, `async search(self, query: str, kind: str) -> list[Clip]`. `PexelsSource`와 **완전히 같은 시그니처**라 Task 6의 체인이 둘을 구분하지 않는다.

> **주의:** Pixabay 공식 문서가 봇 차단(403)이라 아래 응답 모양은 널리 쓰이는 형태를 옮긴 것이다. Task 10 스모크에서 실제 응답을 찍어보고 어긋나면 `_video_clips`/`_photo_clips`와 이 파일의 픽스처를 **함께** 고친다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_stock_pixabay.py`를 만든다.

```python
import httpx
import pytest

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pixabay import PixabaySource

_VIDEO_RESPONSE = {
    "hits": [
        {
            "id": 333,
            "pageURL": "https://pixabay.com/videos/rain-333/",
            "duration": 18,
            "user": "이영희",
            "videos": {
                "large": {"url": "https://cdn/large.mp4", "width": 1920, "height": 1080},
                "medium": {"url": "https://cdn/medium.mp4", "width": 1280, "height": 720},
                "tiny": {"url": "https://cdn/tiny.mp4", "width": 640, "height": 360},
            },
        }
    ]
}

_PHOTO_RESPONSE = {
    "hits": [
        {
            "id": 444,
            "pageURL": "https://pixabay.com/photos/road-444/",
            "user": "박민수",
            "largeImageURL": "https://cdn/large.jpg",
            "imageWidth": 3000,
            "imageHeight": 4500,
        }
    ]
}


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _stub(payload, spy=None):
    async def _get_json(url, params, headers):
        if spy is not None:
            spy.append({"url": url, "params": params, "headers": headers})
        return payload

    return _get_json


@pytest.mark.asyncio
async def test_video_search_maps_to_clip(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    clips = await PixabaySource(get_json=_stub(_VIDEO_RESPONSE)).search("빗소리", VIDEO)

    assert len(clips) == 1
    clip = clips[0]
    assert clip.source == "pixabay"
    assert clip.kind == VIDEO
    assert clip.id == "333"
    assert clip.url == "https://cdn/large.mp4"   # large > medium > small > tiny
    assert clip.page_url == "https://pixabay.com/videos/rain-333/"
    assert clip.author == "이영희"
    assert clip.duration_sec == 18.0
    assert clip.key == ("pixabay", "333")


@pytest.mark.asyncio
async def test_video_search_sends_key_and_korean_lang(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "secret-key")
    spy = []
    await PixabaySource(get_json=_stub(_VIDEO_RESPONSE, spy)).search("빗소리", VIDEO)

    call = spy[0]
    # Pixabay는 헤더가 아니라 쿼리스트링으로 인증한다
    assert call["params"]["key"] == "secret-key"
    assert call["params"]["q"] == "빗소리"
    assert call["params"]["lang"] == "ko"
    assert call["headers"] == {}
    # 영상에는 orientation 파라미터가 없다 — 가로 소재는 ffmpeg crop이 흡수한다
    assert "orientation" not in call["params"]


@pytest.mark.asyncio
async def test_photo_search_sends_vertical_orientation(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    spy = []
    clips = await PixabaySource(get_json=_stub(_PHOTO_RESPONSE, spy)).search("도로", PHOTO)

    assert spy[0]["params"]["orientation"] == "vertical"
    assert spy[0]["params"]["image_type"] == "photo"
    assert clips[0].kind == PHOTO
    assert clips[0].url == "https://cdn/large.jpg"
    assert clips[0].author == "박민수"
    assert (clips[0].width, clips[0].height) == (3000, 4500)
    assert clips[0].duration_sec is None


@pytest.mark.asyncio
async def test_video_hit_without_usable_url_is_skipped(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    payload = {"hits": [{"id": 1, "videos": {"large": {"url": ""}}}]}
    assert await PixabaySource(get_json=_stub(payload)).search("q", VIDEO) == []


@pytest.mark.asyncio
async def test_empty_response_returns_empty_list(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    assert await PixabaySource(get_json=_stub({"hits": []})).search("없는말", VIDEO) == []


@pytest.mark.asyncio
async def test_http_error_propagates(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")

    async def _boom(url, params, headers):
        raise httpx.HTTPStatusError("429", request=None, response=None)

    with pytest.raises(httpx.HTTPStatusError):
        await PixabaySource(get_json=_boom).search("q", VIDEO)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_stock_pixabay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.stock.pixabay'`

- [ ] **Step 3: `app/utils/stock/pixabay.py` 작성**

```python
import httpx

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO, Clip

_VIDEO_URL = "https://pixabay.com/api/videos/"
_PHOTO_URL = "https://pixabay.com/api/"
_PER_PAGE = 20          # Pixabay 허용 범위 3~200
_TIMEOUT_SEC = 15.0
_NAME = "pixabay"
_SIZES = ("large", "medium", "small", "tiny")   # 큰 것부터


async def _get_json(url: str, params: dict, headers: dict) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _best_video(videos: dict) -> dict | None:
    """가장 큰 해상도부터 실제 url이 있는 첫 항목."""
    for size in _SIZES:
        item = videos.get(size) or {}
        if item.get("url"):
            return item
    return None


def _video_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("hits") or []:
        item = _best_video(hit.get("videos") or {})
        if item is None:
            continue
        duration = float(hit.get("duration") or 0)
        clips.append(Clip(
            source=_NAME, kind=VIDEO, id=str(hit.get("id", "")),
            url=item["url"], page_url=hit.get("pageURL", ""),
            author=hit.get("user", ""),
            width=item.get("width") or 0, height=item.get("height") or 0,
            duration_sec=duration or None,
        ))
    return clips


def _photo_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("hits") or []:
        url = hit.get("largeImageURL")
        if not url:
            continue
        clips.append(Clip(
            source=_NAME, kind=PHOTO, id=str(hit.get("id", "")),
            url=url, page_url=hit.get("pageURL", ""),
            author=hit.get("user", ""),
            width=hit.get("imageWidth") or 0, height=hit.get("imageHeight") or 0,
        ))
    return clips


class PixabaySource:
    """Pixabay 무료 API 검색. PexelsSource와 같은 인터페이스라 체인이 둘을 구분하지 않는다."""

    name = _NAME

    def __init__(self, get_json=None):
        # 테스트는 가짜 get_json을 주입해 네트워크 없이 검증한다.
        self._get_json = get_json or _get_json

    async def search(self, query: str, kind: str) -> list[Clip]:
        params = {
            "key": get_settings().pixabay_api_key,   # 헤더가 아니라 쿼리스트링 인증
            "q": query,
            "lang": "ko",        # 한국어 검색어 공식 지원
            "per_page": _PER_PAGE,
            "safesearch": "true",
        }
        if kind == VIDEO:
            url = _VIDEO_URL     # 영상에는 orientation이 없다 — crop이 흡수한다
        else:
            url = _PHOTO_URL
            params |= {"image_type": "photo", "orientation": "vertical"}
        data = await self._get_json(url, params, {})
        return _video_clips(data) if kind == VIDEO else _photo_clips(data)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_stock_pixabay.py -v`
Expected: PASS (6개)

- [ ] **Step 5: 커밋**

```bash
git add app/utils/stock/pixabay.py tests/test_stock_pixabay.py
git commit -m "기능: Pixabay 스톡 검색 소스 추가"
```

---

## Task 4: 씬 시간 배분

**Files:**
- Create: `app/providers/render/timing.py`
- Test: `tests/test_render_timing.py`

**Interfaces:**
- Consumes: `AppError` (`app.utils.errors`)
- Produces: `app.providers.render.timing.scene_spans(scenes: list[dict], duration_sec: float | None) -> list[tuple[float, float]]`. 씬 개수만큼의 `(start, end)`를 돌려주며 `spans[-1][1] == duration_sec`을 보장한다. 씬이 없으면 `SCRIPT_SCENES_MISSING`, duration이 없거나 0 이하면 `CAPTIONS_DURATION_MISSING`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_render_timing.py`를 만든다.

```python
import pytest

from app.providers.render.timing import scene_spans
from app.utils.errors import AppError


def _scenes(*narrations):
    return [{"index": i + 1, "narration": n, "on_screen": "x"} for i, n in enumerate(narrations)]


def test_splits_by_narration_length():
    # 글자수 40 / 60 / 50, 전체 150 → 30초를 8 / 12 / 10초로 나눈다
    scenes = _scenes("가" * 40, "나" * 60, "다" * 50)
    spans = scene_spans(scenes, 30.0)

    assert spans[0] == (0.0, 8.0)
    assert spans[1] == (8.0, 20.0)
    assert spans[2] == (20.0, 30.0)


def test_last_span_absorbs_rounding_and_ends_exactly_at_duration():
    # 3등분이 딱 안 떨어지는 길이 — 마지막 씬이 오차를 흡수해야 합이 정확히 맞는다
    spans = scene_spans(_scenes("가", "나", "다"), 10.0)
    assert spans[-1][1] == 10.0
    assert sum(end - start for start, end in spans) == pytest.approx(10.0)


def test_spans_are_contiguous():
    spans = scene_spans(_scenes("가" * 3, "나" * 7), 12.0)
    assert spans[0][1] == spans[1][0]   # 틈도 겹침도 없어야 concat 길이가 맞는다


def test_single_scene_takes_whole_duration():
    assert scene_spans(_scenes("가나다"), 7.5) == [(0.0, 7.5)]


def test_all_empty_narration_falls_back_to_even_split():
    # 0 나눗셈 방지. 대본이 비어도 실패 대신 균등 분할로 진행한다.
    spans = scene_spans(_scenes("", "  ", ""), 9.0)
    assert spans[0] == (0.0, 3.0)
    assert spans[1] == (3.0, 6.0)
    assert spans[2] == (6.0, 9.0)


def test_no_scenes_raises_script_scenes_missing():
    with pytest.raises(AppError) as exc:
        scene_spans([], 10.0)
    assert exc.value.code == "SCRIPT_SCENES_MISSING"


@pytest.mark.parametrize("duration", [None, 0, -1.0])
def test_missing_duration_raises_captions_duration_missing(duration):
    with pytest.raises(AppError) as exc:
        scene_spans(_scenes("가"), duration)
    assert exc.value.code == "CAPTIONS_DURATION_MISSING"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_render_timing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.render.timing'`

- [ ] **Step 3: `app/providers/render/timing.py` 작성**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_render_timing.py -v`
Expected: PASS (9개 — parametrize 3개 포함)

- [ ] **Step 5: 커밋**

```bash
git add app/providers/render/timing.py tests/test_render_timing.py
git commit -m "기능: 씬 시간을 나레이션 글자수 비례로 배분하는 timing 추가"
```

---

## Task 5: 소재 다운로드 · 디렉토리 정리

**Files:**
- Modify: `app/utils/storage.py:28-30` (`delete` 아래에 추가)
- Create: `app/utils/stock/download.py`
- Test: `tests/test_storage.py` (기존 파일에 추가)
- Test: `tests/test_stock_download.py`

**Interfaces:**
- Consumes: `storage.resolve` (기존), `StockTooLarge` (Task 2)
- Produces:
  - `app.utils.storage.clear_dir(rel: str) -> None` — 디렉토리 안 파일을 모두 지운다. 없으면 조용히 통과(멱등).
  - `app.utils.stock.download.download(url: str, rel: str, max_bytes: int, timeout_sec: int, transport=None) -> int` — 스트리밍 저장, 쓴 바이트 수 반환. 상한 초과 시 `StockTooLarge`, HTTP 오류 시 `httpx.HTTPStatusError`. **어느 실패든 부분 파일을 지운다.**

- [ ] **Step 1: `clear_dir` 실패 테스트 작성**

`tests/test_storage.py` 끝에 추가한다.

```python
def test_clear_dir_removes_files_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("projects/3/render/sources/scene1.mp4", b"a")
    storage.write_bytes("projects/3/render/sources/scene2.jpg", b"b")

    storage.clear_dir("projects/3/render/sources")
    assert list((tmp_path / "projects/3/render/sources").iterdir()) == []

    storage.clear_dir("projects/3/render/sources")          # 두 번째도 통과
    storage.clear_dir("projects/3/render/does-not-exist")   # 없는 디렉토리도 통과


def test_clear_dir_leaves_sibling_files(monkeypatch, tmp_path):
    # 소재만 지우고 같은 단계의 render.mp4는 건드리지 않아야 한다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("projects/3/render/render.mp4", b"keep")
    storage.write_bytes("projects/3/render/sources/scene1.mp4", b"drop")

    storage.clear_dir("projects/3/render/sources")
    assert (tmp_path / "projects/3/render/render.mp4").read_bytes() == b"keep"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_storage.py -k clear_dir -v`
Expected: FAIL — `AttributeError: module 'app.utils.storage' has no attribute 'clear_dir'`

- [ ] **Step 3: `clear_dir` 구현**

`app/utils/storage.py`의 `delete` 함수 아래에 추가한다.

```python
def clear_dir(rel: str) -> None:
    """디렉토리 안의 파일을 모두 지운다. 없어도 조용히 통과한다(멱등).

    stock 렌더러가 재실행될 때 이전 소재를 남기지 않기 위한 것. 소재는 asset으로
    기록하지 않아 _replace_assets가 지워주지 않으므로 provider가 직접 비운다.
    하위 디렉토리는 건드리지 않는다 — 소재는 평평하게 저장된다.
    """
    path = resolve(rel)
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_storage.py -v`
Expected: PASS (기존 4개 + 신규 2개)

- [ ] **Step 5: `download` 실패 테스트 작성**

`tests/test_stock_download.py`를 만든다. `httpx.MockTransport`로 네트워크 없이 스트리밍 응답을 흉내낸다.

```python
import httpx
import pytest

from app.utils import storage
from app.utils.stock.base import StockTooLarge
from app.utils.stock.download import download


def _transport(response_factory):
    return httpx.MockTransport(lambda request: response_factory(request))


@pytest.mark.asyncio
async def test_download_writes_file_and_returns_size(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"x" * 500))

    written = await download("https://cdn/clip.mp4", "projects/5/render/sources/scene1.mp4",
                             max_bytes=1000, timeout_sec=5, transport=transport)

    assert written == 500
    assert (tmp_path / "projects/5/render/sources/scene1.mp4").read_bytes() == b"x" * 500


@pytest.mark.asyncio
async def test_download_creates_parent_directories(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"ok"))

    await download("https://cdn/c.mp4", "projects/6/render/sources/scene1.mp4",
                   max_bytes=1000, timeout_sec=5, transport=transport)

    assert (tmp_path / "projects/6/render/sources/scene1.mp4").exists()


@pytest.mark.asyncio
async def test_download_over_limit_raises_and_removes_partial_file(monkeypatch, tmp_path):
    # 반쪽짜리 파일을 ffmpeg에 물리면 원인 찾기 어려운 실패가 난다 — 반드시 지운다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"x" * 5000))

    with pytest.raises(StockTooLarge):
        await download("https://cdn/huge.mp4", "projects/7/render/sources/scene1.mp4",
                       max_bytes=100, timeout_sec=5, transport=transport)

    assert not (tmp_path / "projects/7/render/sources/scene1.mp4").exists()


@pytest.mark.asyncio
async def test_download_http_error_raises_and_removes_partial_file(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(404))

    with pytest.raises(httpx.HTTPStatusError):
        await download("https://cdn/gone.mp4", "projects/8/render/sources/scene1.mp4",
                       max_bytes=1000, timeout_sec=5, transport=transport)

    assert not (tmp_path / "projects/8/render/sources/scene1.mp4").exists()


@pytest.mark.asyncio
async def test_download_rejects_path_outside_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"x"))

    with pytest.raises(ValueError):
        await download("https://cdn/c.mp4", "../escape.mp4",
                       max_bytes=1000, timeout_sec=5, transport=transport)
```

- [ ] **Step 6: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_stock_download.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.stock.download'`

- [ ] **Step 7: `app/utils/stock/download.py` 작성**

```python
import httpx

from app.utils import storage
from app.utils.stock.base import StockTooLarge

_CHUNK_MESSAGE = "소재가 상한을 넘었습니다"


async def download(url: str, rel: str, max_bytes: int, timeout_sec: int, transport=None) -> int:
    """url을 저장소 rel 경로로 스트리밍 저장하고 쓴 바이트 수를 돌려준다.

    상한을 넘으면 즉시 StockTooLarge. 어떤 실패든 부분 파일을 지우고 예외를 올린다 —
    반쪽짜리 파일이 남으면 ffmpeg가 원인 불명으로 죽는다. 이 후보를 건너뛰고
    다음 후보로 갈지는 호출자(StockRender)가 정한다.
    """
    path = storage.resolve(rel)   # 저장소 밖 경로는 여기서 ValueError
    path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec, follow_redirects=True, transport=transport
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with path.open("wb") as out:
                    async for chunk in response.aiter_bytes():
                        written += len(chunk)
                        if written > max_bytes:
                            raise StockTooLarge(f"{_CHUNK_MESSAGE}({max_bytes} bytes): {url}")
                        out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return written
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run pytest tests/test_stock_download.py tests/test_storage.py -v`
Expected: PASS (다운로드 5개 + 저장소 6개)

- [ ] **Step 9: 커밋**

```bash
git add app/utils/storage.py app/utils/stock/download.py tests/test_storage.py tests/test_stock_download.py
git commit -m "기능: 상한·타임아웃 있는 소재 다운로드와 storage.clear_dir 추가"
```

---

## Task 6: 소재 선택 (폴백 체인)

**Files:**
- Create: `app/providers/render/sources.py`
- Test: `tests/test_render_sources.py`

**Interfaces:**
- Consumes: `Clip`, `VIDEO`, `PHOTO` (Task 2), `PexelsSource` (Task 2), `PixabaySource` (Task 3), `Settings.stock_sources`·`pexels_api_key`·`pixabay_api_key` (Task 1)
- Produces:
  - `DEFAULT_QUERY = "abstract background"`
  - `enabled_sources() -> list` — 설정 순서대로, 키가 있는 소스만. 하나도 없으면 `AppError(400, "STOCK_API_KEY_MISSING", ...)`
  - `queries_for(on_screen: str, topic: str) -> list[str]` — 검색어 우선순위, 빈 문자열·중복 제거
  - `async select_clip(sources, queries, used_keys: set, offset: int) -> tuple[Clip, str]` — `(고른 클립, 실제로 먹힌 검색어)`. 전부 0건이면 `AppError(502, "STOCK_NO_RESULTS", ...)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_render_sources.py`를 만든다.

```python
import pytest

from app.config import get_settings
from app.providers.render.sources import (
    DEFAULT_QUERY,
    enabled_sources,
    queries_for,
    select_clip,
)
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO, VIDEO, Clip


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _clip(source, clip_id, kind=VIDEO):
    return Clip(source=source, kind=kind, id=clip_id, url=f"https://cdn/{clip_id}",
                page_url=f"https://page/{clip_id}", author="a", width=1080, height=1920)


class _FakeSource:
    """(query, kind) -> list[Clip] 또는 예외. 호출 순서를 calls에 남긴다."""

    def __init__(self, name, table):
        self.name = name
        self.table = table
        self.calls = []

    async def search(self, query, kind):
        self.calls.append((query, kind))
        result = self.table.get((query, kind))
        if isinstance(result, Exception):
            raise result
        return list(result or [])


# --- queries_for -------------------------------------------------------------

def test_queries_for_orders_on_screen_then_topic_then_default():
    assert queries_for("서울 야경", "도시 여행") == ["서울 야경", "도시 여행", DEFAULT_QUERY]


def test_queries_for_drops_blank_and_duplicate():
    assert queries_for("   ", "도시") == ["도시", DEFAULT_QUERY]
    assert queries_for("도시", "도시") == ["도시", DEFAULT_QUERY]


# --- select_clip -------------------------------------------------------------

@pytest.mark.asyncio
async def test_picks_first_source_video_for_first_query():
    src = _FakeSource("pexels", {("서울", VIDEO): [_clip("pexels", "1")]})
    clip, query = await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert clip.id == "1"
    assert query == "서울"
    assert src.calls == [("서울", VIDEO)]   # 찾았으면 더 뒤지지 않는다


@pytest.mark.asyncio
async def test_relevance_beats_media_kind():
    # 이 계획의 핵심 순서: on_screen 사진이 topic 영상보다 우선한다
    src = _FakeSource("pexels", {
        ("서울", VIDEO): [],
        ("서울", PHOTO): [_clip("pexels", "photo1", PHOTO)],
        ("도시", VIDEO): [_clip("pexels", "video1")],
    })
    clip, query = await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert clip.id == "photo1"
    assert query == "서울"


@pytest.mark.asyncio
async def test_falls_back_to_topic_when_first_query_is_empty_everywhere():
    src = _FakeSource("pexels", {
        ("서울", VIDEO): [], ("서울", PHOTO): [],
        ("도시", VIDEO): [_clip("pexels", "v")],
    })
    clip, query = await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert query == "도시"


@pytest.mark.asyncio
async def test_falls_back_to_second_source_within_same_query_and_kind():
    first = _FakeSource("pexels", {("서울", VIDEO): []})
    second = _FakeSource("pixabay", {("서울", VIDEO): [_clip("pixabay", "p1")]})
    clip, _ = await select_clip([first, second], ["서울"], set(), 0)

    assert clip.source == "pixabay"


@pytest.mark.asyncio
async def test_source_exception_skips_to_next_source():
    # API가 429/5xx를 내도 전체를 실패시키지 않는다
    boom = _FakeSource("pexels", {("서울", VIDEO): RuntimeError("429")})
    ok = _FakeSource("pixabay", {("서울", VIDEO): [_clip("pixabay", "p1")]})
    clip, _ = await select_clip([boom, ok], ["서울"], set(), 0)

    assert clip.source == "pixabay"


@pytest.mark.asyncio
async def test_excludes_already_used_clips():
    src = _FakeSource("pexels", {
        ("서울", VIDEO): [_clip("pexels", "1"), _clip("pexels", "2")],
    })
    clip, _ = await select_clip([src], ["서울"], {("pexels", "1")}, 0)

    assert clip.id == "2"


@pytest.mark.asyncio
async def test_offset_rotates_pick_so_regenerate_yields_different_clip():
    hits = [_clip("pexels", "1"), _clip("pexels", "2"), _clip("pexels", "3")]
    src = _FakeSource("pexels", {("서울", VIDEO): hits})

    assert (await select_clip([src], ["서울"], set(), 0))[0].id == "1"
    assert (await select_clip([src], ["서울"], set(), 1))[0].id == "2"
    assert (await select_clip([src], ["서울"], set(), 4))[0].id == "2"   # 3개를 넘으면 순환


@pytest.mark.asyncio
async def test_all_queries_empty_raises_no_results():
    src = _FakeSource("pexels", {})
    with pytest.raises(AppError) as exc:
        await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert exc.value.code == "STOCK_NO_RESULTS"
    assert exc.value.status_code == 502


# --- enabled_sources ---------------------------------------------------------

def test_enabled_sources_returns_only_keyed_sources_in_config_order(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    assert [s.name for s in enabled_sources()] == ["pixabay"]


def test_enabled_sources_honours_config_order(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k1")
    monkeypatch.setenv("PIXABAY_API_KEY", "k2")
    monkeypatch.setenv("STOCK_SOURCES", '["pixabay","pexels"]')
    assert [s.name for s in enabled_sources()] == ["pixabay", "pexels"]


def test_enabled_sources_without_any_key_raises(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "")
    with pytest.raises(AppError) as exc:
        enabled_sources()

    assert exc.value.code == "STOCK_API_KEY_MISSING"


def test_enabled_sources_ignores_unknown_source_name(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    monkeypatch.setenv("STOCK_SOURCES", '["nope","pexels"]')
    assert [s.name for s in enabled_sources()] == ["pexels"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_render_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.render.sources'`

- [ ] **Step 3: `app/providers/render/sources.py` 작성**

```python
import logging

from app.config import get_settings
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO, VIDEO, Clip
from app.utils.stock.pexels import PexelsSource
from app.utils.stock.pixabay import PixabaySource

logger = logging.getLogger(__name__)

DEFAULT_QUERY = "abstract background"   # 최후 폴백 — 이게 0건일 일은 사실상 없다
_KINDS = (VIDEO, PHOTO)                 # 영상 우선, 없으면 이미지
_FACTORIES = {
    "pexels": (PexelsSource, "pexels_api_key"),
    "pixabay": (PixabaySource, "pixabay_api_key"),
}


def enabled_sources() -> list:
    """STOCK_SOURCES 순서대로, API 키가 실제로 있는 소스만 만든다.

    키가 하나만 있어도 그 소스로 동작한다. 하나도 없을 때만 실패한다.
    """
    settings = get_settings()
    sources = []
    for name in settings.stock_sources:
        entry = _FACTORIES.get(name)
        if entry is None:
            logger.warning("알 수 없는 STOCK_SOURCES 항목이라 건너뜁니다: %s", name)
            continue
        factory, key_field = entry
        if getattr(settings, key_field, ""):
            sources.append(factory())
    if not sources:
        raise AppError(400, "STOCK_API_KEY_MISSING",
                       "스톡 API 키가 없습니다. PEXELS_API_KEY 또는 PIXABAY_API_KEY를 설정해 주세요.")
    return sources


def queries_for(on_screen: str, topic: str) -> list[str]:
    """검색어 우선순위. 빈 문자열과 중복은 뺀다."""
    ordered = []
    for query in ((on_screen or "").strip(), (topic or "").strip(), DEFAULT_QUERY):
        if query and query not in ordered:
            ordered.append(query)
    return ordered


async def select_clip(sources, queries: list[str], used_keys: set, offset: int) -> tuple[Clip, str]:
    """폴백 체인으로 소재 1건을 고른다. (클립, 실제로 먹힌 검색어)를 돌려준다.

    루프 순서가 곧 우선순위다: 관련성(query) > 매체(kind) > 출처(source).
    on_screen으로 사진밖에 없다면, 그 사진이 topic으로 찾은 무관한 영상보다 낫다.

    offset은 ctx.attempt + 씬 번호다 — [재생성]하면 같은 검색 결과에서 다른 클립이 나온다.
    """
    for query in queries:
        for kind in _KINDS:
            for source in sources:
                try:
                    hits = await source.search(query, kind)
                except Exception:
                    # 4xx·5xx·네트워크 오류는 이 소스만 건너뛴다. 전부 실패해야 아래 STOCK_NO_RESULTS.
                    logger.warning("스톡 검색 실패 — 다음 소스로: source=%s query=%s kind=%s",
                                   source.name, query, kind, exc_info=True)
                    continue
                fresh = [clip for clip in hits if clip.key not in used_keys]
                if fresh:
                    return fresh[offset % len(fresh)], query
    raise AppError(502, "STOCK_NO_RESULTS",
                   "배경 소재를 찾지 못했습니다. 대본의 화면 문구를 바꿔 보세요.")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_render_sources.py -v`
Expected: PASS (14개)

- [ ] **Step 5: 커밋**

```bash
git add app/providers/render/sources.py tests/test_render_sources.py
git commit -m "기능: 스톡 소재 폴백 체인(관련성>매체>출처)과 활성 소스 결정 추가"
```

---

## Task 7: ffmpeg 커맨드 조립

**Files:**
- Modify: `app/utils/ffmpeg.py:11-46` (`build_slideshow_cmd`에서 스타일 문자열 추출) + 파일 끝에 `build_stock_cmd` 추가
- Test: `tests/test_ffmpeg.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces: `app.utils.ffmpeg.build_stock_cmd(*, exe: str, scenes: list[dict], audio_abs: str, srt_rel: str, out_rel: str, width: int, height: int, font: str, font_size: int) -> list[str]`. `scenes`의 각 항목은 `{"path": str, "kind": str, "seconds": float}`이며 `kind`는 `"video"` 또는 `"photo"`. 실행은 기존 `ffmpeg.run(cmd, cwd, on_progress, total_sec)`이 그대로 맡는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ffmpeg.py` 끝에 추가한다.

```python
from app.utils.ffmpeg import build_stock_cmd

_SCENES = [
    {"path": "projects/9/render/sources/scene1.mp4", "kind": "video", "seconds": 8.0},
    {"path": "projects/9/render/sources/scene2.jpg", "kind": "photo", "seconds": 12.0},
    {"path": "projects/9/render/sources/scene3.mp4", "kind": "video", "seconds": 10.0},
]


def _stock_cmd(scenes=None):
    return build_stock_cmd(
        exe="/bin/ffmpeg",
        scenes=scenes if scenes is not None else _SCENES,
        audio_abs="/abs/storage/projects/9/voice/voice.mp3",
        srt_rel="projects/9/captions/captions.srt",
        out_rel="projects/9/render/render.mp4",
        width=1080, height=1920,
        font="Malgun Gothic", font_size=30,
    )


def test_video_scene_loops_and_is_trimmed_by_input_options():
    # 클립이 씬보다 짧으면 반복, 길면 잘린다 — 필터에 trim이 필요 없어진다
    cmd = _stock_cmd()
    i = cmd.index("projects/9/render/sources/scene1.mp4")
    assert cmd[i - 5:i] == ["-stream_loop", "-1", "-t", "8.000", "-i"]


def test_photo_scene_uses_loop_1():
    cmd = _stock_cmd()
    i = cmd.index("projects/9/render/sources/scene2.jpg")
    assert cmd[i - 5:i] == ["-loop", "1", "-t", "12.000", "-i"]


def test_audio_is_last_input_and_mapped_by_index():
    # 씬 3개면 오디오는 3번 입력. 스톡 클립의 오디오는 map에서 빠져 나레이션만 남는다
    cmd = _stock_cmd()
    assert cmd[cmd.index("/abs/storage/projects/9/voice/voice.mp3") - 1] == "-i"
    assert cmd[cmd.index("-map") + 1] == "[v]"
    assert "3:a" in cmd
    assert "0:a" not in cmd


def _filter_of(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


def test_filter_normalizes_every_scene_then_concats():
    vf = _filter_of(_stock_cmd())
    for i in range(3):
        assert (f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,fps=30,setsar=1,setpts=PTS-STARTPTS[v{i}]") in vf
    assert "[v0][v1][v2]concat=n=3:v=1:a=0[bg]" in vf


def test_subtitles_use_relative_path_and_shared_style():
    # 드라이브 문자 ':'가 subtitles 필터 구분자와 충돌하는 Windows 문제 회피
    vf = _filter_of(_stock_cmd())
    assert "[bg]subtitles=projects/9/captions/captions.srt:force_style=" in vf
    assert "Fontname=Malgun Gothic" in vf
    assert "Fontsize=30" in vf
    assert "Alignment=10" in vf   # slideshow와 같은 정중앙 값


def test_output_is_browser_compatible_h264_and_relative():
    cmd = _stock_cmd()
    assert cmd[-1] == "projects/9/render/render.mp4"
    for flag in ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"):
        assert flag in cmd
    assert cmd[:4] == ["/bin/ffmpeg", "-y", "-progress", "pipe:1"]


def test_single_scene_still_concats():
    vf = _filter_of(_stock_cmd([_SCENES[0]]))
    assert "[v0]concat=n=1:v=1:a=0[bg]" in vf


def test_ten_scenes_stay_well_under_windows_command_limit():
    # 리스크: 필터 문자열이 씬 수에 비례해 길어진다. Windows 한계는 약 32768자.
    scenes = [{"path": f"projects/9/render/sources/scene{i}.mp4", "kind": "video", "seconds": 3.0}
              for i in range(1, 11)]
    assert len(" ".join(_stock_cmd(scenes))) < 8000
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_ffmpeg.py -k stock -v`
Expected: FAIL — `ImportError: cannot import name 'build_stock_cmd'`

- [ ] **Step 3: 자막 스타일을 공용 함수로 추출**

`app/utils/ffmpeg.py`의 `build_slideshow_cmd` 위에 `_style`을 추가하고, `build_slideshow_cmd` 안의 `style = (...)` 블록을 호출로 바꾼다. 동작은 그대로이므로 기존 slideshow 테스트가 계속 통과해야 한다.

```python
_FPS = 30


def _style(font: str, font_size: int) -> str:
    """자막 번인 스타일. slideshow와 stock이 공유한다.

    Alignment=10 = 화면 정중앙. 번들 libass는 레거시 SSA 넘버링을 쓴다
    (5는 좌상단, 10이 중앙) — 실제 렌더로 검증한 값이므로 5로 되돌리지 말 것.
    """
    return (
        f"Fontname={font},Fontsize={font_size},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=3,Shadow=0,Alignment=10"
    )
```

`build_slideshow_cmd` 안에서:

```python
    vf = f"subtitles={srt_rel}:force_style='{_style(font, font_size)}'"
```

(기존의 `# Alignment=10 = ...` 주석 두 줄과 `style = (...)` 블록은 `_style`로 옮겼으므로 삭제한다.)

- [ ] **Step 4: 기존 slideshow 테스트가 여전히 통과하는지 확인**

Run: `uv run pytest tests/test_ffmpeg.py tests/test_provider_render_slideshow.py -v`
Expected: 기존 테스트 전부 PASS, 신규 stock 테스트만 FAIL

- [ ] **Step 5: `build_stock_cmd` 작성**

`app/utils/ffmpeg.py`의 `build_slideshow_cmd` 아래에 추가한다.

```python
def build_stock_cmd(
    *,
    exe: str,
    scenes: list[dict],
    audio_abs: str,
    srt_rel: str,
    out_rel: str,
    width: int,
    height: int,
    font: str,
    font_size: int,
) -> list[str]:
    """씬별 스톡 소재를 이어붙이고 자막을 번인해 9:16 mp4를 만드는 ffmpeg 인자.

    scenes 항목: {"path": 저장소 상대경로, "kind": "video"|"photo", "seconds": float}

    길이 정합은 전적으로 입력 옵션이 맡는다 — 영상은 -stream_loop로 무한 반복시킨 뒤
    -t로 자르고, 이미지는 -loop 1 -t로 정지 영상을 늘린다. 덕분에 필터에 trim이
    없어도 각 스트림이 정확히 씬 길이가 된다.

    자막·출력은 build_slideshow_cmd와 같은 이유로 cwd(저장소 루트) 기준 상대경로다.
    오디오는 필터가 아니라 -i 입력이라 절대경로여도 안전하다.
    """
    cmd = [exe, "-y", "-progress", "pipe:1"]
    for scene in scenes:
        seconds = f"{scene['seconds']:.3f}"
        if scene["kind"] == "photo":
            cmd += ["-loop", "1", "-t", seconds, "-i", scene["path"]]
        else:
            cmd += ["-stream_loop", "-1", "-t", seconds, "-i", scene["path"]]
    cmd += ["-i", audio_abs]

    # 소재마다 해상도·비율·fps·SAR이 제각각이라 concat 전에 전부 같은 규격으로 맞춘다.
    # 하나라도 어긋나면 concat 필터가 실패한다.
    chains = [
        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={_FPS},setsar=1,setpts=PTS-STARTPTS[v{i}]"
        for i in range(len(scenes))
    ]
    labels = "".join(f"[v{i}]" for i in range(len(scenes)))
    chains.append(f"{labels}concat=n={len(scenes)}:v=1:a=0[bg]")
    chains.append(f"[bg]subtitles={srt_rel}:force_style='{_style(font, font_size)}'[v]")

    cmd += [
        "-filter_complex", ";".join(chains),
        # 스톡 클립의 오디오는 버리고 나레이션만 싣는다. 오디오는 씬 다음 입력이다.
        "-map", "[v]", "-map", f"{len(scenes)}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        out_rel,
    ]
    return cmd
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_ffmpeg.py tests/test_provider_render_slideshow.py -v`
Expected: PASS 전부

- [ ] **Step 7: 커밋**

```bash
git add app/utils/ffmpeg.py tests/test_ffmpeg.py
git commit -m "기능: 씬별 소재를 concat하는 build_stock_cmd 추가, 자막 스타일 공용 추출"
```

---

## Task 8: `StockRender` provider

**Files:**
- Create: `app/providers/render/stock.py`
- Modify: `app/providers/base.py:48-61` (import 1줄 + REGISTRY 1줄)
- Test: `tests/test_provider_render_stock.py`

**Interfaces:**
- Consumes: `scene_spans` (Task 4), `enabled_sources`·`queries_for`·`select_clip` (Task 6), `download` (Task 5), `storage.clear_dir` (Task 5), `build_stock_cmd`·`run` (Task 7), `input_audio_path`·`input_srt_path` (기존 `render/input.py`)
- Produces: `app.providers.render.stock.StockRender` — `stage = "render"`, `name = "stock"`, `__init__(self, runner=None, exe=None, sources=None, downloader=None)`. `REGISTRY["render"]["stock"]`에 등록된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_provider_render_stock.py`를 만든다.

```python
import pytest

from app.config import get_settings
from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.render.stock import StockRender
from app.utils import storage
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO, VIDEO, Clip, StockTooLarge

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/9/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/9/captions/captions.srt", "meta": {}}],
}
_INPUTS = {
    "captions": {"duration_sec": 30.0},
    "script": {"scenes": [
        {"index": 1, "narration": "가" * 40, "on_screen": "서울 야경"},
        {"index": 2, "narration": "나" * 60, "on_screen": "카페"},
        {"index": 3, "narration": "다" * 50, "on_screen": "출근길"},
    ]},
}


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _clip(clip_id, kind=VIDEO):
    return Clip(source="pexels", kind=kind, id=clip_id, url=f"https://cdn/{clip_id}",
                page_url=f"https://page/{clip_id}", author="홍길동", width=1080, height=1920)


class _FakeSource:
    """어떤 검색어든 요청한 종류의 클립을 넉넉히 돌려준다. 씬 3개보다 많아야
    중복 배제·재시도 테스트가 후보를 소진하지 않는다."""

    name = "pexels"

    def __init__(self, hits=None):
        self._hits = hits if hits is not None else [_clip(f"c{i}") for i in range(1, 6)]

    async def search(self, query, kind):
        # 종류가 다르면 0건 — 실제 소스와 같은 계약이라야 폴백 순서가 그대로 재현된다
        return [clip for clip in self._hits if clip.kind == kind]


class _Recorder:
    """runner·downloader 호출을 기록하는 테스트 더블."""

    def __init__(self, download_fails=0):
        self.cmds = []
        self.downloads = []
        self.progress = []
        self._download_fails = download_fails

    async def runner(self, cmd, cwd, on_progress=None, total_sec=None):
        self.cmds.append({"cmd": cmd, "cwd": cwd, "on_progress": on_progress, "total_sec": total_sec})
        if on_progress is not None:
            on_progress(0.0, "영상 합성 중…")
            on_progress(100.0, "영상 합성 중…")
        storage.write_bytes(cmd[-1], b"MP4-bytes")

    async def downloader(self, url, rel, max_bytes, timeout_sec, transport=None):
        self.downloads.append({"url": url, "rel": rel})
        if len(self.downloads) <= self._download_fails:
            raise StockTooLarge("too big")
        storage.write_bytes(rel, b"CLIP")
        return 4


def _ctx(on_progress=None, attempt=0):
    kwargs = {"topic": "도시 여행", "inputs": _INPUTS, "input_assets": _ASSETS,
              "attempt": attempt, "workdir": "projects/9/render"}
    if on_progress is not None:
        kwargs["on_progress"] = on_progress
    return StageContext(**kwargs)


def _provider(rec, sources=None):
    return StockRender(runner=rec.runner, exe="/bin/ffmpeg",
                       sources=sources or [_FakeSource()], downloader=rec.downloader)


# --- 성공 경로 ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_downloads_one_clip_per_scene_and_records_video_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder()
    result = await _provider(rec).run(_ctx())

    assert len(rec.downloads) == 3
    assert [d["rel"] for d in rec.downloads] == [
        "projects/9/render/sources/scene1.mp4",
        "projects/9/render/sources/scene2.mp4",
        "projects/9/render/sources/scene3.mp4",
    ]
    assert result.assets[0]["kind"] == AssetKind.VIDEO
    assert result.assets[0]["path"] == "projects/9/render/render.mp4"
    assert len(result.assets) == 1   # 소재는 asset으로 기록하지 않는다
    assert result.output["provider"] == "stock"
    assert result.output["duration_sec"] == 30.0
    assert result.output["size_bytes"] == len(b"MP4-bytes")


@pytest.mark.asyncio
async def test_run_records_sources_for_attribution(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await _provider(_Recorder()).run(_ctx())

    sources = result.output["sources"]
    assert len(sources) == 3
    assert sources[0] == {
        "scene": 1, "source": "pexels", "kind": VIDEO,
        "query": "서울 야경", "url": "https://page/c1", "author": "홍길동",
    }


@pytest.mark.asyncio
async def test_run_passes_scene_seconds_to_ffmpeg(monkeypatch, tmp_path):
    # 글자수 40/60/50 → 30초를 8/12/10으로. concat 길이가 오디오와 맞아야 한다.
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder()
    await _provider(rec).run(_ctx())

    cmd = rec.cmds[0]["cmd"]
    assert "8.000" in cmd and "12.000" in cmd and "10.000" in cmd
    assert rec.cmds[0]["cwd"] == str(tmp_path)   # 상대경로 자막 필터를 위해 루트에서 실행
    assert rec.cmds[0]["total_sec"] == 30.0


@pytest.mark.asyncio
async def test_photo_clip_is_saved_with_jpg_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder()
    # 영상이 하나도 없어 매체 폴백이 사진으로 내려가는 상황
    photo_source = _FakeSource(hits=[_clip(f"p{i}", PHOTO) for i in range(1, 6)])
    await StockRender(runner=rec.runner, exe="/bin/ffmpeg",
                      sources=[photo_source], downloader=rec.downloader).run(_ctx())

    assert all(d["rel"].endswith(".jpg") for d in rec.downloads)
    # 이미지 씬은 ffmpeg에서 -loop 1로 늘어난다
    assert "-loop" in rec.cmds[0]["cmd"]


@pytest.mark.asyncio
async def test_scenes_do_not_reuse_the_same_clip(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await _provider(_Recorder()).run(_ctx())

    urls = [s["url"] for s in result.output["sources"]]
    assert len(set(urls)) == 3   # 같은 화면이 반복되면 안 된다


@pytest.mark.asyncio
async def test_previous_sources_are_cleared_before_run(monkeypatch, tmp_path):
    # 재생성 시 이전 소재가 쌓이면 디스크가 샌다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("projects/9/render/sources/stale.mp4", b"old")
    await _provider(_Recorder()).run(_ctx())

    assert not (tmp_path / "projects/9/render/sources/stale.mp4").exists()


# --- 진행률 -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_progress_is_split_between_download_and_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    seen = []
    await _provider(_Recorder()).run(_ctx(on_progress=lambda p, m: seen.append((p, m))))

    percents = [p for p, _ in seen if p is not None]
    assert percents[0] == 0.0            # 첫 소재 준비
    assert max(percents) == 100.0        # ffmpeg 완료가 100%
    assert any(0 < p <= 40 for p in percents)    # 다운로드 구간
    assert any(40 <= p < 100 for p in percents)  # ffmpeg 구간
    assert "배경 소재 준비 중… (1/3)" in [m for _, m in seen]


# --- 실패 경로 ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_download_falls_back_to_next_candidate(monkeypatch, tmp_path):
    # 첫 후보가 상한 초과여도 다음 후보로 이어간다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder(download_fails=1)
    result = await _provider(rec).run(_ctx())

    assert len(rec.downloads) == 4   # 실패 1 + 성공 3
    assert len(result.output["sources"]) == 3


@pytest.mark.asyncio
async def test_all_download_candidates_failing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    rec = _Recorder(download_fails=99)
    with pytest.raises(AppError) as exc:
        await _provider(rec).run(_ctx())

    assert exc.value.code == "STOCK_DOWNLOAD_FAILED"


@pytest.mark.asyncio
async def test_missing_captions_duration_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"captions": {}, "script": _INPUTS["script"]},
                       input_assets=_ASSETS, workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await _provider(_Recorder()).run(ctx)

    assert exc.value.code == "CAPTIONS_DURATION_MISSING"


@pytest.mark.asyncio
async def test_missing_script_scenes_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"captions": {"duration_sec": 10.0}},
                       input_assets=_ASSETS, workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await _provider(_Recorder()).run(ctx)

    assert exc.value.code == "SCRIPT_SCENES_MISSING"


@pytest.mark.asyncio
async def test_missing_voice_asset_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs=_INPUTS,
                       input_assets={StageName.CAPTIONS: _ASSETS[StageName.CAPTIONS]},
                       workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await _provider(_Recorder()).run(ctx)

    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_validate_without_any_api_key_raises(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "")
    with pytest.raises(AppError) as exc:
        StockRender().validate({})

    assert exc.value.code == "STOCK_API_KEY_MISSING"


def test_registry_has_render_stock():
    assert REGISTRY["render"]["stock"] is StockRender
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_provider_render_stock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.render.stock'`

- [ ] **Step 3: `app/providers/render/stock.py` 작성**

```python
import logging

from app.config import get_settings
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.render.input import input_audio_path, input_srt_path
from app.providers.render.sources import enabled_sources, queries_for, select_clip
from app.providers.render.timing import scene_spans
from app.utils import ffmpeg, storage
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO
from app.utils.stock.download import download

logger = logging.getLogger(__name__)

_FILENAME = "render.mp4"
_SOURCES_DIR = "sources"
_WIDTH, _HEIGHT = 1080, 1920
_DOWNLOAD_SHARE = 40.0   # 진행률 0~40%는 소재 준비, 40~100%는 ffmpeg
_MAX_CLIP_TRIES = 3      # 한 씬에서 다운로드를 몇 번까지 다른 후보로 재시도할지


def _extension(kind: str) -> str:
    """저장 파일 확장자. ffmpeg가 실제 컨테이너를 스스로 판별하므로 대략만 맞으면 된다."""
    return ".jpg" if kind == PHOTO else ".mp4"


class StockRender(Provider):
    """Pexels·Pixabay 스톡 소재를 씬별 배경으로 깔아 9:16 mp4를 만드는 provider."""

    stage = "render"
    name = "stock"

    def __init__(self, runner=None, exe=None, sources=None, downloader=None):
        # 테스트는 fake runner/sources/downloader를 주입해 네트워크·ffmpeg 없이 검증한다.
        self._runner = runner or ffmpeg.run
        self._exe = exe
        self._sources = sources
        self._download = downloader or download

    def validate(self, settings: dict) -> None:
        enabled_sources()   # 키가 하나도 없으면 여기서 STOCK_API_KEY_MISSING → 실행 전 조기 실패

    def _exe_path(self) -> str:
        if self._exe is None:
            self._exe = ffmpeg.ffmpeg_exe()
        return self._exe

    async def _prepare_scene(self, ctx, sources, scene, index, seconds, used_keys, sources_dir):
        """씬 하나의 소재를 고르고 내려받는다. 실패한 후보는 건너뛰고 다음을 시도한다."""
        settings = get_settings()
        queries = queries_for(scene.get("on_screen", ""), ctx.topic)
        for _ in range(_MAX_CLIP_TRIES):
            clip, query = await select_clip(sources, queries, used_keys, ctx.attempt + index)
            used_keys.add(clip.key)   # 성공이든 실패든 이 후보는 다시 뽑지 않는다
            rel = f"{sources_dir}/scene{index + 1}{_extension(clip.kind)}"
            try:
                await self._download(
                    clip.url, rel, settings.stock_max_bytes, settings.stock_timeout_sec
                )
            except Exception:
                logger.warning("소재 내려받기 실패 — 다음 후보로: %s", clip.url, exc_info=True)
                continue
            return {"path": rel, "kind": clip.kind, "seconds": seconds,
                    "source": clip.source, "query": query,
                    "url": clip.page_url, "author": clip.author}
        raise AppError(502, "STOCK_DOWNLOAD_FAILED",
                       "배경 소재를 내려받지 못했습니다. 잠시 후 다시 시도해 주세요.")

    async def run(self, ctx: StageContext) -> StageResult:
        settings = get_settings()
        audio_abs = str(storage.resolve(input_audio_path(ctx)))
        srt_rel = input_srt_path(ctx)
        duration = ctx.inputs.get("captions", {}).get("duration_sec")
        scenes = (ctx.inputs.get("script") or {}).get("scenes") or []
        spans = scene_spans(scenes, duration)   # 씬·duration 검증도 여기서 함께 한다

        sources = self._sources or enabled_sources()
        sources_dir = f"{ctx.workdir}/{_SOURCES_DIR}"
        storage.clear_dir(sources_dir)   # 재생성 시 이전 소재를 남기지 않는다

        picked: list[dict] = []
        used_keys: set = set()
        for index, (scene, (start, end)) in enumerate(zip(scenes, spans)):
            ctx.on_progress(
                _DOWNLOAD_SHARE * index / len(scenes),
                f"배경 소재 준비 중… ({index + 1}/{len(scenes)})",
            )
            picked.append(await self._prepare_scene(
                ctx, sources, scene, index, end - start, used_keys, sources_dir
            ))

        out_rel = f"{ctx.workdir}/{_FILENAME}"
        cmd = ffmpeg.build_stock_cmd(
            exe=self._exe_path(),
            scenes=[{"path": p["path"], "kind": p["kind"], "seconds": p["seconds"]} for p in picked],
            audio_abs=audio_abs,
            srt_rel=srt_rel,
            out_rel=out_rel,
            width=_WIDTH,
            height=_HEIGHT,
            font=settings.render_font,
            font_size=settings.render_font_size,
        )
        out_abs = storage.resolve(out_rel)
        out_abs.parent.mkdir(parents=True, exist_ok=True)

        def _ffmpeg_progress(percent, message):
            # ffmpeg의 0~100%를 전체 진행률 40~100% 구간으로 옮긴다.
            # percent가 0일 수도 있으므로 `if percent`가 아니라 None 비교여야 한다.
            scaled = None if percent is None else _DOWNLOAD_SHARE + (
                (100.0 - _DOWNLOAD_SHARE) * percent / 100.0
            )
            ctx.on_progress(scaled, message)

        # cwd를 저장소 루트로 둬야 상대경로 자막 필터가 동작한다(Windows ':' 회피).
        await self._runner(
            cmd, str(storage.resolve(".")), on_progress=_ffmpeg_progress, total_sec=duration
        )

        size = out_abs.stat().st_size
        return StageResult(
            output={
                "provider": "stock",
                "width": _WIDTH,
                "height": _HEIGHT,
                "duration_sec": duration,
                "size_bytes": size,
                "sources": [
                    {"scene": i + 1, "source": p["source"], "kind": p["kind"],
                     "query": p["query"], "url": p["url"], "author": p["author"]}
                    for i, p in enumerate(picked)
                ],
            },
            assets=[{"kind": AssetKind.VIDEO, "path": out_rel,
                     "meta": {"size_bytes": size, "width": _WIDTH, "height": _HEIGHT}}],
        )
```

- [ ] **Step 4: REGISTRY에 등록**

`app/providers/base.py`의 import 블록(`from app.providers.render.slideshow import ...` 다음 줄)에 추가한다.

```python
from app.providers.render.stock import StockRender  # noqa: E402
```

그리고 REGISTRY의 render 줄을 바꾼다.

```python
    "render": {"fake": FakeRender, "slideshow": SlideshowRender, "stock": StockRender},
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_provider_render_stock.py -v`
Expected: PASS (15개)

- [ ] **Step 6: 전체 백엔드 테스트**

Run: `uv run pytest -q`
Expected: 전부 PASS. 특히 `tests/test_provider_registry.py`와 `tests/test_provider_base.py`가 REGISTRY 변경에도 통과해야 한다.

- [ ] **Step 7: 커밋**

```bash
git add app/providers/render/stock.py app/providers/base.py tests/test_provider_render_stock.py
git commit -m "기능: 스톡 소재를 씬별 배경으로 깔아 합성하는 stock 렌더러 추가"
```

---

## Task 9: 프론트엔드 — 소재 출처 표시

**Files:**
- Modify: `web/src/lib/projects.ts:18-24`
- Modify: `web/src/pages/projects/ProjectDetail.tsx:119-137` (`RenderView`)

**Interfaces:**
- Consumes: `StageResult.output.sources` (Task 8)
- Produces: `RenderSource` 타입. `RenderOutput.sources`는 **선택 필드**라 slideshow·fake 출력과 그대로 호환된다.

Pexels 가이드라인이 "API를 쓸 때는 Pexels로 가는 눈에 띄는 링크를 보여줄 것"을 요구한다. 이 태스크가 그 요건을 충족한다.

- [ ] **Step 1: 타입 추가**

`web/src/lib/projects.ts`의 `RenderOutput` 정의를 바꾼다.

```ts
export type RenderSource = {
  scene: number
  source: string
  kind: string
  query: string
  url: string
  author: string
}
export type RenderOutput = {
  provider: string
  width: number
  height: number
  duration_sec: number | null
  size_bytes: number
  // stock 렌더러만 채운다. slideshow·fake 출력과 호환되도록 선택 필드.
  sources?: RenderSource[]
}
```

- [ ] **Step 2: `RenderView`에 출처 목록 추가**

`web/src/pages/projects/ProjectDetail.tsx`에서 `RenderView`의 마지막 `<div className="text-xs text-slate-400">` 블록 **다음**, 컴포넌트를 닫는 `</div>` **앞**에 넣는다.

```tsx
      {stage.output.sources && stage.output.sources.length > 0 && (
        <div className="space-y-1 border-t border-slate-100 pt-2">
          <div className="text-xs font-medium text-slate-500">소재 출처</div>
          <ul className="space-y-0.5">
            {stage.output.sources.map((source) => (
              <li key={source.scene} className="text-xs text-slate-400">
                #{source.scene}{' '}
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-slate-600"
                >
                  {source.source === 'pexels' ? 'Pexels' : 'Pixabay'}
                </a>
                {source.author && ` · ${source.author}`}
              </li>
            ))}
          </ul>
        </div>
      )}
```

- [ ] **Step 3: 타입 검사 · 빌드**

Run: `cd web && npm run build`
Expected: 오류 없음. `stage.output.sources` 접근이 `hasRender` 가드 뒤라 타입이 좁혀져 있어야 한다.

- [ ] **Step 4: 린트**

Run: `cd web && npm run lint`
Expected: 오류 없음

- [ ] **Step 5: 커밋**

```bash
git add web/src/lib/projects.ts web/src/pages/projects/ProjectDetail.tsx
git commit -m "기능: 영상 화면에 스톡 소재 출처 목록 표시"
```

---

## Task 10: 통합 스모크 (실제 API · 실제 ffmpeg)

**Files:**
- Create: `tests/test_stock_smoke.py`

**Interfaces:**
- Consumes: Task 2·3·7의 전부
- Produces: 없음 (검증 전용)

이 태스크가 **스펙의 리스크 1·2를 실제로 닫는다.** 여기서 실패하면 Task 2·3의 URL·파라미터·응답 매핑을 고치고 그 픽스처도 실제 응답으로 갱신한다.

- [ ] **Step 1: 스모크 테스트 작성**

`tests/test_stock_smoke.py`를 만든다.

```python
"""실제 네트워크·ffmpeg를 쓰는 느린 검증. 키가 없으면 통째로 skip한다."""

import subprocess

import pytest

from app.config import get_settings
from app.utils import ffmpeg, storage
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pexels import PexelsSource
from app.utils.stock.pixabay import PixabaySource

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [VIDEO, PHOTO])
async def test_pexels_real_search_returns_usable_clips(kind):
    if not get_settings().pexels_api_key:
        pytest.skip("PEXELS_API_KEY 없음")

    clips = await PexelsSource().search("도시", kind)

    assert clips, "Pexels가 0건을 돌려줬다 — 엔드포인트/파라미터를 확인할 것"
    assert all(c.url.startswith("http") for c in clips)
    assert all(c.kind == kind for c in clips)
    assert all(c.id for c in clips)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [VIDEO, PHOTO])
async def test_pixabay_real_search_returns_usable_clips(kind):
    if not get_settings().pixabay_api_key:
        pytest.skip("PIXABAY_API_KEY 없음")

    clips = await PixabaySource().search("도시", kind)

    assert clips, "Pixabay가 0건을 돌려줬다 — 응답 필드 모양을 확인할 것"
    assert all(c.url.startswith("http") for c in clips)
    assert all(c.kind == kind for c in clips)


@pytest.mark.asyncio
async def test_real_ffmpeg_concats_scenes_with_subtitles(monkeypatch, tmp_path):
    """로컬에서 만든 소재 2개 + 무음 오디오 + srt로 실제 mp4를 합성한다.

    네트워크를 타지 않으므로 키 없이도 돈다. concat 필터 정합(fps·SAR·pix_fmt)과
    Windows 상대경로 자막이 실제로 통과하는지가 검증 대상이다.
    """
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    exe = ffmpeg.ffmpeg_exe()
    workdir = "projects/1/render"
    sources_dir = f"{workdir}/sources"
    storage.resolve(sources_dir).mkdir(parents=True, exist_ok=True)

    # 씬 소재: 파란 영상 1개 + 빨간 정지 이미지 1개 (일부러 가로 규격으로 만들어 crop을 검증)
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1280x720:d=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(storage.resolve(f"{sources_dir}/scene1.mp4"))], check=True,
                   capture_output=True)
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "color=c=red:s=1280x720:d=1",
                    "-frames:v", "1",
                    str(storage.resolve(f"{sources_dir}/scene2.jpg"))], check=True,
                   capture_output=True)
    # 나레이션 대신 무음 4초
    audio_rel = f"{workdir}/voice.mp3"
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "4",
                    str(storage.resolve(audio_rel))], check=True, capture_output=True)
    srt_rel = f"{workdir}/captions.srt"
    storage.write_bytes(srt_rel,
                        "1\n00:00:00,000 --> 00:00:02,000\n안녕하세요\n\n"
                        "2\n00:00:02,000 --> 00:00:04,000\n반갑습니다\n".encode("utf-8"))

    out_rel = f"{workdir}/render.mp4"
    cmd = ffmpeg.build_stock_cmd(
        exe=exe,
        scenes=[{"path": f"{sources_dir}/scene1.mp4", "kind": "video", "seconds": 2.0},
                {"path": f"{sources_dir}/scene2.jpg", "kind": "photo", "seconds": 2.0}],
        audio_abs=str(storage.resolve(audio_rel)),
        srt_rel=srt_rel,
        out_rel=out_rel,
        width=1080, height=1920,
        font=get_settings().render_font, font_size=get_settings().render_font_size,
    )
    await ffmpeg.run(cmd, str(tmp_path))

    out = storage.resolve(out_rel)
    assert out.exists() and out.stat().st_size > 0
    print(f"[스모크] 합성 결과: {out} ({out.stat().st_size} bytes)")
```

- [ ] **Step 2: ffmpeg 합성 스모크 실행 (키 불필요)**

Run: `uv run pytest tests/test_stock_smoke.py -k real_ffmpeg -v -s`
Expected: PASS. 실패하면 `concat` 입력 정합(`fps`·`setsar`·`pix_fmt`) 또는 자막 상대경로가 원인이다 — `build_stock_cmd`를 고치고 Task 7 테스트를 갱신한다.

- [ ] **Step 3: 합성 결과 육안 확인**

Step 2가 출력한 경로의 mp4를 연다. 확인 항목:
- 9:16 세로이고 가로 소재가 **중앙 크롭**되었는가
- 앞 2초 파랑 → 뒤 2초 빨강으로 **배경이 바뀌는가**
- 한글 자막이 □ 박스가 아니라 정상 렌더되고 화면 **정중앙**에 오는가

- [ ] **Step 4: 실제 API 스모크 실행**

`.env`에 `PEXELS_API_KEY`·`PIXABAY_API_KEY`를 채운 뒤 실행한다.

Run: `uv run pytest tests/test_stock_smoke.py -v -s`
Expected: PASS. 다음 실패는 각각 이렇게 대응한다.

| 증상 | 대응 |
|---|---|
| Pexels 영상 404 | `pexels.py`의 `_VIDEO_URL`을 `https://api.pexels.com/videos/search`로 바꾸고 Task 2 테스트 갱신 |
| Pixabay `KeyError`/0건 | 실제 응답을 출력해 `_video_clips`/`_photo_clips` 매핑과 `tests/test_stock_pixabay.py` 픽스처를 **함께** 실제 모양으로 교체 |

이어서 한국어 검색 적중률을 조사한다. **테스트가 아니라 일회성 조사 스크립트다** — 적중률은 통과/실패로 판정할 성질이 아니라, 폴백 체인이 얼마나 자주 발동하는지 보고 영어 `visual_query` 도입 여부를 판단하기 위한 자료다(스펙 리스크 3).

`scripts/probe_stock_hitrate.py`를 만든다.

```python
"""한국어 on_screen이 스톡에서 실제로 얼마나 잡히는지 재는 일회성 조사 스크립트.

테스트가 아니다 — 결과는 판정이 아니라 자료이며, 스펙 리스크 3에 기록한다.
실행: uv run python scripts/probe_stock_hitrate.py
"""

import asyncio

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pexels import PexelsSource
from app.utils.stock.pixabay import PixabaySource

# 실제 대본에 나올 법한 on_screen들 — 구체명사부터 추상 문구까지 섞는다
QUERIES = [
    "서울 야경",       # 구체 장소
    "아침 루틴",       # 일상 개념
    "복리 계산",       # 추상 개념
    "출근길",          # 일상 장면
    "하루 5분이면 충분",  # 자막용 문구 (검색어로는 최악)
    "abstract background",  # 최후 폴백
]


async def main() -> None:
    settings = get_settings()
    sources = []
    if settings.pexels_api_key:
        sources.append(PexelsSource())
    if settings.pixabay_api_key:
        sources.append(PixabaySource())
    if not sources:
        print("PEXELS_API_KEY / PIXABAY_API_KEY 가 없습니다.")
        return

    for query in QUERIES:
        row = []
        for source in sources:
            for kind in (VIDEO, PHOTO):
                try:
                    count = len(await source.search(query, kind))
                except Exception as exc:
                    row.append(f"{source.name}/{kind}=ERR({type(exc).__name__})")
                    continue
                row.append(f"{source.name}/{kind}={count}")
        print(f"{query!r:28} " + "  ".join(row))


if __name__ == "__main__":
    asyncio.run(main())
```

Run: `uv run python scripts/probe_stock_hitrate.py`

읽는 법: `on_screen`으로 쓸 법한 앞쪽 검색어들이 대부분 0건이면 폴백 체인이 매번 `topic`이나 `abstract background`까지 내려간다는 뜻이다 — 배경이 대본과 무관해지므로 영어 `visual_query` 필드 도입을 다음 슬라이스로 올린다. 결과를 스펙 리스크 3에 그대로 붙인다.

- [ ] **Step 5: 실제 파이프라인 1회 확인**

`.env`에 `RENDER_PROVIDER=stock`을 두고 앱을 띄워 프로젝트를 하나 끝까지 돌린다.

Run: `cd web && npm run dev`

확인 항목:
- render 단계 진행률이 "배경 소재 준비 중… (1/N)"에서 시작해 "영상 합성 중…"으로 넘어가는가
- 완성 mp4의 배경이 씬마다 바뀌는가
- 화면 아래 "소재 출처" 목록에 Pexels/Pixabay 링크와 작가명이 뜨는가
- [재생성]을 누르면 **다른 소재**가 나오는가
- `storage/projects/{id}/render/sources/`에 이전 실행의 파일이 쌓이지 않는가

- [ ] **Step 6: 전체 테스트 후 커밋**

Run: `uv run pytest -q`
Run: `cd web && npm run build && npm run lint`
Expected: 전부 PASS

```bash
git add tests/test_stock_smoke.py
git commit -m "테스트: 스톡 검색·ffmpeg 합성 통합 스모크 추가"
```

- [ ] **Step 7: 스펙의 미확정 항목 정리**

Task 10에서 확정된 사실로 [스펙 3.2의 "구현 시 확정할 것" 블록](../specs/2026-07-22-stock-render-design.md)과 10장 리스크 1·2를 갱신한다. 실제로 쓴 엔드포인트·파라미터·응답 필드를 확정 사실로 적고, 한국어 검색 적중률(Step 4 출력)을 리스크 3에 기록한다.

```bash
git add docs/superpowers/specs/2026-07-22-stock-render-design.md
git commit -m "문서: 스톡 API 실측값으로 스펙의 미확정 항목 확정"
```

---

## 완료 기준

- `uv run pytest -q` 전부 통과 (신규 약 60개 포함)
- `cd web && npm run build && npm run lint` 오류 없음
- `RENDER_PROVIDER=slideshow`(기본값)로 기존 파이프라인이 그대로 동작
- `RENDER_PROVIDER=stock` + 키 1개 이상으로 씬별 배경이 바뀌는 mp4 생성
- 키가 하나도 없으면 render 단계가 `STOCK_API_KEY_MISSING` 메시지와 함께 FAILED
