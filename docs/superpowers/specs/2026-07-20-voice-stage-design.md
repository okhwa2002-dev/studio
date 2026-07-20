# voice 단계 (대본 → 음성) 설계

- **한 줄 요약:** 승인된 대본을 edge_tts로 읽어 mp3를 만드는 `voice` 단계를 추가하고, 그 과정에서 **Asset(산출물) 모델**과 **다단계 전이**를 처음 도입한다.
- **날짜:** 2026-07-20
- **선행:** [2026-07-09 전체 설계](2026-07-09-studio-design.md), [2026-07-16 script provider](2026-07-16-script-providers-design.md)

## 1. 배경 & 목표

파이프라인은 `script → voice → captions → render`다. 지금까지 `script` 단계만 구현됐고,
승인하면 프로젝트가 바로 `DONE`이 된다(다음 단계가 없어서 임시로 그렇게 둔 것).

이번 슬라이스는 **두 번째 단계 `voice`** 를 붙인다. 이때 두 가지 토대가 처음 필요해진다:

1. **Asset** — voice는 JSON이 아니라 **mp3 파일**을 낳는다. captions(srt)·render(mp4)도 마찬가지라
   산출물 파일을 담을 테이블이 필요하다.
2. **다단계 전이** — "승인하면 다음 단계를 등록한다"는 상태 머신이 실제로 필요해진다.

**목표:** 주제 입력 → 대본 생성·승인 → **음성 생성·청취·승인**까지 한 흐름으로 동작한다.

**비목표(이번 슬라이스 아님):** captions/render 단계, 비동기 워커·SSE, 목소리 선택 UI,
음성 편집, 여러 산출물 이력 비교.

## 2. 결정 사항 (브레인스토밍 확정)

| 항목 | 결정 | 이유 |
|---|---|---|
| mp3 저장 | **Asset 테이블 도입** | captions·render도 파일을 낳음. 설계 원안대로 토대를 지금 세운다 |
| 목소리 선택 | **기본 한국어 목소리 고정** | 파이프라인 흐름 완성이 먼저. 선택 UI는 나중 |
| 재생성 시 이전 산출물 | **교체(이전 행+파일 삭제)** | 단계당 항상 최신 1건 → 모델·UI·디스크가 단순 |

## 3. 데이터 모델

```
Project ──1:N──▶ Stage ──1:N──▶ Asset
```

```python
class AssetKind(StrEnum):      # app/constants.py (기존 StrEnum 관례)
    AUDIO = "AUDIO"            # 이후 SRT/VIDEO/IMAGE 추가

class Asset(BaseEntity, table=True):
    stage_id: int              # FK → stages.id
    kind: str                  # AssetKind
    path: str                  # STORAGE_PATH 기준 상대 경로
    meta: dict                 # JSONB — voice, size_bytes 등
    # id, created_at/by, updated_at/by → BaseEntity 상속
```

- 스키마는 SQLModel + **Alembic 마이그레이션 1개**. 조회·변경 쿼리는 기존 관례대로 `app/queries/assets.sql` + aiosql.
- `meta`에 **길이(duration)는 넣지 않는다.** 정확한 길이는 다음 captions 단계의 whisper가 계산하므로,
  지금 넣으면 추정값이 두 곳에 생긴다(YAGNI).
- 관계는 1:N으로 두되, **교체 정책상 단계당 유효 행은 항상 0 또는 1**이다.
  (1:N 스키마를 유지하는 이유: 나중에 이력 보존으로 정책만 바꿔도 스키마 변경이 없다.)

## 4. 파이프라인 — 다단계 전이

```
STAGE_ORDER = ["script", "voice"]        # captions/render는 미구현
```

```
script  needs_review ──[승인]──▶ approved ──▶ voice 단계 PENDING 등록 + current_stage="voice"
voice   needs_review ──[승인]──▶ approved ──▶ (마지막 구현 단계) 프로젝트 DONE
```

- `approve_stage`를 일반화한다: `STAGE_ORDER`에서 **다음 단계가 있으면** 그 단계를 `PENDING`으로 만들고
  `current_stage`를 갱신, **없으면** 프로젝트 `DONE`. (지금의 "무조건 DONE"을 대체)
- **실행 트리거는 명시적 [실행] 버튼**을 유지한다(Slice 1 결정 계승). 승인은 다음 단계를 *등록*만 하고 실행하지 않는다.
- **입력 전달:** 현재 `StageContext.inputs`가 `{}`로 하드코딩돼 있다.
  이를 **직전 단계의 output 주입**으로 일반화한다. voice는 `inputs["script"]`의
  `scenes[].narration`을 순서대로 이어붙여 읽는다.
- 이미 존재하는 단계를 다시 승인해도 중복 생성하지 않는다(멱등).

## 5. Provider — edge_tts

```python
REGISTRY["voice"] = {"fake": FakeVoice, "edge_tts": EdgeTTS}
```

- **기본 provider는 설정 `VOICE_PROVIDER`** (script의 `SCRIPT_PROVIDER`와 동일 패턴).
  기본값 `edge_tts`, **테스트는 `fake` 강제**(오프라인·무과금).
- edge_tts는 **무료·API 키 불필요**(네트워크만 필요) → `validate()`는 사실상 no-op.
- 한국어 기본 목소리는 provider 모듈 상수(`_VOICE`)로 고정.
- provider 계약은 기존 `Provider`(`validate`/`run`) 그대로. `run(ctx)`는 mp3를 저장하고
  **저장 경로·메타를 `StageResult`로 돌려준다** — Asset 행 생성은 core(pipeline)가 한다.
  (provider는 "무엇을 만들지"만 알고, "어떻게 기록할지"는 모른다.)

## 6. 파일 저장 & 서빙

- **저장 경로:** `STORAGE_PATH/projects/{project_id}/voice/{stage_id}.mp3`
  (`STORAGE_PATH`는 기존 설정. 프로젝트별로 묶여 삭제·정리가 쉽다.)
- **서빙:** 정적 마운트가 아니라 **인증된 전용 엔드포인트**
  `GET /api/projects/{project_id}/stages/{name}/asset` → `FileResponse`
  (이번 슬라이스에서 `name`은 `voice`뿐이고 `media_type="audio/mpeg"`. 단계 일반형으로 두어
  captions(srt)·render(mp4)에서 경로를 바꿀 일이 없게 한다 — `media_type`은 Asset.kind로 정한다.)
  - 이유: 기존 **owner 격리**를 그대로 태운다. 남의 프로젝트 음성은 `404`(존재 여부도 숨김 — 기존 `Errors.not_found()` 관례).
  - 정적 마운트는 경로만 알면 누구나 받을 수 있어 이 앱의 격리 정책과 맞지 않는다.
- **재생성 = 교체:** 새 mp3를 만들기 전에 해당 stage의 기존 Asset 행과 실제 파일을 삭제한다.
  파일이 이미 없어도 실패하지 않는다(멱등).

## 7. 프론트

- 상세 화면에 **voice 카드**를 추가한다. script 카드와 **동일한 배지·버튼 구조**(실행 / 승인·재생성)를 재사용.
- 검토 수단은 **`<audio controls>` 재생**. `src`는 6절의 서빙 엔드포인트.
- 재생성 후에도 브라우저가 옛 음성을 캐시하지 않도록 `src`에 `attempt`를 쿼리로 붙인다.
- script가 아직 승인 전이면 voice 카드는 `PENDING`(대기) 상태로 보이고 실행 버튼은 비활성.

## 8. 에러 처리

기존 경로를 그대로 쓴다 — 새 규칙을 만들지 않는다.

- edge_tts 네트워크/외부 오류 → `run_stage`의 `except`가 흡수 → stage `FAILED` + **일반 안내 메시지**(원문은 로그)
- 앱은 죽지 않으며, `FAILED`에서 [실행]으로 재시도 가능
- 파일 쓰기 실패도 동일하게 `FAILED`로 흡수

## 9. 테스트 전략

| 대상 | 방법 |
|---|---|
| EdgeTTS provider | **가짜 TTS 클라이언트 주입** — 실제 네트워크 호출 없음 |
| 파이프라인·API 통합 | `VOICE_PROVIDER=fake` 강제 (기존 conftest 패턴 확장) |
| 다단계 전이 | script 승인 → voice 단계가 `PENDING`으로 생성되고 `current_stage` 갱신 / voice 승인 → 프로젝트 `DONE` |
| Asset 교체 | 재생성 시 이전 Asset 행·파일이 사라지고 새 것만 남는지 |
| 서빙 엔드포인트 | 소유자는 200 + `audio/mpeg`, **남의 프로젝트는 404**, 산출물이 아직 없으면 404 |

파일을 만드는 테스트는 `tmp_path` 등으로 격리해 저장소를 더럽히지 않는다.

## 10. 범위 요약

**포함:** Asset 모델·마이그레이션 / 다단계 전이 + inputs 주입 / FakeVoice·EdgeTTS provider + `VOICE_PROVIDER` 설정 /
파일 저장·삭제 + 인증된 서빙 엔드포인트 / 상세 화면 voice 카드 + 오디오 재생 / 위 테스트

**제외:** captions·render, 비동기 워커·SSE, 목소리 선택 UI, 음성 편집, 산출물 이력 비교
