# 앱 로그 콘솔 출력 설계 (Design Spec)

- **작성일:** 2026-07-14
- **한 줄 요약:** 지금 파일로만 나가는 앱 로그를 콘솔에도 내보내되, 파일과 동일한 타임스탬프 형식을 쓴다.

---

## 1. 배경 & 목표

### 지금
- **파일 로그에는 이미 시간이 찍힌다.** `app/utils/logging.py`의 포매터가 `%(asctime)s`를 `APP_TIMEZONE`(Asia/Seoul) 기준으로 넣는다.
- **앱 로거(`app`)에는 파일 핸들러만 달려 있다.** 콘솔로는 아무것도 나가지 않는다. 그래서 `app/main.py`의 예외 핸들러가 `logger.exception(...)`으로 남긴 스택트레이스를 보려면 `LOG_DIR`의 파일을 열어봐야 한다.
- 콘솔에 보이는 `INFO:     Uvicorn running on...` 류는 **uvicorn 자신의 로거**이며, uvicorn 기본 포매터에는 타임스탬프가 없다.

### 목표
개발 중 콘솔만 보고도 앱 로그(특히 예외)를 시간과 함께 즉시 볼 수 있게 한다.

### 범위
`app` 로거에 콘솔 핸들러를 추가한다. **파일 핸들러와 같은 포매터를 공유**한다.

### 비범위 (YAGNI)
- **uvicorn 자신의 로그**(시작 메시지, 액세스 로그)의 타임스탬프 — uvicorn에 별도 로깅 설정을 넘겨야 하는 별개 작업이다.
- SQL 쿼리 로그(`echo=True`) — 필요할 때 별도로 판단한다.
- 로그 레벨·형식을 `.env`로 설정하는 기능 — 지금 필요하지 않다.

---

## 2. 설계

`app/utils/logging.py`의 `configure_logging()`을 고친다.

```python
formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
formatter.converter = _local_time_converter   # APP_TIMEZONE 기준 벽시계 시각

file_handler = TimedRotatingFileHandler(...)  # 기존 설정 그대로
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

logger.handlers = [file_handler, console_handler]
```

출력 예:
```
2026-07-14 15:42:07 INFO app.main - Unhandled exception on POST /auth/login
```

### 결정 두 가지

**포매터는 하나를 두 핸들러가 공유한다.** 따로 만들면 형식을 바꿀 때 한쪽만 고치는 사고가 난다. 파일과 콘솔의 형식이 갈라질 이유가 없다.

**`stdout`으로 보낸다** (`StreamHandler`의 기본값은 `stderr`). `npm run dev`에서 `concurrently`가 `[api]` 접두사로 출력을 묶는데, 정상 로그가 에러 스트림으로 나가면 도구에 따라 에러로 오인되거나 빨갛게 표시된다.

### 중복 출력이 생기지 않는 이유
`app` 로거는 자기 핸들러로 직접 처리하고, 루트 로거에는 핸들러가 없다. uvicorn은 자기 로거(`uvicorn`, `uvicorn.access`)만 설정하고 루트를 건드리지 않는다. 따라서 우리 로그가 두 번 찍힐 경로가 없다.

---

## 3. 테스트

기존 `tests/test_logging.py`를 고치고 하나를 추가한다.

| 테스트 | 내용 |
|--------|------|
| `test_configure_logging_is_idempotent` (수정) | 핸들러 개수 단언을 `1` → `2`로. 파일·콘솔 각각 하나씩인지도 확인한다. 재실행해도 늘어나지 않는다는 것이 이 테스트의 요지다. |
| `test_console_handler_shares_formatter_and_writes_timestamp` (신규) | 콘솔 핸들러가 존재하고, 그 포매터가 파일 핸들러와 **동일 객체**이며, 레코드를 포맷하면 `YYYY-MM-DD HH:MM:SS`로 시작한다. |

포매터가 같은 객체인지 확인하는 것이 핵심이다 — 형식이 갈라지는 것을 막는 것이 이 설계의 결정 사항이므로, 그 결정을 테스트가 지켜야 한다.

---

## 4. 검증

1. `npm test` — 전체 통과
2. `npm run dev:api`로 띄운 뒤, 콘솔에 앱 로그가 타임스탬프와 함께 찍히는지 확인한다. 존재하지 않는 경로로 예외를 유발하는 대신, 기동 시 우리 로거가 남기는 줄이 없다면 임시로 확인할 필요 없이 테스트로 갈음한다.
3. 파일 로그(`LOG_DIR/studio.log`)가 이전과 동일하게 계속 기록되는지 확인한다(콘솔 추가가 파일 출력을 깨뜨리지 않았는지).
