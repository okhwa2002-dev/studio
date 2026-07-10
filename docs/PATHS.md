# 절대경로 관리

이 프로젝트는 로컬 개발 편의를 위해 일부 절대경로를 사용합니다. **프로젝트 폴더**(`D:\workspace\ok2020\studio`) 또는 **로그 폴더**(`D:\workspace\ok2020\log\studio`)의 위치가 바뀌면 아래 항목들을 함께 갱신해야 합니다.

## 1. 프로젝트 폴더 경로에 의존하는 곳

| 위치 | 현재 값 | 갱신 방법 |
|---|---|---|
| `PYTHONPYCACHEPREFIX` (Windows 사용자 환경변수, 파일이 아님) | `D:\workspace\ok2020\studio\.pycache` | PowerShell에서 `setx PYTHONPYCACHEPREFIX "<새 프로젝트 경로>\.pycache"` 실행 후 터미널/VS Code 재시작 |

## 2. 로그 폴더 경로에 의존하는 곳

| 위치 | 현재 값 |
|---|---|
| `.env`의 `LOG_DIR` | `D:/workspace/ok2020/log/studio` |
| `.env.example`의 `LOG_DIR` | `D:/workspace/ok2020/log/studio` |
| [app/config.py](../app/config.py)의 `Settings.log_dir` 기본값 | `D:/workspace/ok2020/log/studio` |

세 곳 모두 값을 새 로그 폴더 경로로 바꿔주면 됩니다. `.env`가 실제로 적용되는 값이고, `app/config.py`의 기본값은 `.env`에 `LOG_DIR`이 없을 때만 쓰이는 폴백이라 `.env`만 바꿔도 동작은 하지만, 새 환경을 셋업하는 사람이 기본값만 보고 착각하지 않도록 셋 다 맞춰두는 걸 권장합니다.

## 바꾸지 않아도 되는 곳

- **`STORAGE_PATH`** (`.env`) — `./storage`처럼 상대경로로 관리 중이라 폴더가 옮겨져도 그대로 따라감. 절대경로로 바꾸지 말 것.
- **`tests/test_logging.py`**의 `D:\workspace\ok2020\log\studio\...` 예시 — 로그 회전 파일명 규칙(정규식)만 검증하는 샘플 문자열이라 실제 `LOG_DIR` 값과 무관하게 동작함. 맞출 필요 없음.
