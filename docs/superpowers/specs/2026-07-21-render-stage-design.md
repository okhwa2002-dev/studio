# render 단계 — 설계 문서 (Design Spec)

- **작성일:** 2026-07-21
- **대상:** studio 파이프라인의 마지막 단계 `render` (자막·오디오·비주얼 합성 → 9:16 mp4)
- **상위 문서:** [2026-07-09-studio-design.md](2026-07-09-studio-design.md) (전체 설계)

---

## 1. 목표 & 범위

### 목표
voice(mp3) + captions(단어별 srt)를 받아 **세로 9:16 mp4**를 합성하는 `render` 단계를 추가한다.
승인 시 프로젝트가 `DONE`이 되고 사용자가 mp4를 다운로드한다.

### 확정된 결정 (브레인스토밍)
| 항목 | 결정 | 이유 |
|------|------|------|
| 렌더러 | **slideshow 1종만** (+ fake) | stock/ai_image는 미래 확장. voice/captions처럼 실 provider 1개 + fake로 시작 |
| ffmpeg 조달 | **imageio-ffmpeg 번들** | pip 의존성만으로 정적 ffmpeg 바이너리 동봉. 설치 수수·팀/클라우드 재현성. (현 PC에 ffmpeg 미설치) |
| 자막 스타일 | **한 단어씩 큰 중앙 팝업** | 기존 단어별 srt를 그대로 번인. 쇼츠 흔한 스타일, 가장 단순·견고, 산출물 재사용 |
| 배경 | 단색 `#0f172a`(slate-900), config로 변경 가능 | MVP. 그라데이션·이미지는 미래 |

### 비범위 (YAGNI)
- stock(Pexels/Pixabay) · ai_image 렌더러
- 구구(여러 단어) 카라오케 자막, 씬별 배경 전환, 트랜지션/효과
- 자막 폰트·크기·색상의 사용자 UI 선택 (config 상수로 고정 시작)
- ffprobe 기반 미디어 프로빙 (imageio-ffmpeg엔 ffprobe 미포함 → 애초에 의존 안 함)

---

## 2. 데이터 흐름 (입력 → 처리 → 출력)

### 입력 (`StageContext.input_assets` / `inputs`에서 해결)
- **voice 단계 `AUDIO` mp3** — 필수. 없으면 `AppError(409, "VOICE_ASSET_MISSING", ...)` → run_stage가 FAILED로 흡수 (captions의 `input_audio_path`와 동일 패턴)
- **captions 단계 `SRT`** — 필수. 없으면 `AppError(409, "CAPTIONS_ASSET_MISSING", ...)` → FAILED
- **길이(duration)**: `ctx.inputs["captions"]["duration_sec"]` 재사용 (출력 메타용). 합성 자체는 `-shortest`로 오디오에 맞추므로 길이 계산이 실행에는 불필요.
- 배경이 단색이라 script·이미지 입력은 사용하지 않는다.

### 처리 (`app/utils/ffmpeg.py`)
9:16 캔버스에 오디오를 싣고 자막을 번인해 H.264/AAC mp4를 만든다. (상세는 3장)

### 출력
- **Asset 1개**: `kind=VIDEO`, `path=projects/{id}/render/render.mp4`, `meta={size_bytes, width:1080, height:1920}`
- **`StageResult.output`**: `{provider, width:1080, height:1920, duration_sec, size_bytes}`
- 단계당 자산 1개 원칙(`find_asset_by_stage`)에 부합 → asset 서빙/다운로드 API 무수정 재사용.

---

## 3. ffmpeg 합성 로직 (`app/utils/ffmpeg.py`)

도메인 지식 없는 순수 기술 헬퍼(utils). "9:16 배경 + 자막 번인 + 오디오 믹스"만 안다.

### 바이너리 경로
```python
import imageio_ffmpeg
exe = imageio_ffmpeg.get_ffmpeg_exe()   # 번들된 정적 ffmpeg 절대경로
```

### 커맨드 개형
```
<exe> -y \
  -f lavfi -i color=c=<bg>:s=1080x1920 \   # 무한 색상 소스 (배경)
  -i <audio.mp3> \                          # 오디오
  -vf "subtitles=<srt_rel>:force_style='<style>'" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \
  <out_rel>
```
- **`-shortest`**: 색상 소스는 무한, 오디오가 끝나면 종료 → 길이 자동 정합(길이 계산 불필요).
- **`-pix_fmt yuv420p`**: 브라우저 `<video>` 호환.

### Windows 경로 함정 회피 (핵심)
`subtitles=` 필터 인자는 드라이브 문자 `C:`의 `:`가 필터 옵션 구분자와 충돌한다. 회피책:
- subprocess `cwd=<storage 루트>`로 실행하고, **자막·출력은 저장소 기준 상대경로 + 슬래시**(`projects/{id}/captions/captions.srt`)로 전달 → 드라이브 문자가 안 나와 `:` 충돌 소멸.
- `-i` 입력(오디오)은 필터가 아니라 절대경로 그대로 OK.

### 자막 스타일 (`force_style`)
한 단어씩 화면 중앙에 크게. 초기 고정값(예):
```
Fontname=<render_font>,Fontsize=30,PrimaryColour=&H00FFFFFF,
OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=10
```
- **실측 확정값(Task 8 스모크 육안 검증):** `Fontsize=30`(config `render_font_size` 기본값), `Alignment=10`.
- 처음엔 `Fontsize=96`/`Alignment=5`로 잡았으나 실제 번들 libass 렌더 결과 (1) 96은 5글자가 3줄로 줄바꿈될 만큼 과대(libass는 기본 PlayResY=288 좌표계로 해석), (2) `Alignment=5`는 중앙이 아니라 **좌상단**(이 libass는 레거시 SSA 넘버링 → 10이 정중앙)임이 드러나 각각 30·10으로 교정. `안녕하세요`가 9:16 정중앙에 한 줄로, 한글(Malgun Gothic) 정상 렌더 확인.
- `Fontname`은 **한글 지원 폰트**여야 한다. Windows 기본 `Malgun Gothic`을 config `render_font`로 둔다. 클라우드/리눅스 이전 시 한글 폰트 설치가 배포 의존성(문서화).

### 분리 설계 (테스트 용이)
```python
def build_slideshow_cmd(exe, bg, audio_abs, srt_rel, out_rel, style) -> list[str]: ...  # 순수 조립
async def run(cmd: list[str], cwd: str) -> None: ...   # asyncio.to_thread로 블로킹 실행, 실패 시 예외
```
- provider는 whisper/edge_tts처럼 runner를 **주입**받아 ffmpeg 없이 단위테스트 가능.

---

## 4. 배선 (기존 단계 패턴 1:1)

| 위치 | 변경 |
|------|------|
| `app/constants.py` | `StageName.RENDER = "render"`, `AssetKind.VIDEO = "VIDEO"` |
| `app/core/pipeline.py` | `STAGE_ORDER`에 `"render"` 추가. 마지막 단계 승인 시 DONE 처리 로직은 이미 존재(`_next_stage` None 분기) |
| `app/providers/render/` | `input.py`(voice+srt 경로 해결), `slideshow.py`, `fake.py`, `__init__.py` |
| `app/providers/base.py` | REGISTRY에 `"render": {"fake": FakeRender, "slideshow": SlideshowRender}` + import 2줄 |
| `app/config.py` | `render_provider="slideshow"`, `render_bg_color="#0f172a"`, `render_font="Malgun Gothic"`, `render_font_size=96` |
| `app/api/projects.py` | `_MEDIA_TYPES`에 `AssetKind.VIDEO: "video/mp4"` 한 줄 |
| `pyproject.toml` | `imageio-ffmpeg` 의존성 추가 |

`SlideshowRender`는 whisper와 동형: `input.py`로 경로 해결 → `utils/ffmpeg.run()` (블로킹은 `asyncio.to_thread`) → `storage`로 크기 확인 → `StageResult`.

---

## 5. 테스트 전략 (TDD, 기존과 동일)

| 대상 | 방식 |
|------|------|
| `utils/ffmpeg.build_slideshow_cmd` | 인자 조립 단위테스트 (ffmpeg 미실행). 상대경로·force_style·`-shortest` 포함 확인 |
| `render/input` | voice 누락 → `VOICE_ASSET_MISSING`, srt 누락 → `CAPTIONS_ASSET_MISSING` |
| `SlideshowRender` | fake runner 주입 → 경로 해결·StageResult·asset(kind=VIDEO) 검증 (ffmpeg 미실행) |
| `FakeRender` | 최소 바이트 mp4 산출 → 파이프라인 흐름 테스트가 render까지 관통 |
| 통합 스모크(선택, slow) | 실제 imageio-ffmpeg로 짧은 mp4 1개 생성 → 파일 존재·size>0. **자막 스타일·한글 폰트 육안 검증은 이때** |

---

## 6. 프론트엔드 (`web/src`)

- `lib/projects.ts`: `RenderOutput = {provider, width, height, duration_sec, size_bytes}` 타입, `hasRender()` 가드, `STAGE_LABEL.render = '영상 (render)'`
- `pages/projects/ProjectDetail.tsx`: `RenderView` 컴포넌트 — `<video controls>`(기존 `assetUrl` 재사용) + **다운로드 링크**(`<a download>`). `StageCard`의 View 목록에 추가.
- 상위 스펙의 최종 목표("render 승인 → DONE → mp4 다운로드")를 이로써 완성.

---

## 7. 구현 중 검증할 리스크 (미리 명시)

1. **자막 정렬/크기**(`Alignment=5`, `Fontsize`, `Outline`) — 번들 libass 버전 의존. 실제 mp4로 확인 후 상수 조정.
2. **한글 폰트 렌더** — 번인 폰트가 한글 미지원이면 □ 박스. `Malgun Gothic` 확인, 부재 폰트 폴백/에러 메시지.
3. **imageio-ffmpeg 최초 실행** — 바이너리 확보(다운로드/동봉) 지연 가능. `validate()`에서 `get_ffmpeg_exe()` 호출로 조기 확인 고려.
