# 활동 기록(감사 로그) 설계

- 작성일: 2026-07-30
- 범위: 사용자·관리자 행위의 DB 기록 · 관리자 조회 화면 · 90일 보관

## 1. 목적과 범위

지금 이 앱에서 "누가 무엇을 했는지"를 확인할 방법은 `LOG_DIR/studio.log` 파일뿐이다. 그 파일에는 미처리 예외와 워커 진행 상황이 들어 있을 뿐, 정상적으로 처리된 행위 — 관리자가 누구를 승인했는지, 누가 어떤 프로젝트를 지웠는지, 시스템 설정을 언제 누가 바꿨는지 — 는 **아무 흔적도 남지 않는다.** 계정이 잠겼다는 사실은 `users.locked_at`에 남지만 왜 잠겼는지, 어느 IP에서 시도했는지는 없다.

서버 로그 파일을 화면에 띄우는 방식은 택하지 않았다. 그 파일은 사람이 아니라 개발자가 장애를 볼 때 읽는 것이고, 여기서 필요한 것은 **행위 단위로 검색·필터되는 기록**이다.

**하는 것**

- 인증·관리자 행위·일반 사용자 쓰기 작업을 `audit_logs` 테이블에 기록
- 관리자 전용 `/admin/logs` 화면에서 기간·행위·결과·검색어로 조회
- 90일이 지난 기록을 기존 정리 잡이 삭제

**하지 않는 것**

- **변경 전/후 값(diff) 저장** — 어느 값이 무엇으로 바뀌었는지를 열로 저장하려면 호출부마다 diff를 만들어 넘겨야 하고, 민감값 마스킹 규칙이 따라붙는다. 무엇이 바뀌었는지는 `summary` 한 줄이 담당한다. 예외는 시스템 설정 하나다(3-4)
- **User-Agent 저장** — 목록이 지저분해지는 것에 비해 얻는 것이 적다. 계정 탈취 조사에 필요해지면 그때 열을 더한다
- **일반 사용자의 "내 활동 내역" 화면** — 조회는 관리자만 한다
- **리소스별 이력 패널** (프로젝트 상세의 "이 프로젝트에 무슨 일이 있었나") — 데이터는 `target_type`·`target_id`로 이미 조회 가능하지만, 화면은 만들지 않는다. 필요해지면 조회 API에 필터 두 개를 더하면 된다
- **서버 로그 파일(`studio.log`) 열람 화면** — 별개 기능이다
- **요청 본문·쿼리스트링 저장** — 로그인·비밀번호 변경의 본문에는 자격증명이 들어 있다. `app/db.py`의 SQL 로거가 파라미터를 일부러 안 찍는 것과 같은 이유다

## 2. 데이터 모델

`audit_logs` 테이블 하나를 추가한다. `app/models/audit_log.py` + Alembic 리비전 1건 + `docs/schema.sql` 갱신.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BIGINT PK | |
| `action` | VARCHAR NOT NULL | 행위 코드. `AuditAction` 값 (대문자) |
| `actor_id` | BIGINT NULL → `users.id` | 행위자. NULL 가능 (3-1) |
| `actor_email` | VARCHAR NULL | 행위 시점 스냅샷 |
| `actor_name` | VARCHAR NULL | 행위 시점 스냅샷 |
| `actor_ip` | VARCHAR(45) NULL | IPv6까지 들어간다 |
| `target_type` | VARCHAR NULL | `USER` \| `PROJECT` \| `NOTICE` \| `FAQ` \| `SYSTEM` |
| `target_id` | BIGINT NULL | 대상 행의 id. FK를 걸지 않는다 |
| `target_label` | VARCHAR NULL | 대상 이름 스냅샷 (프로젝트 제목, 사용자 이름, 공지 제목) |
| `http_method` | VARCHAR(10) NULL | `POST` \| `PUT` \| `PATCH` \| `DELETE` |
| `http_path` | VARCHAR(255) NULL | 실제 호출 경로 |
| `success_yn` | CHAR(1) NOT NULL | `Y`/`N`. 기존 `*_yn` 규칙 |
| `summary` | VARCHAR(200) NULL | 한 줄 설명 |
| `created_at` | TIMESTAMP NOT NULL | 사건 시각 |

`app/models/base.py`의 `created_at_field()`를 쓰고, INSERT 시 앱이 `now_local()`을 명시적으로 넘긴다(`insert_notice`와 같은 방식). DB `now()`는 컨테이너 세션 타임존(UTC) 기준이라 그대로 두면 로컬 벽시계 저장 규칙이 깨진다.

### 2-1. 스냅샷을 저장하는 이유

`actor_email`·`actor_name`·`target_label`은 JOIN으로 뽑을 수 있는데도 행에 복사해 둔다.

감사 로그는 "지금 그 대상이 어떤 상태인가"가 아니라 **"그때 무슨 일이 있었나"의 기록**이다. 사용자가 이름을 바꾸면 JOIN 방식의 목록은 과거 기록의 이름까지 소급해서 바뀐다. 더 나쁜 것은 프로젝트다 — `PROJECT_DELETE` 기록의 가치는 "무엇을 지웠는가"인데, 30일 뒤 정리 잡이 그 행을 완전히 지우면(`2026-07-30-project-delete-and-cleanup-design.md` 3-3) JOIN 결과가 NULL이 되어 **삭제 기록만 남고 무엇을 삭제했는지는 사라진다.**

같은 이유로 `target_id`에 FK를 걸지 않는다. FK가 있으면 대상 행을 지울 때 감사 기록이 걸림돌이 되고, `ON DELETE SET NULL`을 붙이면 위와 같은 소급 손실이 생긴다. `actor_id`에만 FK를 두는데, 사용자는 이 앱에서 하드 삭제되지 않기 때문이다(상태만 `DISABLED`/`REJECTED`로 바뀐다).

### 2-2. append-only

`updated_at`·`updated_by`를 두지 않는다. 쿼리도 INSERT · SELECT · 보관기간 DELETE 세 종류만 만든다. UPDATE 경로를 아예 만들지 않는 것이 "기록은 고쳐지지 않는다"를 지키는 가장 단순한 방법이다.

### 2-3. 인덱스

| 인덱스 | 용도 |
|---|---|
| `(created_at DESC, id DESC)` | 목록 정렬 · 기간 필터 · 보관기간 DELETE |
| `(actor_id)` | 특정 사용자의 행위 추적 |
| `(action)` | 행위 종류 필터 |

`(target_type, target_id)` 인덱스는 지금 두지 않는다 — 그 조합으로 조회하는 화면이 없다(1절). 리소스별 이력을 만들 때 함께 추가한다.

### 2-4. 호출 API를 실제 경로로 저장하는 이유

`http_path`에는 경로 템플릿(`/api/projects/{id}/stages/{name}/run`)이 아니라 실제 경로(`/api/projects/12/stages/voice/run`)를 넣는다.

템플릿은 "어떤 종류의 API인가"만 알려주는데 그것은 `action` 열이 더 정확하게 말해준다. 실제 경로를 남겨야 같은 시각의 `studio.log`에서 그 경로를 찾아 요청 전후의 워커 로그·SQL 로그까지 이어볼 수 있다 — 감사 로그가 서버 로그로 넘어가는 다리 역할이다.

NULL을 허용하는 이유는 요청 밖에서 남길 사건을 위해서다. 실제로 둘이 있다 — 워커의 자동 승인(`STAGE_APPROVE`)과 정리 잡의 완전 삭제(`PROJECT_PURGE`). 두 경우 `http_method`·`http_path`·`actor_ip`가 NULL이고, `PROJECT_PURGE`는 `actor_id`·`actor_email`·`actor_name`까지 NULL이다(3-5).

## 3. 기록할 행위

`app/constants.py`에 `AuditAction` StrEnum을 추가한다. 아래 다섯 표를 합쳐 26종이고, 이 목록이 곧 화면 필터의 선택지다.

행위의 주체는 사람만이 아니다. **워커의 자동 승인과 정리 잡의 완전 삭제도 기록한다** — 감사 로그는 "기록이 없다 = 일어나지 않았다"가 성립해야 값어치가 있는데, 사람이 아닌 주체의 행위를 빼면 그 전제가 무너진다(3-5의 `STAGE_APPROVE`·`PROJECT_PURGE` 참고). 이 두 경우는 요청 밖에서 일어나므로 `http_*`·`actor_ip`가 NULL이다(2-4).

### 3-1. 인증 (`app/auth/router.py`)

| 코드 | 대상 | success | summary 예 |
|---|---|---|---|
| `REGISTER` | USER / 본인 | Y | `가입 신청 (승인 대기)` · `가입 (자동 승인)` |
| `LOGIN_SUCCESS` | — | Y | (없음) |
| `LOGIN_FAILURE` | — | **N** | `존재하지 않는 계정` · `비밀번호 불일치` · `잠긴 계정` · `승인 대기·비활성 계정` |
| `ACCOUNT_LOCKED` | USER / 본인 | N | `연속 로그인 실패 5회로 잠김` |
| `LOGOUT` | — | Y | (없음) |
| `PASSWORD_CHANGE` | USER / 본인 | Y | (없음) |
| `TOKEN_REUSE_DETECTED` | USER / 본인 | **N** | `폐기된 리프레시 토큰 재사용 — 전 세션 폐기` |

**`LOGIN_FAILURE`의 `actor_id`는 NULL일 수 있다.** 존재하지 않는 이메일로 시도한 경우다. 이때도 `actor_email`에는 **입력된 이메일 문자열 그대로**를 남긴다. 계정 열거 공격은 "없는 이메일 수백 건 시도"라는 모양으로 나타나므로, 그 문자열이 없으면 패턴 자체가 보이지 않는다.

**`ACCOUNT_LOCKED`는 잠기는 순간 한 번만 남긴다.** 잠긴 계정에 계속 시도하면 `LOGIN_FAILURE`만 쌓이고, `locked_at`이 새로 세팅되는 그 요청에서만 `ACCOUNT_LOCKED`가 함께 기록된다. [app/auth/router.py:143-148](../../../app/auth/router.py#L143-L148)이 이미 "이미 잠겼으면 잠금 시각을 유지한다"로 갈라져 있어 분기를 새로 만들 필요가 없다.

**`TOKEN_REUSE_DETECTED`는 사용자 조회가 한 번 늘어난다.** [app/auth/router.py:203-207](../../../app/auth/router.py#L203-L207)의 재사용 감지 분기는 `row["user_id"]`만 알고 이메일·이름을 모른다. 스냅샷을 채우려면 `find_by_id`를 부르는데, 이 경로는 정상 운영에서 사실상 발생하지 않는 보안 사건이므로 비용을 따질 자리가 아니다.

### 3-2. 사용자 관리 (`app/auth/admin_router.py`)

대상은 전부 `USER` / 대상 사용자 id / 대상 사용자 이름이다.

| 코드 | summary |
|---|---|
| `USER_APPROVE` | `가입 승인` |
| `USER_REJECT` | `가입 거절` |
| `USER_UNLOCK` | `계정 잠금 해제` |
| `USER_RESET_PASSWORD` | `비밀번호 초기화 — 전 세션 폐기` |
| `USER_RESET_FAILURES` | `로그인 실패 횟수 초기화` |

다섯 엔드포인트 모두 이미 `find_by_id`로 대상 행을 조회해 존재를 확인하므로([admin_router.py:81](../../../app/auth/admin_router.py#L81) 등), `target_label`에 넣을 이름을 얻는 데 추가 쿼리가 필요 없다.

### 3-3. 콘텐츠 (`app/api/admin_notices.py`, `app/api/admin_faqs.py`)

| 코드 | 대상 | target_label | summary |
|---|---|---|---|
| `NOTICE_CREATE` | NOTICE / id | 공지 제목 | `공지 등록 (게시)` · `공지 등록 (임시저장)` |
| `NOTICE_UPDATE` | NOTICE / id | **변경 전** 제목 | `공지 수정 (게시) → 새 제목` |
| `NOTICE_DELETE` | NOTICE / id | 공지 제목 | `공지 삭제` |
| `FAQ_CREATE` | FAQ / id | 질문 | `FAQ 등록 (게시)` 등 |
| `FAQ_UPDATE` | FAQ / id | **변경 전** 질문 | `FAQ 수정 → 새 질문` |
| `FAQ_DELETE` | FAQ / id | 질문 | `FAQ 삭제` |

**수정 기록의 `target_label`은 변경 전 값이다.** 관리자가 감사 로그를 여는 전형적인 이유가 "그 공지 제목을 누가 바꿨지"인데, 변경 후 값을 넣으면 기억하고 있는 옛 제목으로 검색해도 아무것도 나오지 않는다. 변경 후 값은 `summary` 뒤에 `→ 새 값`으로 붙여 검색 가능하게 한다 — 조회 API의 `q`가 `summary`도 훑으므로(5-3) 옛 값·새 값 어느 쪽으로 찾아도 같은 행이 걸린다. 두 엔드포인트 모두 404 검사를 위해 이미 변경 전 행을 읽고 있어 추가 쿼리가 없다.

### 3-4. 시스템 설정 (`app/api/admin_system.py`)

| 코드 | 대상 | summary |
|---|---|---|
| `SYSTEM_SETTINGS_UPDATE` | SYSTEM / NULL | `password_min_len 8 → 12, script_provider openai → claude` |

**여기만 값을 남긴다.** 1절에서 diff를 하지 않기로 했지만 시스템 설정은 세 가지 점에서 다르다. 첫째, 값 자체가 감사 대상이다 — "누가 비밀번호 최소 길이를 낮췄나"는 값 없이는 답할 수 없다. 둘째, `RuntimeSettings`의 필드는 전부 provider 이름·색상·숫자 한계값이라 **민감값이 하나도 없다**(API 키는 `.env`에만 있고 이 모델에 없다). 셋째, 화면이 폼 전체를 PUT하므로 실제로 바뀐 키만 골라내지 않으면 기록이 무의미하다 — 어차피 비교를 해야 한다.

200자를 넘으면 헬퍼가 자른다(4-3).

### 3-5. 프로젝트 (`app/api/projects.py`)

대상은 전부 `PROJECT` / 프로젝트 id / 프로젝트 제목이다.

| 코드 | summary |
|---|---|
| `PROJECT_CREATE` | `프로젝트 생성` |
| `PROJECT_DELETE` | `프로젝트 삭제 (30일 후 완전 삭제)` |
| `PROJECT_PURGE` | `보관 기간 경과로 완전 삭제` |
| `SCRIPT_UPDATE` | `대본 수정` |
| `STAGE_RUN` | `음성 단계 실행` |
| `STAGE_APPROVE` | `자막 단계 승인` · `자막 단계 자동 승인` |
| `STAGE_REGENERATE` | `영상 단계 재생성` |

**`STAGE_APPROVE`는 승인 경로 두 개를 모두 덮는다.** 사용자가 [승인]을 누르는 HTTP 경로([projects.py](../../../app/api/projects.py)의 `approve_stage`)와, `auto_run` 프로젝트에서 워커가 `pipeline.approve_stage`를 직접 부르는 경로([worker.py](../../../app/core/worker.py)의 `_chain_if_auto`) 둘 다다. 자동 승인을 빼면 `auto_run` 프로젝트는 4단계를 다 지나 `DONE`이 되어도 `STAGE_APPROVE`가 한 건도 남지 않아, 관리자에게 "아무도 승인하지 않았는데 완료된 프로젝트"로 보인다. 둘을 가르는 것은 summary 뒤의 "자동"이고, 워커 경로는 `request`가 없어 `http_*`·`actor_ip`가 NULL이며 `actor`는 프로젝트 소유자다(사용자 행을 한 번 조회해 스냅샷을 채운다 — 자동 승인은 단계당 한 번뿐이라 비용을 따질 자리가 아니다).

**`PROJECT_PURGE`는 정리 잡이 남긴다.** [cleanup.py](../../../app/core/cleanup.py)의 `_purge_project`가 행과 파일 트리를 **되돌릴 수 없게** 지우는 사건이고, 2-1·2-4가 이미 이 사건을 스냅샷 설계와 `http_path` NULL 허용의 근거로 쓰고 있다. 사람이 한 일이 아니므로 `actor`는 NULL이다. `target_label`(제목)은 행을 지운 뒤에는 읽을 수 없으므로 `list_purgeable_projects`가 `id`와 함께 미리 읽어 넘긴다. 기록은 행 삭제 직후·파일 삭제 앞에 둔다 — `record`는 커밋하지 않으므로 `_purge_project`의 마지막 커밋에 함께 실리고, "행 삭제 → 파일 삭제 → 커밋" 순서 규칙을 깨지 않는다.

**단계 행위의 대상도 `STAGE`가 아니라 `PROJECT`다.** 단계는 프로젝트에 종속된 행이고 단독으로 의미가 없다. 프로젝트를 대상으로 통일해야 "이 프로젝트에 무슨 일이 있었나"가 `target_id` 하나로 모이고, 단계 이름은 `summary`가 말해준다. `target_type`에 `STAGE`를 두지 않는 이유다.

### 3-6. 일부러 기록하지 않는 것

| 엔드포인트 | 이유 |
|---|---|
| `POST /api/notices/{id}/read` | 공지 읽음 표시. 사용자가 목록을 열 때마다 발생해 다른 모든 행위의 합을 넘긴다. 감사 가치는 없고 화면만 못 읽게 만든다 |
| `POST /api/auth/refresh` | 토큰 자동 갱신. 같은 이유다. **단 그 안의 재사용 감지는 `TOKEN_REUSE_DETECTED`로 반드시 남긴다** |

두 경로는 `tests/test_audit_coverage.py`의 `_EXEMPT` 집합에 명시한다(9절). 빠뜨린 것이 아니라 결정한 것임을 코드에 남긴다.

HTTP 엔드포인트가 아닌 사건 중에도 일부러 기록하지 않는 것이 있다. 커버리지 테스트가 잡아주지 못하는 영역이라 여기 적어둔다.

| 사건 | 이유 |
|---|---|
| 워커의 단계 실행 성공/실패 (`run_one` / `run_claimed_stage`) | 사용자 행위가 아니라 그 행위의 **결과**다. 시작점인 `STAGE_RUN`이 이미 남고, 결과는 `stages.status`·`stages.error`가 권위 있는 값으로 들고 있으며 실패는 `studio.log`의 `logger.exception`이 스택까지 남긴다. 기록하면 진행률·재시도까지 딸려와 건수가 사용자 행위를 덮는다 |
| `StageWorker._recover()`의 기동 시 FAILED 처리 | 재시작마다 발생하는 운영 잡음이고 주체가 "프로세스 재시작"이라 행위자가 없다. `logger.info("기동 복구: …")`가 이미 남는다 |
| `_purge_old_audit_logs`(감사 로그 자체의 삭제) | **자기참조**다. 감사 로그를 지운 사실을 감사 로그에 남기면 매 주기 한 건씩 영구히 늘어나고, 그 행은 90일 뒤 다시 지워지며 또 한 건을 만든다. 대신 삭제 건수를 `logger.info`로 남긴다(프로젝트 완전 삭제 쪽과 같은 형식) |

## 4. 기록 헬퍼

`app/core/audit.py`.

### 4-1. 두 함수

```python
async def record(
    conn,
    *,
    action: AuditAction,
    request: Request | None = None,
    actor: dict | None = None,
    actor_email: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    target_label: str | None = None,
    success: bool = True,
    summary: str | None = None,
) -> None:
    """현재 트랜잭션에 감사 행을 넣는다. 원 작업과 함께 커밋되고 함께 롤백된다."""


async def record_failure(db: AsyncSession, **kwargs) -> None:
    """감사 행을 넣고 즉시 커밋한다. 예외를 던지며 끝나는 경로 전용."""
```

`record`는 엔드포인트가 이미 들고 있는 `conn`(= `raw_connection(db)`)을 그대로 받는다. 같은 트랜잭션이므로 **작업이 롤백되면 기록도 사라진다.** 이것이 기본형이고 옳은 기본값이다 — 일어나지 않은 일은 기록되지 않아야 한다.

`actor`에는 `current_user`/`require_admin`이 준 dict를 그대로 넘긴다. 헬퍼가 `id`·`email`·`name`을 꺼내 스냅샷 열에 채운다. `actor_email`을 따로 받는 이유는 로그인 실패 하나뿐이다 — 계정이 없어 dict가 없고 입력 문자열만 있다.

`request`를 받으면 `request.method`·`request.url.path`·`request.client.host`를 자동으로 채운다. **호출부는 이 세 값을 신경 쓰지 않는다.**

### 4-2. `record_failure`가 따로 필요한 이유

[app/db.py:51-53](../../../app/db.py#L51-L53)의 `get_db`는 세션을 닫기만 하고 커밋하지 않는다. 그래서 예외로 끝나는 경로에서 `record`만 부르면 **감사 행이 조용히 사라진다.** 하필 기록이 가장 중요한 실패 사건에서만 그렇게 된다.

로그인 엔드포인트가 이 문제를 그대로 보여준다.

| 경로 | 기존 커밋 | 사용할 함수 |
|---|---|---|
| 없는 이메일 → 401 ([router.py:137](../../../app/auth/router.py#L137)) | **없음** | `record_failure` |
| 비밀번호 불일치 → 401 ([router.py:152](../../../app/auth/router.py#L152)) | 있음 | `record` |
| 잠긴 계정 → 423 ([router.py:158](../../../app/auth/router.py#L158)) | **없음** | `record_failure` |
| 미승인·비활성 → 403 ([router.py:160](../../../app/auth/router.py#L160)) | **없음** | `record_failure` |

같은 파일 안에서 네 갈래가 서로 다르다. 함수를 하나만 두고 "커밋 여부는 호출부가 알아서"로 하면 이 표를 매번 머릿속에서 다시 그려야 하고, 틀려도 테스트가 커밋까지 확인하지 않으면 통과한다. 함수를 둘로 나눠 **위험에 이름을 붙인다.**

`record_failure`가 커밋하는 시점에 아직 커밋되지 않은 다른 변경이 함께 커밋될 수 있다. 위 세 경로에는 그런 변경이 없다(전부 조회만 한 상태다). 새로운 호출부를 추가할 때 이 점을 확인해야 한다.

### 4-3. 길이 초과는 헬퍼가 자른다

`summary`는 200자, `target_label`·`actor_email`·`actor_name`은 각 컬럼 길이에 맞춰 헬퍼가 잘라 넣는다.

**감사 INSERT를 `try/except`로 감싸 삼키지 않는다.** 삼키면 "기록이 없다"와 "행위가 없었다"를 구분할 수 없게 되어 감사 로그의 전제가 무너진다. 대신 실패할 수 있는 원인을 미리 없앤다 — 현실적으로 INSERT를 깨뜨리는 것은 값 길이뿐이고, 그것을 헬퍼가 처리한다. 그러고도 실패한다면 DB 장애이고 그 상황에선 원 작업도 어차피 실패한다.

**미인증 경로가 감사 테이블을 키울 수 있다는 점은 알고 수용한다.** 위 근거는 "DB 장애는 외생적"을 전제하는데, 한 시나리오에서는 그렇지 않다. 이 기능 이전에 존재하지 않는 이메일로 로그인을 시도하면 DB 작업은 `find_by_email` SELECT 하나였다. 지금은 `record_failure`가 INSERT + 커밋을 더한다. 이 앱에는 rate limiting이 없고 보관 기간은 90일이므로, 지속적인 계정 열거 시도는 감사 테이블을 키운다 — 극단적으로 테이블스페이스가 차면 감사 INSERT가 실패하고, 위 방침대로 삼키지 않으므로 **모든 쓰기 엔드포인트가 500이 된다.** 즉 이 경우에는 감사 로깅 자체가 장애의 원인이다.

그럼에도 지금은 코드를 바꾸지 않는다. 이 앱은 단독 배포 사내 도구이고, 존재하지 않는 계정 경로도 타이밍 노출을 막기 위해 Argon2 더미 해시를 계산하므로 시도 스루풋이 그 비용에 묶인다. 90일 보관이 상한을 씌운다. 문제가 실제로 관측되면 순서대로 대응한다 — (1) `LOGIN_FAILURE` 중 `actor_id IS NULL`인 행(= 없는 계정)에만 짧은 보관 기간을 적용하는 DELETE를 `_purge_old_audit_logs`에 한 줄 더한다(열거 패턴 탐지에 90일이 필요하지 않다), (2) `/api/auth/login`에 IP 기준 rate limiting을 넣는다(별도 과제다).

### 4-4. 쿼리

`app/queries/audit_logs.sql` (신규).

```sql
-- name: insert_audit_log<!
INSERT INTO audit_logs (action, actor_id, actor_email, actor_name, actor_ip,
                        target_type, target_id, target_label,
                        http_method, http_path, success_yn, summary, created_at)
VALUES (:action, :actor_id, :actor_email, :actor_name, :actor_ip,
        :target_type, :target_id, :target_label,
        :http_method, :http_path, :success_yn, :summary, :created_at)
RETURNING id;
```

## 5. 조회 API

`app/api/admin_audit_logs.py` (신규). `router = APIRouter(prefix="/admin/audit-logs", tags=["admin"])`, 전 엔드포인트 `require_admin`. `app/main.py`에 `prefix="/api"`로 등록한다.

| 메서드 | 경로 | 동작 |
|---|---|---|
| GET | `/api/admin/audit-logs` | 목록 (필터 + 페이지네이션) |

**쿼리 파라미터**

| 이름 | 기본값 | 설명 |
|---|---|---|
| `from` | 오늘 - 7일 | 시작 날짜 (`YYYY-MM-DD`, 그날 00:00:00 포함) |
| `to` | 오늘 | 종료 날짜 (그날 23:59:59.999999까지 포함) |
| `action` | 없음 | 행위 코드 하나 |
| `success` | 없음 | `Y` \| `N` |
| `q` | 없음 | 검색어 |
| `page` | 1 | 1부터 |
| `size` | 50 | 최대 200 |

`from`은 파이썬 예약어라 함수 인자 이름으로 쓸 수 없다. 핸들러에서는 `from_date: date = Query(None, alias="from")`으로 받는다 — 화면·URL에 노출되는 이름은 `from`이어야 `to`와 짝이 맞는다.

**응답**

```json
{ "items": [ { "id": 1, "action": "PROJECT_DELETE", "...": "..." } ],
  "total": 1234, "page": 1, "size": 50 }
```

### 5-1. 서버에서 필터·페이지네이션한다

[admin_notices.py:63](../../../app/api/admin_notices.py#L63)의 "전량 내려주고 프론트가 거른다" 방침을 여기서는 따르지 않는다. 그 방침은 공지 수십 건이라 성립하는 것이고, 감사 로그는 90일치 × 모든 사용자 쓰기라 수만~수십만 행이 된다. 같은 방침이면 화면을 열 때마다 그 전부가 JSON으로 나간다.

`total`을 함께 주는 이유는 `seqColumn(total, page, pageSize)`가 전체 건수를 요구하기 때문이다([seqColumn.ts:13](../../../web/src/components/table/seqColumn.ts#L13)).

### 5-2. 기본 기간이 7일인 이유

화면을 열자마자 90일 전체에 `COUNT(*)`가 도는 것을 막는다. 필터 없는 전체 조회를 기본 화면으로 두면 데이터가 쌓일수록 화면이 느려지고, 그때 고치려면 이미 관리자가 그 동작에 익숙해진 뒤다.

### 5-3. `q`는 네 열을 훑는다

`actor_email` · `actor_name` · `target_label` · `summary`를 `ILIKE '%' || :q || '%'`로 검사한다. 관리자가 "그 프로젝트 누가 지웠지"를 찾을 때 검색어가 어느 열에 있는지 미리 알 수 없다. 열을 골라 검색하게 만들면 그 선택 자체가 실패 원인이 된다.

### 5-4. 행위 종류 목록 엔드포인트는 만들지 않는다

프론트가 `AUDIT_ACTION_LABEL` 맵의 키로 셀렉트를 그린다. 백엔드 Enum에 항목을 추가하면 라벨 맵에도 추가해야 화면에 나타나므로, **라벨 없는 코드값이 화면에 노출되는 일이 구조적으로 없다.** 엔드포인트로 내려주면 반대가 된다 — 라벨을 잊은 새 코드값이 그대로 관리자 화면에 뜬다.

### 5-5. 쿼리

`app/queries/audit_logs.sql`에 목록과 건수를 나란히 둔다. 두 쿼리의 WHERE 절이 **글자 그대로 같아야 한다** — 어긋나면 페이지 수가 실제 결과와 맞지 않는다.

```sql
-- name: list_audit_logs
SELECT id, action, actor_id, actor_email, actor_name, actor_ip,
       target_type, target_id, target_label,
       http_method, http_path, success_yn, summary, created_at
FROM audit_logs
WHERE created_at >= :from_at
  AND created_at <= :to_at
  AND (:action IS NULL OR action = :action)
  AND (:success_yn IS NULL OR success_yn = :success_yn)
  AND (:q IS NULL OR actor_email ILIKE :like OR actor_name ILIKE :like
       OR target_label ILIKE :like OR summary ILIKE :like)
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;

-- name: count_audit_logs^
SELECT COUNT(*) AS n FROM audit_logs
WHERE ...;   -- 위와 동일
```

`ORDER BY created_at DESC, id DESC`는 인덱스와 같은 순서다. `id`를 두 번째 키로 두는 이유는 같은 초에 여러 건이 들어올 때 순서가 흔들려 페이지 경계에서 행이 중복·누락되는 것을 막기 위해서다.

## 6. 프론트엔드

### 6-1. 화면

`web/src/pages/admin/AdminAuditLogs.tsx` (신규), 경로 `/admin/logs`.

`web/src/lib/nav.ts`의 `NAV`에 `{ path: '/admin/logs', label: '활동 기록', icon: '🧾', adminOnly: true }`를 시스템 설정 앞에 추가하고, `web/src/App.tsx`에 라우트를 더한다.

```
┌──────────────────────────────────────────────────────────────────────┐
│ [기간: 2026-07-23] ~ [2026-07-30]  [행위 ▾] [결과 ▾] [검색어____] 🔍 │
├────┬────────────┬──────────┬────────────┬─────────┬──────┬──────────┤
│ No │ 시각       │ 행위     │ 행위자     │ 대상    │ 결과 │ 설명     │
├────┼────────────┼──────────┼────────────┼─────────┼──────┼──────────┤
│ 87 │ 07-30 14:2 │ 프로젝트 │ 홍길동     │ 여행 브 │ 성공 │ 프로젝트 │
│    │ 2:10       │ 삭제     │ hong@…     │ 이로그  │      │ 삭제 (30…│
│ 86 │ 07-30 14:1 │ 로그인   │ —          │ —       │ 실패 │ 존재하지 │
│    │ 9:03       │ 실패     │ bad@x.com  │         │      │ 않는 계정│
├────┴────────────┴──────────┴────────────┴─────────┴──────┴──────────┤
│                          << 1 / 25 >>                     총 1,234건 │
└──────────────────────────────────────────────────────────────────────┘
```

기존 `Table` · `Pagination` · `TableFooter` · `seqColumn`을 그대로 쓴다. 호출 API(`http_method` + `http_path`)는 열로 두지 않고 **행 확장이 아니라 `title` 속성(툴팁)** 으로 붙인다 — 표의 가로 폭은 이미 빠듯하고, 이 값은 "이상한 기록을 발견했을 때 확인하는" 이차 정보다.

행위자 열은 이름과 이메일을 두 줄로 보여준다. 이름이 없는 경우(없는 계정으로 로그인 시도)는 이메일만 나온다.

### 6-2. 필터는 URL 쿼리스트링에 둔다

`AdminUsers`가 이미 그렇게 하고 있고(커밋 `860dbb5`), 감사 로그는 "이 조건으로 본 화면"을 링크로 넘기는 일이 실제로 생긴다. 새로고침해도 조건이 유지되어야 한다는 점도 같다.

### 6-3. API 클라이언트

`web/src/lib/auditLogs.ts` (신규).

```ts
export const AUDIT_ACTION_LABEL: Record<string, string> = {
  LOGIN_SUCCESS: '로그인',
  LOGIN_FAILURE: '로그인 실패',
  // ... 26종 (3절의 표 전부)
}

export const auditLogs = {
  list: (params: AuditLogQuery) => api.get<AuditLogPage>(`/admin/audit-logs?${qs}`),
}
```

라벨 맵은 `FAQ_CATEGORY_LABEL`([faqs.ts:7](../../../web/src/lib/faqs.ts#L7))과 같은 패턴이다.

## 7. 보관과 정리

[app/core/cleanup.py](../../../app/core/cleanup.py)에 `AUDIT_RETENTION_DAYS = 90`을 `PROJECT_RETENTION_DAYS` 옆에 두고, `run_once()`에 한 단계를 더한다.

```python
async def _purge_old_audit_logs(session) -> None:
    conn = await raw_connection(session)
    before = now_local() - timedelta(days=AUDIT_RETENTION_DAYS)
    await queries.delete_old_audit_logs(conn, before=before)
    await session.commit()
```

```sql
-- name: delete_old_audit_logs!
DELETE FROM audit_logs WHERE created_at < :before;
```

이미 24시간 주기로 돌고 기동 직후에도 한 번 도는 잡이므로 새 스케줄러가 필요 없다. 멱등한 DELETE라 동시 인스턴스도 문제가 없다([cleanup.py:99-101](../../../app/core/cleanup.py#L99-L101)의 전제 그대로다).

보관 기간을 **소스 상수로 두는 이유**는 `PROJECT_RETENTION_DAYS`와 같다([cleanup.py:17-19](../../../app/core/cleanup.py#L17-L19)) — `.env`로 빼면 `check_env_defaults`의 범위 검증까지 붙어야 하고, 관리자가 이 값을 바꿀 이유가 아직 없다. 시스템 설정 화면에 올리는 것은 그때 가서 판단한다.

만료 토큰 정리보다 **뒤에**, 프로젝트 완전 삭제보다 **앞에** 부른다. 프로젝트 완전 삭제는 한 건씩 실패할 수 있는데, 그 실패가 감사 로그 정리를 막지 않게 각자 자기 세션에서 돈다.

삭제 건수는 `logger.info`로 남긴다(프로젝트 완전 삭제 쪽과 같은 형식). 이 단계 자체는 감사 로그에 남기지 않는다 — 3-6의 자기참조 항목 참고.

## 8. 에러 처리

**기록 쪽**

| 상황 | 처리 |
|---|---|
| 원 작업이 롤백됨 | 감사 행도 함께 롤백 (설계된 동작) |
| 값이 컬럼 길이 초과 | 헬퍼가 자른다 (4-3) |
| INSERT 실패 (DB 장애) | 예외를 그대로 올린다 — 원 작업도 실패한다 |

**조회 쪽**

| 상황 | 응답 |
|---|---|
| 비로그인 | 401 |
| 관리자가 아님 | 403 (`require_admin`) |
| `size > 200` · `page < 1` · 날짜 형식 오류 | 422 (FastAPI 검증) |
| `from` > `to` | 422 `VALIDATION_ERROR`, 메시지 `종료 날짜는 시작 날짜보다 뒤여야 합니다.` |
| 조건에 맞는 기록 없음 | 200, `items: []`, `total: 0` |

`from` > `to`를 422로 막는 것은 `_resolve_period`([admin_notices.py:44](../../../app/api/admin_notices.py#L44))가 기간 역전을 거부하는 것과 같은 판단이다. 빈 목록으로 돌려주면 "기록이 없다"와 "조건이 잘못됐다"를 구분할 수 없다.

## 9. 테스트

**`tests/test_core_audit.py`** (신규) — 헬퍼 단위

- `record`가 모든 열을 채운다 (`actor` dict → id·email·name 스냅샷)
- `request`를 주면 `http_method`·`http_path`·`actor_ip`가 채워진다
- `request`가 없으면 그 세 열이 NULL이다
- `actor`가 없고 `actor_email`만 있으면 `actor_id`는 NULL, 이메일은 저장된다
- 200자를 넘는 `summary`가 잘려서 저장된다
- `success=False`가 `success_yn='N'`으로 저장된다
- `record` 후 `db.rollback()` → 행이 사라진다 (같은 트랜잭션임을 고정)
- `record_failure` 후 `db.rollback()` → **행이 남는다** (실제로 커밋했음을 고정)

**커밋 여부는 롤백으로 판별한다 — 별도 세션으로는 확인할 수 없다.** `tests/conftest.py`의 `db_session`은 바깥 트랜잭션 위의 SAVEPOINT이고 `client` 픽스처가 같은 세션을 주입하므로([conftest.py:52-79](../../../tests/conftest.py#L52-L79)), 별도 세션에서는 커밋된 행도 보이지 않는다. 반대로 같은 세션에서는 커밋하지 않은 행도 보인다. 두 경우를 가르는 것은 **롤백 뒤에도 살아남는지** 하나뿐이다. `db.commit()`이 SAVEPOINT를 RELEASE하므로 그 뒤의 `rollback()`은 이미 반영된 행을 되돌리지 못한다.

**반대로 "기록이 없어야 한다"를 보는 테스트에는 `rollback()`을 쓰면 안 된다.** 그 호출이 증거를 스스로 지워 구현이 어떻든 통과하게 만든다. 미커밋 행까지 보이는 그 세션에서 그대로 세는 것이 맞다.

**남아 있는 한계.** 이 하네스는 "커밋 뒤 반납된 `conn`을 그대로 재사용하는" 회귀를 잡지 못한다. 테스트에서는 커밋이 커넥션을 풀에 반납하지 않으므로, 기록을 커밋 뒤로 옮기면서 `raw_connection()`을 다시 부르지 **않으면** 그 INSERT가 바깥 트랜잭션에 실려 `rollback()`을 넘겨 살아남는다(운영에서는 깨진다). 실제 풀링 엔진에 붙는 통합 테스트 계층이 생기기 전까지는 코드 주석이 그 규칙을 지킨다.

**`tests/test_api_audit_logs.py`** (신규) — 조회 API

- 기본 조회가 최근 7일만 돌려준다 (8일 전 기록은 빠진다)
- `from`·`to`로 기간을 넓히면 그 기록이 들어온다
- `action` 필터가 그 행위만 남긴다
- `success=N` 필터가 실패 기록만 남긴다
- `q`가 `actor_email`·`actor_name`·`target_label`·`summary` 각각에서 걸린다 (4케이스)
- 페이지네이션: `total`이 필터 적용 후 전체 건수고, `size`만큼만 돌아오며, 2페이지가 1페이지와 겹치지 않는다
- 정렬이 최신순이다
- `size=201`은 422
- `from` > `to`는 422
- 일반 사용자는 403, 비로그인은 401

**`tests/test_audit_coverage.py`** (신규) — 누락 방지

OpenAPI 스키마를 훑어 POST/PUT/PATCH/DELETE의 **`(메서드, 경로)` 쌍**을 모으고, 각 쌍이 `_AUDITED` 또는 `_EXEMPT` 집합에 있는지 확인한다. 없으면 그 메서드와 경로를 함께 찍으며 실패한다.

**단위가 경로가 아니라 쌍이어야 하는 이유**가 있다. 경로만 보면 이미 목록에 있는 경로에 메서드를 하나 더하는 변경이 조용히 통과한다 — 예를 들어 제목 수정용 `PATCH /api/projects/{project_id}`를 추가해도 그 경로는 `DELETE` 때문에 이미 `_AUDITED`에 있어 테스트가 초록색이다. 그런 변경(프로젝트 제목 변경)은 하필 `target_label` 스냅샷 설계(2-1)가 정확히 대비하는 종류의 사건이다. 현재 24쌍이 22개 경로에 들어 있다(`/api/admin/notices/{notice_id}`와 `/api/admin/faqs/{faq_id}`가 각각 PATCH+DELETE 둘씩).

이것이 접근 방식(엔드포인트에서 헬퍼를 직접 호출)의 유일한 약점을 막는다. 새 변경 엔드포인트를 추가하고 감사를 잊으면 테스트가 **어느 메서드·경로인지 찍으며** 실패한다. 기록을 강요하는 것이 아니라 **어느 쪽 집합에 넣을지 결정하도록 강요**하는 것이다 — 3-6의 두 제외 항목처럼 "안 남기기로 했다"도 정당한 답이다.

**한계 두 가지.** `include_in_schema=False`로 등록된 라우트는 OpenAPI에 들어가지 않아 이 방식으로 보이지 않는다(현재 0건이며, `_get_write_endpoints`의 독스트링에 적어두었다). 그리고 이 테스트는 HTTP 라우트만 본다 — 워커의 자동 승인이나 정리 잡의 완전 삭제처럼 요청 밖에서 일어나는 행위는 구조적으로 잡지 못하므로 3절 표와 3-6이 그 자리를 대신한다.

**기존 테스트 파일에 추가**

| 파일 | 추가할 검증 |
|---|---|
| `test_auth_login.py` | 로그인 성공 → `LOGIN_SUCCESS`. 없는 이메일 → `LOGIN_FAILURE`(`actor_id` NULL, 입력 이메일 저장). 비밀번호 불일치 → `LOGIN_FAILURE`. **401 응답 후 `db_session.rollback()`을 하고도 기록이 남는지 확인** (실제 커밋 여부) |
| `test_account_lockout.py` | 임계치 도달 요청에 `ACCOUNT_LOCKED`가 함께 남고, 그 뒤 시도에는 `LOGIN_FAILURE`만 쌓인다 |
| `test_auth_refresh_logout.py` | 로그아웃 → `LOGOUT`. 폐기 토큰 재사용 → `TOKEN_REUSE_DETECTED`. **정상 갱신에는 아무 기록도 남지 않는다** |
| `test_auth_register.py` | `REGISTER`가 남고 승인 방식이 summary에 반영된다 |
| `test_auth_change_password.py` | `PASSWORD_CHANGE` |
| `test_admin_users.py` | 승인·거절·잠금해제·실패초기화 4종, `target_label`에 대상 이름이 들어간다 |
| `test_admin_reset_password.py` | `USER_RESET_PASSWORD` |
| `test_admin_notices.py` · `test_admin_faqs.py` | 생성·수정·삭제 각 3종 |
| `test_admin_system.py` | `SYSTEM_SETTINGS_UPDATE`의 summary에 **바뀐 키만** 들어간다 (안 바뀐 키는 없다) |
| `test_api_projects.py` | `PROJECT_CREATE`, `STAGE_RUN`, `STAGE_APPROVE`, `STAGE_REGENERATE` |
| `test_api_project_delete.py` | `PROJECT_DELETE`. **409로 거절된 삭제에는 기록이 남지 않는다** |
| `test_api_script_edit.py` | `SCRIPT_UPDATE` |
| `test_notices.py` | 읽음 표시에는 기록이 남지 않는다 |
| `test_core_cleanup.py` | 90일 지난 기록은 지워지고 89일짜리는 남는다. 다른 정리 단계가 실패해도 감사 정리는 수행된다. **완전 삭제가 `PROJECT_PURGE`로 남고 실제로 커밋된다**(제목·행위자 NULL 포함). 보관 기간 안의 프로젝트에는 기록이 없다 |
| `test_core_worker.py` | **워커의 자동 승인이 `STAGE_APPROVE`로 남고 실제로 커밋된다.** 마지막(render) 단계 분기를 별도로 고정한다 — 중간 단계는 `_chain_if_auto`가 다음 단계를 큐에 올리며 한 번 더 커밋하므로 기록이 잘못된 자리에 있어도 얹혀 살아남지만, 마지막 단계는 뒤에 커밋이 없어 위치 오류가 그대로 드러난다. 수동 모드에는 기록이 남지 않는다 |

`tests/test_alembic_migration.py`는 새 리비전을 자동으로 포함한다.

**프론트엔드**는 이 프로젝트에 자동화 테스트가 없다. 수동 확인 항목만 남긴다.

- 관리자 사이드바에 "활동 기록"이 뜨고, 일반 사용자에게는 안 보인다
- 일반 사용자가 `/admin/logs`에 직접 접근하면 막힌다
- 기본 화면이 최근 7일을 보여준다
- 기간·행위·결과·검색어 필터가 각각 동작하고 URL에 반영된다
- 필터가 걸린 URL을 새 탭에서 열면 같은 화면이 나온다
- 페이지를 넘겨도 No가 이어진다
- 로그인 실패 행이 실패 배지로 구분된다
- 행에 마우스를 올리면 호출 API가 툴팁으로 보인다
- 결과가 없으면 빈 상태 문구가 나온다
- 다크모드에서 표·배지·필터가 깨지지 않는다

## 10. 구현 순서

1. `AuditAction` Enum + `AuditLog` 모델 + Alembic 리비전 + `docs/schema.sql`
2. `app/queries/audit_logs.sql`의 INSERT + `app/core/audit.py` + `tests/test_core_audit.py`
3. **인증 경로 기록** (`auth/router.py`) + 해당 테스트 — `record_failure`가 실제로 커밋하는지 여기서 확정된다
4. 나머지 기록 지점 (사용자 관리 → 콘텐츠 → 시스템 설정 → 프로젝트) + 각 기존 테스트 보강
5. `tests/test_audit_coverage.py` — 4번이 끝난 뒤에 넣어야 통과 상태에서 시작한다
6. 조회 쿼리 2개 + `GET /api/admin/audit-logs` + `tests/test_api_audit_logs.py`
7. 정리 잡에 90일 삭제 추가 + `test_core_cleanup.py` 보강
8. 프론트: `lib/auditLogs.ts` → `AdminAuditLogs.tsx` → 라우트·네비

**3번을 4번보다 먼저 하는 이유**: 인증 경로가 트랜잭션 규칙(4-2)이 실제로 걸리는 유일한 곳이다. 여기를 먼저 끝내면 나머지 기록 지점은 전부 `record` 한 줄이라 기계적으로 진행된다. 반대로 쉬운 것부터 하면 규칙이 검증되지 않은 채 20곳에 퍼진다.

**5번을 4번 뒤에 두는 이유**: 커버리지 테스트를 먼저 넣으면 4번을 진행하는 내내 빨간 상태로 남아, 그 실패가 "아직 안 한 것"인지 "잘못한 것"인지 구분되지 않는다.

**7번을 프론트보다 먼저**: 90일 삭제는 화면과 무관하지만, 기록이 무한정 쌓이는 상태로 화면을 먼저 만들면 보관 정책이 "나중에"로 밀린다.
