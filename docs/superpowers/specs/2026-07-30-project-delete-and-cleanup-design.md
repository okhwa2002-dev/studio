# 프로젝트 삭제와 정리 잡 설계

- 작성일: 2026-07-30
- 범위: 프로젝트 소프트 삭제 · 보관 기간 후 자동 완전 삭제 · 만료 refresh token 정리

## 1. 목적과 범위

지금은 프로젝트를 지울 방법이 없다. `projects.sql`에 삭제 쿼리가 없고 화면에도 버튼이 없다. 실패한 프로젝트도 목록에 영구히 남고, `storage/projects/{id}` 아래의 음성·자막·영상·스톡 소재가 **회수되지 않고 계속 쌓인다.**

`refresh_tokens`도 같은 문제다. 로그인·리프레시마다 행이 늘고 폐기·만료된 행을 지우는 경로가 없다. 현재 로컬 DB는 81행 중 74행이 폐기, 19행이 만료 상태다.

두 문제를 한 스펙으로 묶는 이유: 둘 다 "수명주기가 끝난 데이터를 지운다"는 같은 일이고, **주기 작업 인프라를 공유한다.** 이 프로젝트에는 스케줄러가 없어서 그 인프라를 만드는 것이 작업의 절반이다. 두 번 만들 이유가 없다.

**하는 것**

- 사용자가 자기 프로젝트를 삭제 (소프트 삭제 — 즉시 화면에서 사라진다)
- 30일이 지난 삭제 프로젝트를 정리 잡이 완전 삭제 (행 + 파일)
- 만료된 refresh token을 정리 잡이 삭제

**하지 않는 것**

- **복원 UI** — 30일 안에는 되돌릴 수 있는 상태지만, 화면을 만들면 "삭제함" 목록·복원 버튼·그 상태의 표시·목록 필터까지 딸려온다. 실수로 지운 경우는 그 기간 안에 `deleted_at`을 비우면 되고, 실제 요청이 생기면 그때 만든다
- **제목·주제 수정** — 별개 기능이다. 수명주기와 무관하다
- **관리자의 타인 프로젝트 삭제** (2-4)
- **목록 페이지네이션** — 같은 감사에서 나온 항목이지만 API 3개 + 화면 3개의 검색·필터를 서버로 옮기는 별도 작업이다
- **고아 파일 청소** — DB에 없는데 디스크에만 있는 파일을 찾아 지우는 일. 아래 삭제 순서(2-3)가 그 상황 자체를 만들지 않으므로 필요 없다

## 2. 프로젝트 삭제

### 2-1. 스키마

`projects`에 두 컬럼을 더한다. 공지·FAQ의 소프트 삭제와 같은 모양이다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `deleted_at` | TIMESTAMP NULL | 소프트 삭제 일시 (NULL = 미삭제) |
| `deleted_by` | BIGINT NULL → `users.id` | 삭제한 사용자 |

`app/models/project.py`에서 업무 컬럼 맨 아래, 감사 컬럼 앞에 선언한다(`id` → 업무 → 감사 순서 규칙). `app/models/notice.py`의 같은 두 컬럼과 같은 모양으로 쓴다.

`server_default`는 두지 않는다 — NULL이 기본이고, `insert_project`가 이 컬럼을 넘기지 않아도 NULL이 들어간다.

### 2-2. API

| 메서드 | 경로 | 동작 |
|---|---|---|
| DELETE | `/api/projects/{id}` | 소프트 삭제. 응답 `{"id", "deleted_at"}` |

응답 형태는 `admin_notices`·`admin_faqs`의 삭제와 같게 맞춘다.

처리 순서:

1. `_load_owned_project` — 소유자가 아니거나 없으면 404
2. 진행 중인 단계가 있으면 409 (2-5)
3. `soft_delete_project` 실행 후 commit

### 2-3. 조회에서 제외

다음 6개 쿼리에 `deleted_at IS NULL`을 추가한다.

| 쿼리 | 쓰는 곳 |
|---|---|
| `find_project_by_id` | 상세 · SSE · 에셋 · **워커** |
| `list_projects_by_owner` | 내 프로젝트 목록 |
| `list_all_projects` | 관리자 전체 프로젝트 |
| `count_projects_by_status_for_owner` | 대시보드 내 집계 |
| `list_owner_attention_projects` | 대시보드 "조치 필요" |
| `count_projects_by_status` | 대시보드 관리자 집계 |

**`find_project_by_id`에 넣는 것이 핵심이다.** 상세·SSE·에셋이 전부 404가 되고, 워커도 같은 쿼리를 쓰므로 삭제된 프로젝트의 단계를 자연히 포기한다 — `app/core/worker.py`의 `run_one`에는 이미 "중간에 프로젝트가 지워졌다 → 조용히 버린다" 분기가 두 곳 있어서 새 코드가 필요 없다. 2-5에서 진행 중 삭제를 막으므로 이 경로는 경합일 때만 타지만, 그때도 올바르게 동작한다.

정리 잡은 삭제된 프로젝트를 찾아야 하므로 이 쿼리를 쓰지 않고 전용 쿼리(`list_purgeable_projects`)를 쓴다.

이미 열려 있는 SSE 스트림은 끊지 않는다. 삭제 후에는 이벤트가 오지 않고 ping만 계속되며, 화면은 삭제를 실행한 직후 목록으로 이동하므로 브라우저가 `EventSource`를 닫는다. 남의 열린 스트림(관리자 열람 등)은 새로고침 시 404로 정리된다 — 스트림을 강제로 닫는 장치를 넣을 만큼의 문제가 아니다.

### 2-4. 삭제 권한은 소유자뿐

관리자는 다른 사람의 프로젝트를 지울 수 없다. 관리자 프로젝트 화면은 이미 읽기 전용(`/admin/projects/:id`는 `ProjectDetail readOnly`)이고, 실행·승인·재생성도 전부 `_load_owned_project`로 소유자만 통과한다. 삭제만 예외로 두면 "관리자는 프로젝트를 볼 수만 있다"는 경계가 무너진다.

관리자가 남의 프로젝트를 정리해야 하는 상황(퇴사자 계정 등)은 아직 요구가 없고, 생기면 그때 별도 관리자 기능으로 만드는 편이 낫다 — 소유자용 삭제 버튼에 관리자 예외를 끼워 넣는 것보다 의도가 분명하다.

### 2-5. 진행 중인 단계가 있으면 409

`stages`에 `RUNNING` 또는 `QUEUED`인 행이 있으면 삭제를 거절한다.

```
AppError(409, "PROJECT_BUSY", "실행 중인 단계가 있어 삭제할 수 없습니다. 완료된 뒤 다시 시도해 주세요.")
```

파일 경합은 이유가 아니다 — 소프트 삭제는 파일을 건드리지 않고, 정리 잡은 30일 뒤에 돈다. 실제 이유는 두 가지다.

첫째, **사용자가 몇 분씩 걸리는 작업을 돌리는 중에 삭제를 누르는 것은 대개 실수다.** 조용히 진행 중 작업을 버리는 대신 "끝난 뒤에 하세요"라고 알려주는 편이 낫다.

둘째, 어중간한 상태가 남는다. `QUEUED` 단계는 워커의 `run_one`이 맨 처음 `find_project_by_id`로 프로젝트를 확인하고 `None`이면 조용히 버리므로, **영구히 `QUEUED`로 남는다**(앱을 재시작하면 `_recover`가 다시 큐에 넣지만 프로젝트가 여전히 삭제 상태라 또 버려진다). 화면에 안 보이니 해는 없지만, 30일 안에 `deleted_at`을 비워 되돌렸을 때 그 단계가 재시작 전까지 멈춰 있는 원인이 된다. 삭제를 막으면 이 상태 자체가 생기지 않는다.

`APPROVED`·`NEEDS_REVIEW`·`FAILED`·`PENDING`은 막지 않는다 — 워커가 손대지 않는 정지 상태다.

### 2-6. 쿼리

`app/queries/projects.sql`에 추가한다.

```sql
-- name: count_active_stages^
-- 삭제 전 확인용: 워커가 손대고 있는 단계 수. RUNNING은 실행 중, QUEUED는 곧 실행된다.
SELECT COUNT(*) AS n
FROM stages
WHERE project_id = :project_id AND status IN ('RUNNING', 'QUEUED');

-- name: soft_delete_project!
-- deleted_at IS NULL 조건은 멱등성을 위한 것이다(이미 지운 것을 다시 지워도 시각이 안 바뀐다).
UPDATE projects
SET deleted_at = :deleted_at,
    deleted_by = :deleted_by,
    updated_at = :deleted_at,
    updated_by = :deleted_by
WHERE id = :id AND deleted_at IS NULL;
```

`count_active_stages`를 `stages.sql`이 아니라 `projects.sql`에 두는 것은 이 쿼리가 프로젝트 삭제 판정에만 쓰이기 때문이다. 다른 곳에서 단계 상태를 세게 되면 그때 옮긴다.

## 3. 정리 잡

### 3-1. 위치와 구동

`app/core/cleanup.py`에 둔다. `app/main.py`의 `lifespan`이 워커와 나란히 시작·정지한다.

```python
worker = get_worker()
await worker.start()
cleanup = get_cleanup_job()
await cleanup.start()
try:
    yield
finally:
    await cleanup.stop()
    await worker.stop()
```

`StageWorker`와 같은 모양으로 만든다 — `session_factory`를 주입받고(테스트가 SAVEPOINT 격리 안에서 돌 수 있게), `start`/`stop`이 asyncio 태스크를 관리하고, 전역 싱글턴 접근자와 테스트용 `reset()`을 둔다. 이유는 워커의 주석에 있는 것과 같다: 잡이 `async_session_maker`를 직접 잡으면 테스트 격리 밖으로 나가 실제 DB에 쓴다.

**핵심은 `run_once()`를 공개 함수로 분리하는 것이다.** 태스크 루프는 `run_once`를 주기적으로 부르는 껍데기일 뿐이고, 테스트는 루프를 돌리지 않고 `run_once`를 직접 부른다. 24시간을 기다리는 테스트를 쓸 수 없으므로 이 분리가 테스트 가능성의 전부다.

```python
PURGE_INTERVAL_SEC = 24 * 60 * 60
PROJECT_RETENTION_DAYS = 30
```

주기는 기동 직후 1회, 이후 24시간마다. 기동 직후에 도는 이유: 개발·배포 중 앱이 자주 재시작되는데 매번 24시간을 기다리면 잡이 사실상 안 돈다.

보관 기간 30일은 **소스 상수로 둔다.** `.env`로 빼면 `check_env_defaults`의 범위 검증까지 붙어야 하고, 관리자가 이 값을 바꿀 이유가 아직 없다. 필요해지면 그때 `runtime_settings`로 올린다.

**동시 인스턴스는 문제가 아니다.** 잡의 모든 작업이 멱등한 DELETE이고, 두 인스턴스가 같은 프로젝트를 동시에 지워도 한쪽이 0행을 지울 뿐이다. 워커의 단일 인스턴스 전제(`_recover`가 RUNNING을 전부 실패 처리)보다 느슨하다.

실패는 삼키고 로그만 남긴다 — 정리 잡의 예외가 앱을 죽이거나 다음 주기를 멈추면 안 된다. 워커의 `_loop`가 같은 방식이다.

### 3-2. 만료 refresh token 삭제

```sql
-- name: delete_expired_refresh_tokens!
DELETE FROM refresh_tokens WHERE expires_at < :now;
```

**조건이 `expires_at < now` 하나여야 하는 이유가 중요하다.**

`app/auth/router.py`의 `refresh`는 **이미 폐기된 토큰이 다시 제시되면 탈취로 보고 그 사용자의 모든 세션을 폐기한다.** 이 경보는 폐기된 행이 DB에 남아 있어야 동작한다. `revoked_at IS NOT NULL`을 지우는 조건에 넣으면, 탈취된 토큰이 재사용될 때 `find_by_token_hash`가 `None`을 돌려주고 평범한 401이 나가면서 **경보가 영구히 죽는다.**

만료 후에는 지워도 안전하다. 만료된 토큰으로는 새 세션을 받을 수 없으므로(`expires_at < now` 검사가 막는다) 공격자가 얻을 것이 없고, 경보가 울려도 보호할 것이 남아 있지 않다.

로그아웃하거나 회전된 토큰은 폐기 시각과 무관하게 **원래 만료 시각(발급 후 14일)까지 남아 있다가** 지워진다. 즉 이 정리는 테이블을 비우는 것이 아니라 상한을 씌우는 것이다 — 활성 사용자 수 × 14일치가 정상 크기다.

### 3-3. 보관 기간 지난 프로젝트 완전 삭제

```sql
-- name: list_purgeable_projects
-- 소프트 삭제 후 보관 기간이 지난 프로젝트. 정리 잡만 쓴다(다른 조회는 삭제된 것을 아예 안 본다).
SELECT id FROM projects
WHERE deleted_at IS NOT NULL AND deleted_at < :before
ORDER BY id;

-- name: delete_assets_by_project!
-- FK에 ON DELETE CASCADE가 없어서 자식부터 직접 지운다. assets는 stage_id로만 프로젝트에 매달려 있다.
DELETE FROM assets
WHERE stage_id IN (SELECT id FROM stages WHERE project_id = :project_id);

-- name: delete_stages_by_project!
DELETE FROM stages WHERE project_id = :project_id;

-- name: delete_project!
DELETE FROM projects WHERE id = :id;
```

프로젝트 하나를 지우는 순서가 이 설계에서 가장 중요한 부분이다.

```
트랜잭션 시작
  ├─ delete_assets_by_project
  ├─ delete_stages_by_project
  ├─ delete_project
  ├─ storage.delete_tree(f"projects/{id}")    ← 파일
  └─ commit                                   ← 마지막
```

**커밋을 파일 삭제 뒤에 두는 이유:**

| 순서 | 중간에 실패하면 | 회복 |
|---|---|---|
| 커밋을 마지막에 (채택) | 파일은 일부 지워졌고 행은 살아 있다 | 다음 주기가 다시 시도해 끝낸다 |
| 커밋을 먼저 | 행은 없고 파일만 남는다 | **영구 고아** — 어느 화면에서도 닿을 수 없고 이 파일을 찾아낼 잡도 없다 |

커밋을 마지막에 두면 "행이 지워졌는데 파일이 남는" 조합이 생길 수 없다. 반대 조합(파일이 지워졌는데 행이 남음)은 남은 행이 이미 소프트 삭제 상태라 사용자에게 보이지 않고, 다음 주기가 마무리한다.

프로젝트는 **한 건씩 각자의 트랜잭션으로** 지운다. 한 건이 실패해도 나머지가 함께 롤백되지 않고, 다음 주기가 실패한 건만 다시 집는다.

`storage.delete_tree`가 `projects/{id}` 전체를 지우므로 **asset으로 기록되지 않는 파일도 함께 정리된다.** 스톡 렌더러가 내려받는 소재가 그렇다(`storage.clear_dir`의 주석 참고 — 소재는 asset 테이블에 남지 않는다). 실제 DB의 asset 경로가 전부 `projects/{id}/...` 형태이고 workdir이 `app/core/pipeline.py` 한 곳에서 `projects/{id}/{stage}`로만 정해지므로, 이 하나의 서브트리가 프로젝트의 파일 전부다.

### 3-4. `storage.delete_tree`

```python
def delete_tree(rel: str) -> None:
    """디렉토리를 하위까지 통째로 지운다. 없어도 조용히 통과한다(멱등).

    clear_dir은 한 단계의 파일만 지워서 프로젝트 삭제에는 쓸 수 없다
    (실제 구조는 projects/{id}/{voice,captions,render}/ 로 한 단 더 깊다).
    """
    path = resolve(rel)  # 저장소 루트 밖 경로는 여기서 ValueError
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
```

경로 검증은 기존 `resolve()`를 그대로 쓴다 — 루트 밖을 가리키면 `ValueError`다. `rmtree`에 `ignore_errors=True`를 주는 이유: 파일 하나가 잠겨 있어도(Windows에서 재생 중인 mp4 등) 나머지는 지우고, 남은 것은 다음 주기가 처리한다.

## 4. 프론트엔드

### 4-1. 삭제 버튼

`web/src/pages/projects/ProjectDetail.tsx` 하단, "← 목록으로"와 같은 줄의 오른쪽에 둔다.

```
┌──────────────────────────────────────────────┐
│ 여행 브이로그 쇼츠                           │
│ 주제: 제주도 3박 4일                         │
│                                              │
│ [ 대본 ]  [ 음성 ]  [ 자막 ]  [ 영상 ]       │
│                                              │
│ ← 목록으로                          [삭제]   │
└──────────────────────────────────────────────┘
```

`!readOnly`일 때만 보인다. 관리자 열람에서 액션 버튼을 숨기는 기존 규칙을 그대로 따르고, 이것이 2-4의 "관리자는 삭제 못 함"과도 자동으로 맞는다.

목록 화면에는 두지 않는다 — 행 클릭이 상세로 가는 표에서 삭제 버튼을 나란히 두면 오클릭이 난다. 관리 컬럼을 새로 만들 만한 동작도 아니다.

### 4-2. 확인 대화상자

`web/src/components/ConfirmDialog.tsx`를 `tone="danger"`로 쓴다.

- 제목: `프로젝트 삭제`
- 본문: `「{제목}」을 삭제합니다. 대본·음성·자막·영상이 함께 사라지며 되돌릴 수 없습니다.`
- 확인 버튼: `삭제`

**"되돌릴 수 없습니다"는 사용자 입장에서 사실이다.** 내부적으로는 30일간 행이 남아 있지만 복원 UI가 없으므로(1절) 화면에서 되돌릴 방법은 없다. 여기에 "30일 안에는 복구 가능"이라고 적으면 화면에 없는 기능을 약속하는 셈이 되어 오히려 거짓이 된다. 보관 기간은 운영자가 사고를 수습할 여지이고, 사용자에게 하는 약속이 아니다.

`window.confirm`을 쓰지 않는다 — 방금 `ConfirmDialog`가 추가되어 다른 화면이 이걸 쓰는 방향으로 가고 있고, 다크모드·디자인이 일관된다.

### 4-3. 성공·실패 처리

성공하면 `useToast`의 `success('프로젝트를 삭제했습니다.')`를 띄우고 `navigate('/projects', { replace: true })`로 목록으로 보낸다. `replace`인 이유: 뒤로 가기로 방금 지운 상세에 돌아가면 404 화면이 뜬다.

실패는 대화상자를 닫지 않고 그 안에 메시지를 보여준다. 409(진행 중)가 실제로 나올 수 있는 유일한 실패이고, 사용자가 "지금은 안 된다"를 읽고 취소해야 하므로 화면이 사라지면 안 된다.

`ConfirmDialog`에는 지금 오류를 표시할 자리가 없다. `message` 아래에 `FormError`를 넣을 수 있도록 옵셔널 `error?: string` prop을 더한다 — 삭제·거절처럼 실패할 수 있는 확인 동작이 앞으로도 이 컴포넌트를 쓰므로, 호출부마다 따로 처리하는 것보다 여기 한 곳에 두는 편이 맞다.

### 4-4. API 클라이언트

`web/src/lib/projects.ts`의 `projects`에 추가한다.

```ts
remove: (id: number) => api.del<{ id: number; deleted_at: string }>(`/projects/${id}`),
```

이름이 `remove`인 것은 `adminNotices`·`adminFaqs`와 같은 이유다(`delete`는 JS 예약어와 겹쳐 읽기 헷갈린다).

## 5. 에러 처리

**백엔드**

| 상황 | 응답 |
|---|---|
| 없는 프로젝트 · 남의 프로젝트 · 이미 삭제된 프로젝트 | 404 `RESOURCE_NOT_FOUND` |
| 진행 중인 단계가 있음 | 409 `PROJECT_BUSY` |
| 비로그인 | 401 |

이미 삭제된 프로젝트가 404인 것은 `find_project_by_id`가 `deleted_at IS NULL`로 걸러서 자동으로 그렇게 된다 — 별도 분기가 없다.

**정리 잡**은 사용자에게 응답하지 않는다. 프로젝트 한 건의 실패는 로그로 남기고 다음 건으로 넘어가며, 주기 전체가 실패해도 다음 주기가 다시 돈다.

**프론트엔드**

| 상황 | 처리 |
|---|---|
| 삭제 실패 | 확인 대화상자 안에 `FormError`, 대화상자는 열어둔다 |
| 삭제 성공 | 토스트 + 목록으로 이동(`replace`) |

## 6. 테스트

**백엔드** (기존 conftest의 testcontainers DB 픽스처)

`tests/test_api_project_delete.py` (신규)

- 삭제는 200이고 `deleted_at`을 돌려준다
- 삭제 후 목록(`GET /api/projects`)에서 빠진다
- 삭제 후 상세(`GET /api/projects/{id}`)가 404다
- 삭제 후 SSE(`GET /api/projects/{id}/events`)가 404다
- 삭제 후 에셋(`GET .../asset`)이 404다
- 삭제 후 관리자 전체 목록(`GET /api/admin/projects`)에서도 빠진다
- 삭제 후 대시보드 집계(`GET /api/dashboard/summary`)의 내 프로젝트 수가 줄고, "조치 필요" 목록에서도 빠진다
- 행은 남아 있고 `deleted_at`·`deleted_by`가 채워진다 (하드 삭제가 아님을 고정)
- `RUNNING` 단계가 있으면 409 `PROJECT_BUSY`이고 `deleted_at`이 그대로 NULL이다
- `QUEUED` 단계가 있으면 409다
- `FAILED`·`NEEDS_REVIEW` 단계만 있으면 삭제된다
- 남의 프로젝트를 지우려 하면 404이고 그 프로젝트는 그대로다
- 관리자가 남의 프로젝트를 지우려 하면 404다
- 같은 프로젝트를 두 번 지우면 두 번째는 404다
- 비로그인은 401이다

`tests/test_core_cleanup.py` (신규) — `run_once`를 직접 부른다

- 만료된 refresh token이 지워진다
- **폐기됐지만 만료되지 않은 토큰은 남는다** (탈취 경보가 계속 동작해야 한다 — 3-2)
- 폐기되지 않고 만료되지 않은 토큰은 남는다
- 보관 기간이 지난 삭제 프로젝트가 행·단계·에셋까지 모두 지워진다
- 그 프로젝트의 `storage/projects/{id}` 디렉토리가 하위까지 사라진다
- 보관 기간이 지나지 않은 삭제 프로젝트는 그대로 남는다
- 삭제되지 않은(`deleted_at IS NULL`) 프로젝트는 기간과 무관하게 그대로다
- asset으로 기록되지 않은 파일(스톡 소재 등)도 함께 지워진다
- 다른 프로젝트의 파일·행은 건드리지 않는다
- `run_once`를 두 번 불러도 오류가 나지 않는다 (멱등)

`tests/test_storage.py` (기존 파일에 추가)

- `delete_tree`가 하위 디렉토리까지 지운다
- 없는 경로에 대해 조용히 통과한다
- 저장소 루트 밖을 가리키는 경로는 `ValueError`다

기존 테스트 중 프로젝트 목록·대시보드 집계를 단언하는 것들은 수정이 필요 없다 — 삭제하지 않은 프로젝트만 다루므로 `deleted_at IS NULL` 조건에 걸리지 않는다. `tests/test_alembic_migration.py`는 새 리비전을 자동으로 포함한다.

**프론트엔드**는 이 프로젝트에 자동화 테스트가 없다. 수동 확인 항목만 남긴다.

- 상세에서 삭제 → 확인 대화상자가 뜨고, 확인하면 토스트와 함께 목록으로 이동한다
- 목록에 그 프로젝트가 없다
- 뒤로 가기로 방금 지운 상세에 돌아가지지 않는다
- 실행 중인 단계가 있을 때 삭제하면 대화상자 안에 409 메시지가 뜨고 대화상자가 닫히지 않는다
- 취소를 누르면 아무 일도 일어나지 않는다
- 관리자 열람(`/admin/projects/:id`)에는 삭제 버튼이 없다
- 다크모드에서 삭제 버튼과 대화상자가 깨지지 않는다

## 7. 구현 순서

1. `deleted_at`·`deleted_by` 모델 + alembic 리비전 + `docs/schema.sql`
2. `storage.delete_tree` + 테스트
3. 조회 쿼리 6개에 `deleted_at IS NULL` (아직 삭제 경로가 없으니 동작 변화 없음 — 회귀만 확인)
4. `soft_delete_project`·`count_active_stages` 쿼리 + 삭제 API + 테스트
5. 정리 잡(`cleanup.py`) + 퍼지 쿼리 + 테스트 + `lifespan` 연결
6. `ConfirmDialog`에 `error` prop 추가
7. 프론트 API 클라이언트 + 상세 화면 삭제 버튼

3번을 4번보다 먼저 하는 이유: 필터를 먼저 넣어두면 삭제 API가 생기는 순간 조회가 이미 올바르게 동작한다. 반대 순서면 "지웠는데 목록에 남아 있는" 중간 상태를 거친다.

5번을 프론트보다 먼저 끝내는 이유: 정리 잡이 프로젝트를 실제로 지우는 유일한 경로다. 화면부터 만들면 소프트 삭제까지만 확인하고 완전 삭제는 검증하지 못한 채로 남는다.
