# stock 렌더러 — 설계 문서 (Design Spec)

- **작성일:** 2026-07-22
- **대상:** `render` 단계에 스톡 영상/이미지 배경 provider `stock` 추가
- **상위 문서:** [2026-07-09-studio-design.md](2026-07-09-studio-design.md) (전체 설계) · [2026-07-21-render-stage-design.md](2026-07-21-render-stage-design.md) (render 단계)

---

## 1. 목표 & 범위

### 목표
대본의 `on_screen`으로 **Pexels·Pixabay 무료 API**에서 씬별 배경 소재를 찾아, 기존 자막·나레이션과 합성해 9:16 mp4를 만드는 `render` provider `stock`을 추가한다. 상위 설계가 예고한 render 3종(`slideshow`/`stock`/`ai_image`) 중 두 번째다.

지금까지 `on_screen`은 script 스키마에 저장·표시만 되고 실제로 쓰이는 곳이 없었다. 이 슬라이스가 그 필드에 처음 용도를 준다.

### 확정된 결정 (브레인스토밍)
| 항목 | 결정 | 이유 |
|------|------|------|
| 배치 지점 | **`render` provider 1개 추가** | REGISTRY 한 줄. core·DB·`STAGE_ORDER`·워커·SSE 무변경 |
| 씬 분할 | **씬별 소재 교체**, 경계는 **narration 글자수 비례** | TTS 속도가 균일해 오차가 작고, 구현이 상수 수준으로 단순 |
| 검색어 | **한국어 `on_screen` 그대로** + 폴백 체인 | Pexels `locale=ko-KR` · Pixabay `lang=ko` 공식 지원. script 스키마 무변경 |
| 미디어 | **영상 우선 → 없으면 이미지** | 정규화 필터 경로가 같아 추가 비용이 입력 옵션 한 줄 |
| 공급사 | **Pexels 우선 → Pixabay 폴백**, 단일 `stock` provider 내부 | 적중률↑. 공통 인터페이스라 소스 추가가 파일 하나 |
| 합성 | **단일 `filter_complex` 1회 실행** | 중간 파일·정리 로직 없음. 기존 진행률 파서 그대로 재사용 |

### 비범위 (YAGNI)
- 사용자가 씬별 소재를 직접 고르는 UI — `visuals` 단계 신설이 필요한 별도 슬라이스
- 소재 캐시·재사용, 트랜지션·페이드, 이미지 켄번즈(줌) 효과
- 영어 검색어 자동 번역, script 스키마의 `visual_query` 필드
- `ai_image` 렌더러

---

## 2. 파일 배치

기존 관례를 따른다 — `utils/`는 studio 도메인을 모르는 순수 기술 헬퍼, `providers/`는 도메인 결정.

```
app/utils/stock/
  __init__.py
  base.py      # Clip 데이터클래스 + StockSource 프로토콜        ← 도메인 모름
  pexels.py    # search(query, kind, ...) -> list[Clip]
  pixabay.py   # 동일 인터페이스
app/providers/render/
  stock.py     # StockRender — 폴백 체인·씬 배분·합성 지휘        ← 도메인 결정
  timing.py    # 씬 -> (start, end) 글자수 비례 분배
app/utils/ffmpeg.py    # build_stock_cmd() 추가 (기존 run()은 그대로 재사용)
app/utils/storage.py   # clear_dir() 추가
```

| 위치 | 변경 |
|------|------|
| `app/providers/base.py` | import 1줄 + `REGISTRY["render"]["stock"] = StockRender` |
| `app/config.py` | 스톡 관련 설정 5개 (5장) |
| `.env.example` | 위 5개 + 지금 누락된 `RENDER_*` 키들 |
| `pyproject.toml` | `httpx`를 dev 그룹에서 **런타임 의존성으로 승격** |

`app/core/`, `app/models/`, `app/queries/`, 마이그레이션은 **손대지 않는다.**

---

## 3. 소재 검색

### 3.1 Clip (공통 표현)

```python
@dataclass(frozen=True)
class Clip:
    source: str        # "pexels" | "pixabay"
    kind: str          # "video" | "photo"
    id: str            # 소스 내 고유 id — 씬 간 중복 배제 키
    url: str           # 다운로드할 실제 파일 URL
    page_url: str      # 출처 표기용 소스 페이지 링크
    author: str        # 작가명 (없으면 "")
    width: int
    height: int
    duration_sec: float | None   # 이미지는 None
```

각 소스 모듈은 `search(query, kind) -> list[Clip]` 하나만 노출한다. 호출자는 어느 소스인지 몰라도 된다.

### 3.2 소스별 요청

| | Pexels | Pixabay |
|---|---|---|
| 영상 | `GET https://api.pexels.com/v1/videos/search` | `GET https://pixabay.com/api/videos/` |
| 이미지 | `GET https://api.pexels.com/v1/search` | `GET https://pixabay.com/api/` |
| 인증 | `Authorization: <KEY>` 헤더 (Bearer 아님) | 쿼리스트링 `key=<KEY>` |
| 한국어 | `locale=ko-KR` | `lang=ko` |
| 세로 필터 | `orientation=portrait` | 이미지만 `orientation=vertical` (영상은 없음) |
| 레이트리밋 | 200 req/hour · 20,000/month | 100 req/60s |

> **구현 시 확정할 것:** Pexels 영상 엔드포인트는 문서상 `/v1/videos/search`지만 과거 `/videos/search` 경로도 통용된다 — 실제 응답으로 확인한다. Pixabay 공식 문서는 봇 차단(403)이라 레이트리밋만 검증했다. 파라미터명(`video_type`, `per_page`, `order`)과 응답 필드(`hits[].videos.{large,medium,small,tiny}.url`, `hits[].duration`, `hits[].user`)는 **첫 구현 시 실제 응답을 찍어 확정**하고, 그 응답을 테스트 픽스처로 고정한다.

Pixabay는 영상에 orientation 필터가 없어 가로 소재가 많이 온다. 4.2의 `crop`이 이를 흡수한다.

### 3.3 폴백 체인

3중 루프. 바깥일수록 우선순위가 높다 — **관련성 > 매체 > 출처**.

```python
for query in [scene["on_screen"], project_topic, DEFAULT_QUERY]:  # 빈 문자열·중복 제거
    for kind in ("video", "photo"):
        for source in enabled_sources:            # settings.stock_sources 순서
            hits = source.search(query, kind)
            picked = pick(hits, used_ids, ctx.attempt, scene_index)
            if picked is not None:
                return picked
raise AppError(502, "STOCK_NO_RESULTS", "배경 소재를 찾지 못했습니다. 대본의 화면 문구를 바꿔 보세요.")
```

- `DEFAULT_QUERY = "abstract background"` — 최후 폴백. 이 쿼리가 0건일 일은 사실상 없지만 방어적으로 `STOCK_NO_RESULTS`로 끝낸다.
- 순서 근거: `on_screen`으로 영상은 없고 사진만 있다면, 그 사진이 `topic`으로 찾은 무관한 영상보다 낫다.

### 3.4 클립 선택 (`pick`)

1. `used_ids`(이미 다른 씬이 쓴 `(source, id)`)에 있는 후보 제외 → 같은 화면 반복 방지
2. 남은 후보를 `(ctx.attempt + scene_index) % len(candidates)` 위치부터 고름 → [재생성] 시 다른 소재. 기존 provider들의 `attempt` 변주 관례와 동일
3. 영상은 `video_files`(Pexels) / `videos.*`(Pixabay) 중 **세로에 가장 가깝고 1080 이상**인 파일을 고름. 없으면 가장 큰 것

---

## 4. 합성

### 4.1 씬 타이밍 (`render/timing.py`)

```python
def scene_spans(scenes: list[dict], duration_sec: float) -> list[tuple[float, float]]:
    """narration 글자수 비율로 전체 길이를 씬에 배분한다.

    누적 반올림 오차는 마지막 씬이 흡수해 spans[-1][1] == duration_sec을 보장한다.
    """
```

- `duration_sec`은 `ctx.inputs["captions"]["duration_sec"]`. slideshow에선 "있으면 진행률용"이었지만 stock에선 **필수** — 없으면 `AppError(409, "CAPTIONS_DURATION_MISSING", ...)`
- narration이 전부 빈 문자열이면 균등 분할로 폴백(0 나눗셈 방지)
- 예상 오차 ±0.5초. 배경 전환 시점이라 육안으로 드러나지 않는다

### 4.2 ffmpeg 커맨드 (`utils/ffmpeg.build_stock_cmd`)

핵심은 **입력 옵션만으로 길이를 맞추는 것**이다. 클립이 씬보다 짧으면 반복, 길면 잘려 필터에 `trim`이 필요 없다.

```
<exe> -y -progress pipe:1 \
  -stream_loop -1 -t 8.0  -i sources/scene1.mp4 \   # 영상 씬 — 짧으면 반복
  -loop 1       -t 12.0 -i sources/scene2.jpg \     # 이미지 씬
  -stream_loop -1 -t 10.0 -i sources/scene3.mp4 \
  -i <voice.mp3 절대경로> \
  -filter_complex "
    [0:v]scale=1080:1920:force_original_aspect_ratio=increase,
         crop=1080:1920,fps=30,setsar=1,setpts=PTS-STARTPTS[v0];
    [1:v]...[v1];
    [2:v]...[v2];
    [v0][v1][v2]concat=n=3:v=1:a=0[bg];
    [bg]subtitles=<srt_rel>:force_style='<slideshow와 동일>'[v]
  " \
  -map "[v]" -map 3:a \        # 씬 N개면 오디오는 N번째 입력 → -map N:a
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \
  <out_rel>
```

- **`-map`으로 스톡 클립의 오디오를 버린다** — 나레이션만 남는다
- **`crop=1080:1920`** 이 가로 소재를 중앙 세로 크롭 → orientation 필터가 없는 Pixabay 영상도 흡수
- **자막 스타일·경로 규칙은 slideshow와 완전히 동일** — `force_style` 상수와 "상대경로 + cwd=저장소 루트"(Windows `:` 회피)를 그대로 공유한다
- 함수는 순수 조립. 실행은 기존 `ffmpeg.run(cmd, cwd, on_progress, total_sec)`을 재사용한다

### 4.3 소재 파일 관리

- 저장 위치: `projects/{id}/render/sources/scene{N}.{ext}`
- **Asset으로 기록하지 않는다** — 단계당 asset 1개 원칙(`find_asset_by_stage`)을 지켜 asset 서빙·다운로드 API를 무수정 재사용. 최종 산출물은 `render.mp4` 하나뿐
- 대신 `_replace_assets`가 지우지 못하므로, `run()` 진입 시 `storage.clear_dir("projects/{id}/render/sources")`로 직접 비운다. 재생성 시 이전 소재가 쌓이지 않는다
- 다운로드는 씬당 `STOCK_MAX_BYTES`·`STOCK_TIMEOUT_SEC` 상한. 초과하면 그 소재만 건너뛰고 다음 후보로 진행

### 4.4 진행률

`ctx.on_progress`를 두 구간으로 나눠 쓴다.

| 구간 | 범위 | 메시지 |
|---|---|---|
| 검색·다운로드 | 0 ~ 40% | `"배경 소재 준비 중… (2/3)"` |
| ffmpeg 합성 | 40 ~ 100% | `"영상 합성 중…"` |

`ffmpeg.run`에 넘기는 콜백을 `lambda p, m: ctx.on_progress(40 + 0.6 * p if p is not None else None, m)`으로 감싼다 (`p == 0`도 유효한 진행률이므로 `if p`가 아니다). `ffmpeg.py`는 수정하지 않는다.

---

## 5. 설정

`app/config.py`의 `Settings`에 추가하고 `.env.example`에도 같은 값을 넣는다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `PEXELS_API_KEY` | `""` | 무료 발급 |
| `PIXABAY_API_KEY` | `""` | 무료 발급 |
| `STOCK_SOURCES` | `["pexels", "pixabay"]` | **순서가 폴백 우선순위.** `.env`에는 `CORS_ORIGINS`와 같은 JSON 배열 표기로 쓴다 |
| `STOCK_MAX_BYTES` | `52428800` | 씬당 다운로드 상한 (50MB) |
| `STOCK_TIMEOUT_SEC` | `30` | 소재 1건 다운로드 타임아웃(초) |

- **`RENDER_PROVIDER`는 `slideshow` 기본값을 유지한다.** 키 없이도 기존 흐름이 깨지지 않고, 쓰려는 사람만 `stock`으로 바꾼다
- `.env.example`에 현재 `RENDER_PROVIDER`·`RENDER_BG_COLOR`·`RENDER_FONT`·`RENDER_FONT_SIZE`·`WORKER_CONCURRENCY`가 누락돼 있다 — 이참에 함께 채운다

---

## 6. 에러 처리

전부 `AppError`로 던지고 `run_claimed_stage`가 FAILED로 흡수해 한국어 메시지를 UI에 보여준다 (기존 패턴 그대로).

| 상황 | 코드 | 시점 |
|---|---|---|
| 키가 하나도 없음 | `STOCK_API_KEY_MISSING` | `validate()` — 실행 전 조기 실패 |
| captions `duration_sec` 없음 | `CAPTIONS_DURATION_MISSING` | `run()` 진입 |
| voice mp3 / captions srt 없음 | `VOICE_ASSET_MISSING` / `CAPTIONS_ASSET_MISSING` | 기존 `render/input.py` 재사용 |
| script 씬이 비어 있음 | `SCRIPT_SCENES_MISSING` | `run()` 진입 |
| 폴백 체인 끝까지 0건 | `STOCK_NO_RESULTS` | 검색 후 |
| 상한 초과·타임아웃 | (에러 아님) 해당 소재만 건너뛰고 다음 후보 | 다운로드 중 |
| 한 씬에서 후보 3개 연속 다운로드 실패 | `STOCK_DOWNLOAD_FAILED` | 다운로드 재시도 소진 |

- **키가 하나만 있으면 그 소스만 쓴다.** `validate()`는 `stock_sources` 중 키가 있는 것만 남기고, 하나도 없을 때만 실패한다
- API 4xx/5xx·네트워크 오류는 그 소스를 건너뛰고 다음 소스로. 전부 실패해야 `STOCK_NO_RESULTS`

---

## 7. 산출물

- **Asset 1개**: `kind=VIDEO`, `path=projects/{id}/render/render.mp4` — slideshow와 동일
- **`StageResult.output`**:

```json
{
  "provider": "stock",
  "width": 1080, "height": 1920,
  "duration_sec": 30.2, "size_bytes": 4823910,
  "sources": [
    {"scene": 1, "source": "pexels", "kind": "video",
     "query": "서울 야경", "url": "https://www.pexels.com/video/...", "author": "홍길동"}
  ]
}
```

`sources`는 출처 표기와 디버깅(어떤 쿼리가 실제로 먹혔는지)을 겸한다.

---

## 8. 테스트 전략 (TDD, 네트워크·ffmpeg 없이)

| 대상 | 방식 |
|------|------|
| `timing.scene_spans` | 순수 함수. 합계 == duration, 마지막 씬이 오차 흡수, 씬 1개, narration 전부 빈 문자열 |
| `utils/stock/pexels` · `pixabay` | 가짜 HTTP 클라이언트 주입 → 실제 응답 픽스처 → `Clip` 매핑, 0건, 4xx |
| 폴백 체인 | 가짜 소스 주입 → `on_screen` 0건이면 topic으로, video 0건이면 photo로, 씬 간 중복 배제, `attempt` 변주 |
| `ffmpeg.build_stock_cmd` | 인자 조립 단위테스트. `-stream_loop`/`-loop 1`, `-t` 값, `concat=n=`, 상대경로, `-map`으로 스톡 오디오 제외 |
| `StockRender` | 가짜 검색·다운로드·runner 주입 → `StageResult`·asset(VIDEO)·`output.sources` 검증. `sources/` 사전 정리 확인 |
| 에러 경로 | 키 없음, duration 없음, 씬 없음, 전 소스 0건 → 각 코드로 `AppError` |
| 통합 스모크 (`@pytest.mark.slow`) | 실제 API 1회 + 실제 ffmpeg로 짧은 mp4 1개. **키가 없으면 skip.** 세로 크롭·자막 가독성 육안 검증은 이때 |

`httpx`를 런타임 의존성으로 승격한다 (지금은 dev 그룹).

---

## 9. 프론트엔드 (`web/src`)

- `lib/projects.ts`: `RenderOutput`에 `sources?: { scene: number; source: string; kind: string; query: string; url: string; author: string }[]` 추가. **선택 필드**라 slideshow 출력과 그대로 호환된다
- `pages/projects/ProjectDetail.tsx`의 `RenderView`: 영상 아래 "소재 출처" 목록 — 씬 번호 + 작가명 + Pexels/Pixabay 링크
- Pexels 가이드라인의 "prominent link to Pexels" 요구를 이로써 충족한다

---

## 10. 구현 중 검증할 리스크

1. **Pixabay API 스펙** — 공식 문서를 봇 차단으로 읽지 못했다. 파라미터·응답 필드를 첫 호출로 확정하고 픽스처로 고정한다 (3.2)
2. **Pexels 영상 엔드포인트 경로** — `/v1/videos/search` vs `/videos/search`. 실제 응답으로 확인 (3.2)
3. **한국어 검색 적중률** — `locale=ko-KR`·`lang=ko`가 실제로 얼마나 잡는지는 돌려봐야 안다. 폴백 체인이 자주 발동하면(= 대부분 `topic`이나 `abstract background`로 떨어지면) 영어 `visual_query` 필드 도입을 다음 슬라이스로 재검토
4. **`concat` 필터 입력 정합** — `fps`·`setsar`·`pix_fmt`가 씬마다 어긋나면 concat이 실패한다. 정규화 체인이 모든 입력에 동일하게 붙는지 커맨드 조립 테스트로 고정
5. **긴 filter_complex 문자열** — 씬 수가 늘면 Windows 커맨드라인 길이 제한(약 32KB)에 닿을 수 있다. 씬 3개 내외 대본에선 여유롭지만, 조립 테스트에 씬 10개 케이스를 넣어 길이를 관찰
6. **다운로드 시간** — 씬당 5MB 안팎 × 3씬이면 수 초~수십 초. 진행률 0~40% 구간이 실제로 움직이는지 스모크에서 확인
