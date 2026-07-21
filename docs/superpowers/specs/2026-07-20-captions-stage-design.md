# captions 단계 (음성 → 단어별 자막) 설계

- **한 줄 요약:** voice가 만든 mp3를 로컬 whisper로 받아써 **단어별 srt**를 만드는 `captions` 단계를 추가하고,
  그 과정에서 **단계 간 파일 전달(`input_assets`)** 을 일반화한다.
- **날짜:** 2026-07-20
- **선행:** [2026-07-09 전체 설계](2026-07-09-studio-design.md), [2026-07-20 voice 단계](2026-07-20-voice-stage-design.md)

## 1. 배경 & 목표

파이프라인은 `script → voice → captions → render`다. 지금까지 `script`와 `voice`가 구현됐고,
voice를 승인하면 다음 단계가 없어 프로젝트가 `DONE`이 된다.

이번 슬라이스는 **세 번째 단계 `captions`** 를 붙인다. 여기서 처음으로 필요해지는 토대가 하나 있다:

**단계 간 파일 전달.** script → voice는 JSON(`Stage.output`)만 넘기면 됐다.
captions는 **이전 단계가 만든 파일(mp3)** 이 입력이다. render(mp3 + srt → mp4)도 마찬가지라
지금 일반형을 세운다.

**목표:** 주제 입력 → 대본 → 음성 → **자막 생성·검토·승인**까지 한 흐름으로 동작한다.

**비목표(이번 슬라이스 아님):** render 단계, 비동기 워커·SSE, 자막 수동 편집,
언어·모델 선택 UI, GPU 설정, 산출물 이력 비교.

## 2. 결정 사항 (브레인스토밍 확정)

| 항목 | 결정 | 이유 |
|---|---|---|
| whisper 구현체 | **faster-whisper + `small`** | CTranslate2 기반이라 원본 대비 4~5배 빠르고 torch 의존이 없다. `small`이 한국어 정확도와 CPU 속도의 균형점 |
| 실행 방식 | **동기 유지 + `asyncio.to_thread`** | 기존 요청-내-실행 패턴을 지킨다. 워커·SSE는 원 설계대로 다음 슬라이스 |
| srt 큐 단위 | **단어 1개 = 큐 1개** | 정보 손실 0. render가 나중에 어떤 스타일을 고르든 합치면 된다 — 합치기는 쉽고 쪼개기는 불가능 |
| 입력 전달 | **`StageContext.input_assets` 추가** | output(요약 JSON)과 asset(파일)의 기존 분리를 유지. render도 그대로 쓴다 |
| 검토 수단 | **오디오 재생 + 단어 하이라이트** | captions가 틀리는 방식은 '오인식'과 '싱크 밀림' 둘뿐이고, 둘 다 이 화면에서만 보인다 |

## 3. 데이터 모델 — 변경 없음

`assets` 테이블과 `Asset` 모델을 그대로 쓴다. **마이그레이션이 필요 없다** —
`assets.kind`에 CHECK 제약이 없어 새 코드값을 그냥 넣을 수 있다.

앱 상수만 한 줄씩 는다:

```python
class StageName(StrEnum):
    ...
    CAPTIONS = "captions"

class AssetKind(StrEnum):
    ...
    SRT = "SRT"
```

## 4. 파이프라인

```python
STAGE_ORDER = ["script", "voice", "captions"]   # render는 미구현
```

```
voice     needs_review ──[승인]──▶ approved ──▶ captions 단계 PENDING 등록 + current_stage="captions"
captions  needs_review ──[승인]──▶ approved ──▶ (마지막 구현 단계) 프로젝트 DONE
```

**`approve_stage`는 손대지 않는다.** `STAGE_ORDER`에 한 줄 추가하면 기존 일반화 코드가
그대로 동작한다 — voice 승인 시 captions가 `PENDING`으로 등록되고, captions 승인 시
`_next_stage`가 `None`이라 프로젝트가 `DONE`이 된다.

### 단계 간 입력 전달 (유일한 core 변경)

현재 `_previous_outputs(conn, project_id, upto)`는 앞선 단계들의 `Stage.output`만 모은다.
이를 output과 asset을 **한 번의 순회로** 같이 모으도록 바꾼다 (`find_stage`를 두 번 돌지 않게):

```python
async def _previous_context(conn, project_id: int, upto: str) -> tuple[dict, dict]:
    """이 단계 앞 단계들의 (outputs, assets)를 모은다.

    outputs: {단계이름: output}
    assets:  {단계이름: [{kind, path, meta}, ...]}
    """
```

`StageContext`에 필드 하나를 추가한다:

```python
input_assets: dict = field(default_factory=dict)   # {단계이름: [{kind, path, meta}]}
```

기존 provider(script·voice)는 이 필드를 쓰지 않으므로 **무변경**이다.

captions provider는 `ctx.input_assets["voice"]`에서 `kind == AssetKind.AUDIO`인 첫 항목의
`path`를 찾는다. 없으면 친절한 메시지의 `AppError`를 던지고, `run_stage`의 기존 `except`가
`FAILED`로 흡수한다.

## 5. Provider — faster-whisper

```python
REGISTRY["captions"] = {"fake": FakeCaptions, "whisper": WhisperCaptions}
```

```
app/providers/captions/
├─ __init__.py
├─ srt.py       # to_srt(words) -> str   (순수 함수)
├─ fake.py      # FakeCaptions
└─ whisper.py   # WhisperCaptions
```

- **설정:** `CAPTIONS_PROVIDER`(기본 `whisper`), `WHISPER_MODEL`(기본 `small`).
  기존 `SCRIPT_PROVIDER`·`VOICE_PROVIDER`와 동일 패턴. **테스트는 `fake` 강제**(오프라인·무모델).
- `device="cpu"`, `compute_type="int8"`은 모듈 상수로 고정한다.
  int8 양자화가 CPU에서 2배 이상 빠르고 한국어 품질 저하는 미미하다. GPU 설정은 YAGNI.
- **모델 로딩은 `@lru_cache` 싱글턴** — 프로세스당 1회. 최초 실행 시 `small` 모델(~500MB)을
  자동 다운로드하며 **그 첫 실행만** 느리다. README에 명시한다.
- `transcribe(...)`는 **CPU 블로킹 호출**이므로 `asyncio.to_thread`로 감싼다.
  이걸 빠뜨리면 whisper가 도는 30~60초 동안 서버 전체가 멎는다.
- `language="ko"` 고정, `word_timestamps=True`.
- **script 대본을 `initial_prompt`로 넘기지 않는다.** 고유명사 인식에 도움이 될 수는 있으나
  whisper가 프롬프트 문장을 그대로 뱉는 환각이 알려져 있고, 대본과 실제 발화가 어긋나면
  오히려 나빠진다. 필요해지면 나중에 켠다.
- provider 계약은 기존 `Provider`(`validate`/`run`) 그대로. API 키가 없으므로 `validate()`는 no-op.
  `run(ctx)`는 srt를 저장하고 경로·메타를 `StageResult`로 돌려준다 — Asset 행 생성은 core가 한다.

### FakeCaptions

외부 호출·모델 없이 결정적 자막을 만든다. `script` output의 나레이션을 공백으로 쪼개
단어마다 균등한 시간(예: 0.4초)을 배분한다. 파이프라인·전이·교체·서빙 테스트에 충분하다.

## 6. 산출물

- **파일:** `projects/{project_id}/captions/captions.srt` (`ctx.workdir` 규칙 그대로), `kind = SRT`.
- **서빙:** 기존 `GET /api/projects/{id}/stages/{name}/asset`을 그대로 탄다.
  `_MEDIA_TYPES`에 `AssetKind.SRT: "application/x-subrip"` 한 줄만 는다.
- **재생성 = 교체:** 기존 `_replace_assets`가 처리한다. 새 코드 없음.
- **`Stage.output`:**
  ```json
  {
    "language": "ko",
    "duration_sec": 41.2,
    "word_count": 87,
    "words": [{"w": "안녕하세요", "s": 0.12, "e": 0.68}, ...]
  }
  ```
  1분 쇼츠 ≈ 150~200단어라 JSONB 크기는 문제되지 않는다.
  `words`를 output에 담는 이유는 **프론트가 srt를 파싱하지 않게** 하기 위해서다.
  `duration_sec`은 faster-whisper가 돌려주는 `info.duration`(오디오 실제 길이)을 쓴다.
  `language`도 `info.language`를 그대로 기록한다 — `ko`로 고정 실행하지만 기록은 사실대로 남긴다.

### srt 직렬화 (`srt.py`)

- 큐 1개 = 단어 1개. 번호는 1부터, 타임코드는 `HH:MM:SS,mmm`.
- whisper가 `end <= start`인 단어를 내놓는 경우가 있다. **최소 50ms로 클램프**한다 —
  안 하면 재생기가 거부하는 잘못된 srt가 나온다.
- 단어 사이의 빈틈은 메우지 않는다(무음은 무음 그대로). YAGNI.
- 순수 함수라 DB·파일 없이 단위 테스트한다.

## 7. 프론트

`ScriptView`/`VoiceView`와 나란히 `CaptionsView`를 추가한다. 기존 관례대로 output 모양으로
자기 자신을 판별한다 — `hasCaptions(output)` = `'words' in output`.

- **재생하는 오디오는 voice 단계의 mp3다.** captions 카드지만 오디오 자산의 주인은 voice다.
  `ProjectDetail`이 stages에서 voice 단계의 `attempt`를 계산해 `StageCard`에 내려주고,
  `CaptionsView`가 `projects.assetUrl(projectId, 'voice', voiceAttempt)`로 재생한다.
  voice 단계를 못 찾으면 오디오 없이 단어 칩만 보여준다(방어).
- `onTimeUpdate`에서 현재 초에 해당하는 단어를 하이라이트한다. 단어가 수백 개이므로
  매 틱 전체 탐색 대신 **현재 인덱스에서 전진 탐색**한다. 사용자가 뒤로 시킬 수 있으므로
  현재 시각이 현재 단어보다 앞서면 인덱스를 0으로 되돌리고 다시 전진한다.
- `STAGE_LABEL`에 `captions: '자막 (captions)'` 한 줄.
- **실행 중 표시:** 수십 초가 걸리므로 [실행] 버튼은 `acting` 동안 `생성 중… (최대 1분)`으로
  바뀐다. 기존 `acting` 상태를 그대로 쓴다 — 새 상태를 만들지 않는다.
- `lib/projects.ts`에 `CaptionsOutput` 타입과 `hasCaptions` 가드를 추가한다.

## 8. 에러 처리

기존 경로를 그대로 쓴다 — 새 규칙을 만들지 않는다.

- voice asset이 없다 → `AppError` → `FAILED` + 친절 메시지
- 모델 다운로드 실패·오디오 디코딩 실패 → 일반 `except` → `FAILED` + 일반 안내(원문은 로그)
- 파일 쓰기 실패도 동일하게 `FAILED`로 흡수
- `FAILED`에서 [실행]으로 재시도 가능

## 9. 테스트 전략

| 대상 | 방법 |
|---|---|
| `to_srt` | 순수 단위 테스트 — 타임코드 포맷, 0초·1시간 경계, `end <= start` 클램프 |
| WhisperCaptions | **가짜 transcribe 주입**(EdgeTTS의 `communicate_factory`와 동일 패턴) — 모델·네트워크·오디오 없음 |
| 파이프라인 통합 | `CAPTIONS_PROVIDER=fake` 강제 — voice 승인 → captions `PENDING` → 실행 → `NEEDS_REVIEW` |
| 3단계 전이 | captions 승인 → 프로젝트 `DONE` |
| `input_assets` | captions가 voice의 mp3 경로를 실제로 받는지 / voice asset이 없으면 `FAILED` |
| Asset 교체 | captions 재생성 시 이전 srt 행·파일이 사라지고 새 것만 남는지 |
| 서빙 | 소유자 200 + `application/x-subrip`, 남의 프로젝트 404, 산출물 없으면 404 |

파일을 만드는 테스트는 `tmp_path` 등으로 격리해 저장소를 더럽히지 않는다.

## 10. 범위 요약

**포함:** `faster-whisper` 의존성 추가 / `captions` 상수·`STAGE_ORDER` 확장 / `StageContext.input_assets` + `_previous_context` /
`FakeCaptions`·`WhisperCaptions` + `CAPTIONS_PROVIDER`·`WHISPER_MODEL` 설정 / `srt.py` 직렬화 /
`SRT` media type 한 줄 / 상세 화면 captions 카드(오디오 + 단어 하이라이트) / 위 테스트 / README 모델 다운로드 안내

**제외:** render, 비동기 워커·SSE, 자막 수동 편집, 언어·모델 선택 UI, GPU 설정, 산출물 이력 비교
