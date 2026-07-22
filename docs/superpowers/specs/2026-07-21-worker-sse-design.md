# 백그라운드 워커 + SSE — 설계 문서 (Design Spec)

- **작성일:** 2026-07-21
- **대상:** 단계 실행을 HTTP 요청에서 분리하고(백그라운드 워커), 진행 상황을 SSE로 UI에 푸시한다
- **상위 문서:** [2026-07-09-studio-design.md](2026-07-09-studio-design.md) (전체 설계)

---

## 1. 목표 & 범위

### 문제
[`app/core/pipeline.py`](../../../app/core/pipeline.py)의 `run_stage`가 **HTTP 요청 안에서 동기 실행**된다. 프론트는 POST 응답을 그대로 기다리고 버튼에 "생성 중… (최대 1분)"을 띄운다. 그래서:

- 프록시/브라우저 타임아웃에 노출된다 (whisper·ffmpeg는 수십 초~수 분).
- 페이지를 새로고침하면 진행 상황을 잃는다.
- 무슨 일이 얼마나 진행됐는지 알 수 없다.
- 단계마다 사람이 [실행]을 눌러야 해서 4단계를 끝까지 돌리려면 계속 붙어 있어야 한다.

### 목표
1. **요청과 실행 분리** — `run`은 즉시 202로 돌아오고 실행은 워커가 맡는다.
2. **실시간 상태 푸시** — 단계 상태 전이를 SSE로 UI에 밀어 넣는다(폴링 없음).
3. **진행률 표시** — provider가 진행 상황을 보고할 수 있는 계약(`on_progress`)을 만든다.
4. **전체 자동 실행 모드** — 프로젝트 생성 시 켜면 script→voice→captions→render를 검토 없이 끝까지 진행한다.

### 확정된 결정 (브레인스토밍)
| 항목 | 결정 | 이유 |
|------|------|------|
| 워커 런타임 | **앱 내 asyncio 워커** (`lifespan`에서 기동) | 새 의존성·새 프로세스 0. 현재 배포는 단일 uvicorn이고 provider들은 이미 `asyncio.to_thread`로 블로킹을 비켜준다 |
| 큐 | **`stages` 테이블 + 인메모리 `asyncio.Queue`** | 상태의 단일 출처는 DB. 큐에는 `stage_id`만 싣는다 |
| 이벤트 전달 | **인메모리 pub/sub** (`core/events.py`로 캡슐화) | 진행률처럼 초당 여러 번 나오는 이벤트에 가장 단순. 인터페이스로 감싸 뒀으므로 나중에 Postgres LISTEN/NOTIFY로 교체 가능 |
| 진행률 | **`on_progress(percent \| None, message)`** | script는 LLM 단일 호출이라 진짜 %가 존재하지 않는다. 가짜 진행바 대신 "무엇을 하는 중인지"를 보낸다 |
| 자동 실행 | **`projects.settings.auto_run`** (JSONB) | 새 컬럼 불필요. 기존 `approve_stage` 경로를 그대로 태우므로 상태 머신에 새 규칙이 없다 |

### 비범위 (YAGNI)
- **procrastinate** 도입 — 워커를 여러 대에서 돌려야 할 때 도입한다. 그때 바뀌는 곳은 `core/worker.py` 경계뿐이다.
- 워커 다중 프로세스·수평 확장, 잡 우선순위·지연 실행·자동 재시도 정책
- 진행률의 DB 영속화 (인메모리 전용 — 재접속 시 스냅샷으로 복구)
- 실패한 단계의 자동 재시도 (자동 모드에서도 실패하면 멈춘다)
- 프로젝트 목록 화면의 실시간 갱신 (SSE는 프로젝트 상세 화면 한정)

---

## 2. 상태 머신

### 새 상태 `QUEUED`
실행이 비동기가 되면 "실행을 눌렀지만 워커가 아직 집지 않은" 구간이 생긴다. 이때 상태가 `PENDING`으로 남으면 사용자 눈에는 아무 일도 안 일어난 것처럼 보이고 [실행] 버튼도 계속 눌린다. 상태를 하나 추가한다.

```
PENDING ──[run API: CAS]──▶ QUEUED ──[워커 선점: CAS]──▶ RUNNING ──┬─성공─▶ NEEDS_REVIEW
   ▲                                                                └─실패─▶ FAILED
   └────────────────[재생성 / 재시도]──────────────────────────────────────┘

NEEDS_REVIEW ──[승인]──▶ APPROVED ──▶ 다음 단계 PENDING 등록
                                      (auto_run이면 이어서 QUEUED로 투입)
```

`ALLOWED_TRANSITIONS` 갱신:
```python
PENDING:      {QUEUED}
QUEUED:       {RUNNING, FAILED}          # FAILED는 기동 복구 경로
RUNNING:      {NEEDS_REVIEW, FAILED}
NEEDS_REVIEW: {APPROVED, PENDING}        # 승인 / 재생성
FAILED:       {QUEUED}                   # 재시도는 곧바로 큐로
APPROVED:     set()
```

`stages.status`는 CHECK 제약 없는 varchar이므로([`app/models/stage.py`](../../../app/models/stage.py)) **마이그레이션은 컬럼 코멘트 갱신 한 줄**이다.

### CAS 두 번
기존 `claim_stage_run`(`PENDING|FAILED → RUNNING`)을 두 개의 이름 붙은 쿼리로 나눈다. 둘 다 `WHERE ... AND status IN (...)` + `RETURNING id` 형태라 **영향 행이 0이면 경합에서 졌다는 뜻**이다.

| 쿼리 | 전이 | 호출자 |
|------|------|--------|
| `enqueue_stage` | `PENDING\|FAILED → QUEUED` | run/regenerate API, 자동 연쇄 |
| `claim_stage_run` | `QUEUED → RUNNING` | 워커 |

이 구조 덕분에 중복 실행이 API 레벨과 워커 레벨 양쪽에서 구조적으로 막힌다. 큐에 같은 `stage_id`가 두 번 들어가도 두 번째 `claim`이 0행을 반환하고 조용히 버려진다.

---

## 3. 백그라운드 워커 (`app/core/worker.py`)

### 구조
```python
class StageWorker:
    def __init__(self, session_factory, concurrency: int = 1): ...
    async def start(self) -> None       # 기동 복구 → 워커 태스크 N개 생성
    async def stop(self) -> None        # 진행 중 작업을 5초 기다린 뒤 취소
    def enqueue(self, stage_id: int) -> None
    async def run_one(self, stage_id: int) -> None   # 테스트가 직접 부르는 단위
```

- **`session_factory` 주입이 설계 제약이다.** 워커가 `async_session_maker`를 직접 잡으면 테스트의 SAVEPOINT 격리([`tests/conftest.py`](../../../tests/conftest.py)) 밖으로 나가 테스트 데이터를 못 보고 실제 DB에 쓰기를 흘린다. 팩토리를 받으면 테스트가 세션을 주입할 수 있다.
- **동시성 기본값 1** (`worker_concurrency` 설정). whisper와 ffmpeg는 CPU를 포화시키므로 병렬로 돌려도 서로 느려지기만 한다. 설정으로 올릴 수는 있게 둔다.
- 워커는 요청 세션이 아니라 **자체 세션**을 연다. 요청 수명에 묶이면 안 된다.

### 기동 복구
`start()`가 워커 태스크를 만들기 전에 고아 상태를 정리한다.

| 남은 상태 | 처리 | 이유 |
|---|---|---|
| `QUEUED` | 큐에 다시 넣는다 | 아직 시작 안 했으므로 재투입이 안전하다 |
| `RUNNING` | `FAILED` + `error="서버가 재시작되어 중단되었습니다."` | 중간 산출물 상태를 알 수 없다. 사용자가 재시도할 수 있다 |

### 실행 흐름 (`run_one`)
```
claim_stage_run(QUEUED → RUNNING) + commit   # 0행이면 조용히 반환
  → publish(stage 이벤트: RUNNING)            # 발행은 항상 commit 이후
  → 이전 단계 컨텍스트 수집 + on_progress 주입한 StageContext 구성
  → provider.validate() → provider.run(ctx)
  → 성공: 산출물 교체 → NEEDS_REVIEW  /  실패: FAILED (기존 예외 처리 규칙 그대로)
  → commit → publish(stage 이벤트: 최종 상태)
  → auto_run이면 approve_stage() 호출 → 다음 단계를 enqueue
```

[`pipeline.py`](../../../app/core/pipeline.py)의 `run_stage`는 "provider를 실행하고 결과를 반영한다"는 알맹이만 남기고, **상태 선점과 트랜잭션 소유는 워커로 옮긴다.** `approve_stage` / `regenerate_stage`는 그대로 pipeline에 남는다 (`regenerate_stage`는 마지막의 `run_stage` 직접 호출만 `enqueue`로 바꾼다).

예외 처리는 기존 규칙을 유지한다 — `AppError`는 친절 메시지를 그대로 `error`에 담고, 그 외 예외는 로그만 남기고 일반 안내 문구로 치환한다.

### 앱 배선 (`app/main.py`)
`FastAPI(lifespan=...)`를 추가해 기동 시 `StageWorker.start()`, 종료 시 `stop()`을 부른다. `ASGITransport`는 lifespan 이벤트를 보내지 않으므로 **기존 테스트에서 워커가 자동 기동하지 않는다** — 의도된 동작이다.

---

## 4. 자동 실행 모드

`projects.settings` JSONB에 `auto_run: bool`을 넣는다. 프로젝트 생성 모달의 체크박스 하나로 켠다.

- 생성 시 `auto_run`이면 `script` 단계를 만든 직후 곧바로 `enqueue`한다.
- 워커가 단계를 성공시키면(`NEEDS_REVIEW`) **기존 `approve_stage`를 그대로 호출**한다. `NEEDS_REVIEW → APPROVED`는 이미 허용된 전이이므로 상태 머신에 새 규칙이 필요 없고, 자동/수동이 같은 코드를 지난다. `actor_id`는 프로젝트 소유자.
- `approve_stage`가 다음 단계를 `PENDING`으로 등록하면 이어서 `enqueue`한다.
- **실패하면 연쇄가 멈춘다.** `FAILED`로 남고 자동 재시도는 없다. 사용자가 상세 화면에서 재시도한다.
- 마지막 `render` 승인 → 프로젝트 `DONE` (기존 `_next_stage() is None` 분기 그대로).

---

## 5. 이벤트 버스 (`app/core/events.py`)

### 인터페이스
```python
_subscribers: dict[int, set[asyncio.Queue]]   # project_id → 구독자 큐들
_last_progress: dict[int, dict]               # stage_id → 마지막 진행률

def publish(project_id: int, event: dict) -> None       # 동기·논블로킹·예외를 던지지 않음
async def subscribe(project_id: int) -> AsyncIterator    # async with, finally에서 구독 해제
```

- **`publish`는 절대 `await`하지 않고 예외도 삼킨다.** 이벤트 발행 실패가 파이프라인을 죽이면 안 된다.
- 구독자 큐는 `maxsize=100`. 가득 차면 **가장 오래된 것을 버리고** 새 것을 넣는다 — 진행률은 최신값만 의미가 있고, 느린 클라이언트 하나가 워커를 멈춰세우면 안 된다.
- `_last_progress`는 단계가 종료될 때 삭제한다.

### 이벤트 3종
| 타입 | 언제 | 내용 |
|------|------|------|
| `snapshot` | 구독 직후 1회 | `_detail()` 전체 + 진행 중 단계의 마지막 진행률 |
| `stage` | 단계 상태 전이 시 | `_stage_public()` + 프로젝트 `status`/`current_stage` |
| `progress` | provider가 `on_progress` 호출 시 | `{stage, percent: number\|null, message}` — **DB에 저장하지 않는다** |

`snapshot`을 먼저 보내므로 프론트는 "GET detail과 SSE 중 무엇이 먼저 도착했나"를 신경 쓸 필요가 없다.

### 진행률 계약 (`StageContext.on_progress`)
```python
on_progress: Callable[[float | None, str], None]   # 동기, 논블로킹
```
provider가 호출하지 않으면 상태 전이만 흐른다(계약은 선택적). 이번에 실제로 채우는 범위:

| 단계 | percent | message 예시 |
|------|---------|--------------|
| `script` | `None` | "대본을 생성하는 중…" |
| `voice` | `None` | "음성 합성 중…" |
| `captions` | 누적 세그먼트 끝시각 / 전체 길이 | "받아쓰는 중…" |
| `render` | ffmpeg `-progress` 파이프의 `out_time_us` / 전체 길이 | "영상 합성 중…" |

`script`는 LLM 단일 호출, `voice`는 edge-tts가 전체 텍스트를 한 번에 합성하고 총량을 알려주지 않으므로 둘 다 진짜 %가 없다. 문장 단위 %를 내려면 씬별로 나눠 합성하고 mp3를 이어붙여야 하는데 이는 산출물이 달라지는 동작 변경이라 이번 범위 밖이다. UI는 `percent`가 `null`이면 불확정 바를 보여준다.

`render`는 [`utils/ffmpeg.run`](../../../app/utils/ffmpeg.py)에 `-progress pipe:1`을 추가하고 stdout을 줄 단위로 읽는 형태로 바꾼다. `captions`는 whisper의 지연 제너레이터를 소비하는 루프 안에서 보고한다 — 둘 다 워커 스레드에서 호출되므로 `on_progress`는 **스레드 안전해야 한다**(내부에서 `loop.call_soon_threadsafe`로 넘긴다).

---

## 6. SSE 엔드포인트

### `GET /api/projects/{id}/events`
- `current_user` 의존성 + 소유자 검증. 남의 프로젝트면 기존 규칙대로 **404**.
- `StreamingResponse(media_type="text/event-stream")`, 헤더 `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- 구독 등록 → 즉시 `snapshot` 전송 → 이후 이벤트 relay.
- **15초마다 `: ping` 코멘트**를 흘린다. 프록시 유휴 타임아웃을 막고 끊긴 클라이언트를 감지한다.
- 연결이 끊기면 `finally`에서 구독을 해제한다.

### 나머지 API 변경
| 엔드포인트 | 변경 |
|---|---|
| `POST .../run` | **202 Accepted**. 본문은 `QUEUED`가 반영된 detail. 이미 큐/실행 중이면 지금처럼 409 |
| `POST .../regenerate` | 동일 (**202**). `attempt+1`과 함께 `PENDING`으로 리셋한 뒤 **같은 트랜잭션에서 이어서 `enqueue`** (`NEEDS_REVIEW → PENDING → QUEUED`) |
| `POST .../approve` | 그대로 200 (즉시 끝나는 작업) |
| `POST /projects` | 요청 본문에 `auto_run: bool = False` 추가 |

---

## 7. 프론트엔드 (`web/src`)

### `lib/events.ts` — EventSource 래퍼
```ts
subscribeProject(id, handlers): () => void   // 정리 함수를 돌려준다
```

까다로운 지점은 **토큰 만료**다. `EventSource`는 401을 받으면 무한 재접속을 시도한다. 그래서 `onerror`가 뜨면 소켓을 닫고, **재연결 직전에 `projects.detail(id)`를 한 번 호출**한다. 이것이 [`lib/api.ts`](../../../web/src/lib/api.ts)의 401→refresh→재시도 로직을 그대로 태우므로, 성공하면 갱신된 쿠키로 `EventSource`를 새로 만들고 실패하면 로그아웃 상태로 떨어진다. 재연결은 지수 백오프(1s→2s→4s, 최대 30s).

### `pages/projects/ProjectDetail.tsx`
- `useEffect`로 구독. `snapshot`/`stage`는 `setDetail`, `progress`는 별도 state(`Record<stageName, {percent, message}>`).
- `acting` 플래그는 **"요청 전송 중"만** 뜻하게 축소된다. 실행 완료를 기다리지 않는다.
- `QUEUED`/`RUNNING` 카드에 진행률 바 + 메시지를 표시한다. `percent`가 `null`이면 불확정(indeterminate) 바 + 메시지만.
- [실행] 버튼은 `PENDING`/`FAILED`에서만 나타난다 (`QUEUED`가 생기면서 자연히 사라진다).

### 그 외
- `lib/projects.ts`: `STAGE_BADGE`에 `QUEUED` 추가, `create()`에 `auto_run` 인자
- `pages/projects/NewProjectModal.tsx`: "자동으로 끝까지 진행" 체크박스 + 설명 문구

---

## 8. 테스트 전략

| 대상 | 방식 |
|------|------|
| `core/events` | 발행/구독/해제. 구독자 2명이 같은 이벤트를 받는지. 큐 오버플로 시 **최신값이 남는지** |
| `core/worker` — 정상 | fake provider로 `run_one` 직접 호출 → `RUNNING`→`NEEDS_REVIEW` 전이와 `stage` 이벤트 발행 검증 |
| `core/worker` — 실패 | provider 예외 → `FAILED` + 자동 연쇄 중단 |
| `core/worker` — 경합 | 같은 `stage_id`를 두 번 `run_one` → 두 번째는 0행 claim으로 무시 |
| `core/worker` — 기동 복구 | `RUNNING`/`QUEUED` 행을 심어두고 `start()` → 각각 `FAILED` 정리 / 큐 재투입 |
| API — run | **202** + `QUEUED` 반환, 중복 호출 **409**, 남의 프로젝트 **404** |
| API — SSE | 스트림 접속 → `snapshot` 수신 → `publish` 후 해당 이벤트 수신 → 남의 프로젝트 **404** |
| 자동 모드 | `auto_run` 프로젝트가 fake provider 4단계를 관통해 프로젝트 `DONE`까지 |
| `utils/ffmpeg` | `-progress pipe:1` 인자 포함 확인 + stdout 줄 파싱 단위테스트 (ffmpeg 미실행) |

**워커 테스트는 루프를 돌리지 않고 `run_one(stage_id)`를 직접 호출**하고 세션 팩토리를 주입한다. 그래야 SAVEPOINT 격리 안에 머문다. 이벤트는 테스트에서 직접 `subscribe`해 수신을 확인한다.

---

## 9. 변경 요약

| 위치 | 변경 |
|------|------|
| `app/constants.py` | `StageStatus.QUEUED = "QUEUED"` |
| `app/config.py` | `worker_concurrency: int = 1` |
| `app/core/events.py` | **신규** — 인메모리 pub/sub |
| `app/core/views.py` | **신규** — API 응답·SSE 이벤트가 공유하는 공개 표현(`api/projects.py`에서 이동) |
| `app/core/worker.py` | **신규** — `StageWorker` |
| `app/core/pipeline.py` | `ALLOWED_TRANSITIONS` 갱신, `run_stage`에서 상태 선점 분리, `regenerate_stage`가 `enqueue` |
| `app/providers/base.py` | `StageContext.on_progress` 추가 |
| `app/providers/*` | script·voice·captions·render가 `on_progress` 호출 |
| `app/utils/ffmpeg.py` | `-progress pipe:1` + stdout 파싱 → 진행률 콜백 |
| `app/queries/stages.sql` | `queue_stage`·`find_stage_by_id`·`fail_running_stages`·`list_queued_stage_ids` 추가, `claim_stage_run` 조건 변경 |
| `app/api/projects.py` | SSE 엔드포인트, `run`/`regenerate` 202, `auto_run` 옵션 |
| `app/main.py` | `lifespan`으로 워커 기동/종료 |
| `alembic/versions/` | `stages.status` 컬럼 코멘트 갱신 |
| `web/src/lib/events.ts` | **신규** — EventSource 래퍼 |
| `web/src/lib/projects.ts` | `QUEUED` 배지, `auto_run` |
| `web/src/pages/projects/*` | 진행률 UI, 자동 진행 체크박스 |

---

## 10. 구현 중 검증할 리스크

1. **스레드에서의 `on_progress`** — whisper·ffmpeg는 `asyncio.to_thread` 안에서 돈다. 콜백이 이벤트 루프를 건드리므로 `call_soon_threadsafe` 경유가 맞는지 실제로 확인한다.
2. **Vite 개발 프록시의 SSE 버퍼링** — `/api` 프록시가 스트림을 버퍼링하면 이벤트가 뭉쳐서 도착한다. 개발 환경에서 실측하고 필요하면 프록시 설정을 조정한다.
3. **워커 종료 타이밍** — `stop()`이 렌더 중인 ffmpeg를 취소할 때 좀비 프로세스가 남지 않는지.
4. **자동 모드의 연쇄 깊이** — `run_one` 안에서 `approve` → `enqueue`가 재귀하지 않고 큐를 경유하는지(스택이 쌓이면 안 된다).
