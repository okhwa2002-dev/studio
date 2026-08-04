# 공지사항 설계

- 작성일: 2026-07-28
- 범위: 공지사항 신규 기능 (테이블 · API · 화면)

## 1. 목적과 범위

관리자가 공지를 작성하고 로그인한 모든 사용자가 읽는 기능을 추가한다. 공지는 목록/상세 화면, 대시보드 위젯, 상단바 안 읽은 배지, 로그인 직후 메인 팝업 네 곳에 노출된다.

**하는 것**

- 관리자 작성/수정/삭제 (임시저장 · 게시 · 예약 게시 · 게시 종료)
- 목록 상단 고정
- 사용자별 읽음 기록과 안 읽은 건수 배지
- 메인 팝업 노출 + "오늘 하루 보지 않기"

**하지 않는 것**

- 마크다운/리치 텍스트 본문 (일반 텍스트 + 줄바꿈 유지)
- 첨부파일, 카테고리, 조회수
- 비로그인 공개 노출
- 실시간 푸시(SSE) — 공지 갱신 빈도에 비해 과하다

## 2. 데이터 모델

### 2-1. `notices`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BIGINT PK | 기본키, BIGINT 자동 증가 |
| `title` | VARCHAR NOT NULL | 공지 제목 |
| `body` | TEXT NOT NULL | 본문 (일반 텍스트, 줄바꿈 그대로 표시) |
| `status` | VARCHAR NOT NULL `'DRAFT'` | 상태: `DRAFT` \| `PUBLISHED` |
| `pinned_yn` | CHAR(1) NOT NULL `'N'` | 목록 상단 고정 여부: `Y` \| `N` |
| `popup_yn` | CHAR(1) NOT NULL `'N'` | 메인 팝업 노출 여부: `Y` \| `N` |
| `starts_at` | TIMESTAMP NULL | 게시 시작 일시 (`DRAFT`면 NULL) |
| `ends_at` | TIMESTAMP NULL | 게시 종료 일시 (NULL = 무기한) |
| `deleted_at` | TIMESTAMP NULL | 소프트 삭제 일시 (NULL = 미삭제) |
| `deleted_by` | BIGINT NULL → `users.id` | 삭제한 관리자 |
| `created_at` / `created_by` | | `base.py` 헬퍼 |
| `updated_at` / `updated_by` | | `base.py` 헬퍼 |

컬럼 순서는 프로젝트 규칙대로 `id` → 업무 컬럼 → 감사 컬럼이다. 모델은 `app/models/notice.py`에 `BaseEntity`를 상속해 선언하고, 감사 컬럼은 클래스 본문 맨 아래에서 `created_at_field()` 등 헬퍼로 명시 선언한다.

**게시일 컬럼을 `starts_at` 하나로 통일한다.** `published_at`을 따로 두면 "게시일"이 두 개가 되어 화면마다 어느 쪽을 보여줄지 헷갈린다. 게시 전환 시 `starts_at`이 비어 있으면 서버가 그 시각으로 채우므로, 이후 `starts_at`이 유일한 게시일이다. 미래 값을 넣으면 예약 게시가 된다.

**팝업 기간은 게시 기간을 그대로 쓴다.** `popup_starts_at`을 따로 두면 "게시는 끝났는데 팝업만 살아있는" 상태를 매번 방어해야 한다. `popup_yn`은 "게시 중인 동안 팝업으로도 띄울지"를 뜻하는 플래그 하나다.

**참/거짓 컬럼은 BOOLEAN이 아니라 `_yn` 접미사 + `'Y'`/`'N'` 문자로 표기한다.** 이 테이블이 프로젝트에 참/거짓 컬럼을 처음 들이므로, 여기서 정한 표기가 앞으로의 기준이 된다. 두 컬럼 모두 같은 규칙을 따른다.

정렬에서 `pinned_yn DESC`는 `'Y'`(0x59)가 `'N'`(0x4E)보다 커서 고정 공지를 앞으로 보낸다 — BOOLEAN `true DESC`와 결과가 같다.

### 2-2. `notice_reads`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BIGINT PK | 기본키, BIGINT 자동 증가 |
| `notice_id` | BIGINT NOT NULL → `notices.id`, index | 읽은 공지 |
| `user_id` | BIGINT NOT NULL → `users.id`, index | 읽은 사용자 |
| `created_at` / `created_by` | | `base.py` 헬퍼 |
| `updated_at` / `updated_by` | | `base.py` 헬퍼 |

`UNIQUE(notice_id, user_id)` — 재열람 시 행이 늘지 않게 한다. `created_by`·`updated_by`에는 `user_id`와 같은 값(읽은 본인)이 들어간다.

**`read_at` 컬럼을 두지 않는다.** 행의 존재가 곧 "읽음"이고, 읽은 시각은 `created_at`이다. `read_at`을 따로 두면 항상 `created_at`과 같은 값이 들어가는 중복 컬럼이 된다. 이 규칙은 테이블 코멘트에 명시한다: `"공지 읽음 기록 (행 존재 = 읽음, created_at = 읽은 시각)"`.

### 2-3. 노출 조건과 파생 상태

사용자에게 보이는 공지의 조건은 한 줄로 고정된다.

```sql
deleted_at IS NULL AND status = 'PUBLISHED'
  AND starts_at <= :now AND (ends_at IS NULL OR ends_at > :now)
```

팝업 대상은 여기에 `AND popup_yn = 'Y'`를 더한 것이다.

관리자 화면의 표시 상태는 저장하지 않고 파생한다.

| 표시 | 조건 |
|---|---|
| 임시저장 | `status = 'DRAFT'` |
| 예약 | `status = 'PUBLISHED'` AND `starts_at > now` |
| 게시중 | `status = 'PUBLISHED'` AND `starts_at <= now` AND (`ends_at` IS NULL OR `ends_at > now`) |
| 종료 | `status = 'PUBLISHED'` AND `ends_at <= now` |

### 2-4. 상수와 마이그레이션

`app/constants.py`에 추가한다.

```python
class NoticeStatus(StrEnum):
    """notices.status 코드값. DB에 대문자로 저장된다."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class YN(StrEnum):
    """참/거짓을 나타내는 *_yn 컬럼의 값."""

    Y = "Y"
    N = "N"
```

`YN`은 특정 테이블 전용이 아니므로 `NoticeStatus`와 떨어뜨려, 파일 안에서 도메인 열거형들보다 위에 둔다.

마이그레이션은 기존 방식대로 alembic autogenerate로 만든 뒤 컬럼 코멘트를 다듬는다(`ac6e7626417d_create_projects_and_stages.py`가 참고 예시).

### 2-5. "오늘 하루 보지 않기"는 DB에 저장하지 않는다

브라우저 `localStorage`의 `notice_popup_dismissed` 키에 `{ "12": "2026-07-28" }` 형태로 담고, 값이 오늘 날짜와 같으면 그 공지의 팝업을 건너뛴다. 읽을 때 오늘이 아닌 항목은 지운다. 기기별로 따로 노는 것은 이 기능의 정상 동작이다.

## 3. API

모든 경로는 `main.py`에서 `prefix="/api"`로 등록한다.

### 3-1. 사용자용 — `app/api/notices.py` (prefix `/notices`, 전부 `current_user` 의존)

| 메서드 | 경로 | 응답 |
|---|---|---|
| GET | `/api/notices` | 게시중 공지 목록 (각 행에 `is_read`) |
| GET | `/api/notices/popups` | 팝업 대상 목록 (게시중 + `popup_yn = 'Y'`) |
| GET | `/api/notices/unread/count` | `{ "count": 3 }` |
| GET | `/api/notices/{id}` | 공지 한 건 (상세 화면용, `is_read` 포함) |
| POST | `/api/notices/{id}/read` | 읽음 기록 |

목록 정렬은 `pinned_yn DESC, starts_at DESC, id DESC`다.

**응답은 DB 값을 그대로 `"Y"` / `"N"`으로 내려준다.** API 경계에서 불리언으로 바꾸면 같은 값이 DB·API·프론트에서 세 가지 표기를 갖게 되고, 어느 층에서 뒤집혔는지 추적하기 어려워진다. 프론트 타입도 `'Y' | 'N'`이고, 변환은 체크박스에 바인딩하는 지점 한 곳에서만 일어난다(4-6).

**목록 응답에도 `body`를 포함시킨다.** 검색이 제목뿐 아니라 본문까지 훑기 때문이다. 상세는 `GET /notices/{id}`가 따로 준다 — 상세가 별도 화면(`/notices/:id`)이라 새로고침·링크 공유로 바로 들어올 수 있어야 하고, 그때 목록 전체를 받아 골라내는 것은 낭비다. 이 경로는 `popups`·`unread/count`가 `{id}`로 잡히지 않도록 두 정적 경로보다 **뒤에** 선언한다.

`POST /{id}/read`는 `ON CONFLICT DO NOTHING`이라 몇 번을 불러도 결과가 같다. 노출 조건을 만족하지 않는 공지 id면 404를 낸다.

### 3-2. 관리자용 — `app/api/admin_notices.py` (prefix `/admin/notices`, 전부 `require_admin` 의존)

| 메서드 | 경로 | 동작 |
|---|---|---|
| GET | `/api/admin/notices` | 삭제되지 않은 전체 목록 (작성자 이름 조인) |
| POST | `/api/admin/notices` | 생성 (201) |
| PATCH | `/api/admin/notices/{id}` | 수정 |
| DELETE | `/api/admin/notices/{id}` | 소프트 삭제 (`deleted_at`/`deleted_by` 기록) |

상태 필터·검색은 `admin_projects.py`와 같은 방침으로 프론트에서 처리한다.

### 3-3. 요청 검증과 게시 전환 규칙

요청 본문은 `CreateProjectRequest`와 같이 pydantic `BaseModel` + `field_validator`로 받는다.

- `title`·`body`: 앞뒤 공백을 다듬고 공백뿐인 값은 거부한다 → FastAPI가 422
- `pinned_yn`·`popup_yn`: 요청 모델에 `YN` 타입으로 선언해 `'Y'`/`'N'` 외의 값을 FastAPI가 422로 거른다 (`UserStatus`를 쿼리 파라미터로 선언한 `admin_router.list_users`와 같은 방식)
- `status = 'PUBLISHED'`인데 `starts_at`이 비어 있으면 → 서버가 `now_local()`로 채운다
- `status = 'DRAFT'`로 되돌리면 → `starts_at`을 NULL로 비운다. "임시저장 = 아직 게시된 적 없음"이라는 의미를 지키기 위해서고, 다시 게시하면 그때 시각이 새 게시일이 된다
- `ends_at <= starts_at`이면 → `Errors.bad_request("종료 일시는 시작 일시보다 뒤여야 합니다.")`
- 없거나 이미 삭제된 id면 → `Errors.not_found("공지사항을 찾을 수 없습니다.")`

### 3-4. 시각 비교는 앱이 넘긴 `now_local()`을 쓴다

SQL 안에서 `now()`를 쓰면 DB 세션 타임존(UTC) 기준이라 이 프로젝트의 Asia/Seoul naive 저장 규칙과 9시간 어긋난다(`app/models/base.py`에 같은 취지의 주석이 있다). 노출 조건이 들어가는 쿼리는 전부 `:now`를 파라미터로 받는다.

### 3-5. `app/queries/notices.sql`

aiosql 이름 붙은 쿼리로 다음을 둔다.

| 쿼리 | 용도 |
|---|---|
| `list_published_notices` | 사용자 목록 — `notice_reads` LEFT JOIN으로 `is_read` 계산 |
| `list_popup_notices` | 팝업 대상 (읽음 여부와 무관) |
| `count_unread_notices^` | 배지 — 노출 조건 AND 내 읽음 행 없음 |
| `find_published_notice_by_id^` | 상세 조회 + 읽음 처리 전 노출 조건 확인 (없으면 404) — 두 경로가 같은 쿼리를 쓴다 |
| `mark_notice_read!` | 읽음 기록 `INSERT ... ON CONFLICT DO NOTHING` |
| `list_notices_for_admin` | 관리자 목록 (`users` LEFT JOIN으로 작성자 이름), 정렬 `pinned_yn DESC, COALESCE(starts_at, created_at) DESC, id DESC` |
| `find_notice_by_id^` | 수정·삭제 전 존재 확인 (삭제된 행 제외) |
| `insert_notice<!` | 생성 |
| `update_notice!` | 수정 |
| `soft_delete_notice!` | `deleted_at`/`deleted_by` 기록 |

### 3-6. 대시보드 위젯은 전용 API를 두지 않는다

`GET /api/notices`를 그대로 부르고 상위 5건만 자른다. `/api/dashboard/summary`에 끼워 넣으면 대시보드 집계 응답이 공지 도메인과 엮이고, 위젯의 "더보기 → /notices"가 같은 데이터를 두 경로로 받게 된다.

## 4. 화면

### 4-1. 사용자 공지 목록 `/notices`

```
공지사항
┌──────────────────────────────────────────────┐
│                        [제목 또는 내용 검색] │
│ ──────────────────────────────────────────── │
│ No    제목                          게시일   │
│ [공지] 서버 점검 안내       🔴NEW   07-28   │
│ [공지] 이용약관 개정 안내           07-25   │
│  3    v1.2 업데이트 내용    🔴NEW   07-20   │
│  2    추석 연휴 운영 안내           07-14   │
│  1    서비스 오픈 안내              07-01   │
│ ──────────────────────────────────────────── │
│                 총 5건   ‹ 1 ›               │
└──────────────────────────────────────────────┘
     ↓ 행 클릭 → /notices/:id

공지사항                              ← 화면 이동
┌──────────────────────────────────────────────┐
│ 서버 점검 안내                               │
│ 2026-07-28                                   │
│ ──────────────────────────────────────────── │
│ 7/30(목) 02:00~04:00 정기 점검이 있습니다.   │
│ 해당 시간 렌더링 요청은 대기 상태로 남습니다.│
│                                              │
│ [← 목록으로]                                 │
└──────────────────────────────────────────────┘
```

목록은 기존 `Table` + `badgedSeqColumn` + `TableFooter`를 쓴다. 검색은 `AdminUsers`와 같이 클라이언트 필터다(제목 + 본문).

고정 공지는 번호 대신 `공지` 배지를 보여준다. 번호는 최신순 일련번호인데 고정 공지는 그 순서를 벗어나 있어, 번호를 붙이면 목록의 번호가 뒤죽박죽이 된다.

**검색어와 페이지는 URL 쿼리(`?q=`, `?page=`)에 둔다.** 상세가 별도 화면이라 목록을 떠났다 돌아오는 흐름이 생겼고, 그때 보던 자리가 살아 있어야 한다. 기본값(빈 검색어·1페이지)은 적지 않고, 페이지 이동은 `replace`로 써서 히스토리에 쌓지 않는다. `useClientPagination`은 선택적 `binding`을 받아 페이지 번호만 바깥(URL)에 맡기고, 범위 보정 규칙은 그대로 훅이 관리한다.

**상세는 모달이 아니라 화면(`/notices/:id`)이다.** 본문은 `whitespace-pre-wrap`으로 줄바꿈을 살려 그린다. 진입하면 `GET /api/notices/{id}`로 한 건을 받고, 아직 읽지 않았으면 `POST /api/notices/{id}/read`를 보낸 뒤 컨텍스트의 `refresh()`로 상단바 배지를 줄인다. 노출 조건을 벗어난 id면 404 메시지를 그린다.

`[← 목록으로]`는 목록에서 넘겨준 검색어·페이지(`location.state.from`)를 달고 돌아간다. URL로 바로 들어왔으면 값이 없어 기본 목록으로 간다.

### 4-2. 상단바 배지

```
┌──────────────────────────────────────────────┐
│ ☰  Studio                    📢②   [사용자▾] │
└──────────────────────────────────────────────┘
```

`UserMenu` 왼쪽에 📢 버튼을 두고, 안 읽은 건수가 0이면 배지를 그리지 않는다. 클릭하면 `/notices`로 이동한다.

배지 값은 `AppLayout`이 감싸는 `UnreadNoticesProvider`에서 온다. 컨텍스트는 `{ count, refresh() }`를 공급하고, 최초 마운트와 라우트 변경 시 한 번씩 조회한다. 공지 목록에서 읽음 처리가 끝나면 `refresh()`를 호출해 즉시 반영한다.

라우트 변경 시 재조회만 하고 컨텍스트를 두지 않는 안(案)도 검토했으나, 공지 목록에 머문 채로 여러 건을 읽으면 화면을 떠나기 전까지 배지가 그대로 남는 어색함이 실제로 눈에 띈다. 해소 비용은 파일 하나다.

### 4-3. 메인 팝업

```
┌─ 서버 점검 안내 ──────────────────  ✕ ┐
│ 2026-07-28                            │
│ ───────────────────────────────────── │
│ 7/30(목) 02:00~04:00 정기 점검이      │
│ 있습니다.                             │
│ ───────────────────────────────────── │
│ ☐ 오늘 하루 보지 않기          [닫기] │
└───────────────────────────────────────┘
```

**`AppLayout`에 두고 마운트될 때 한 번만 조회한다.** `Dashboard` 페이지에 매달면 화면을 옮겨 다닐 때마다 다시 뜬다. `AppLayout`은 라우트의 부모라 페이지 이동으로 리마운트되지 않으므로(파일 주석에 명시된 설계), 로그인 직후·새로고침 직후에 딱 한 번 뜬다.

팝업 대상이 여러 건이면 `pinned_yn DESC, starts_at DESC` 순으로 한 건씩 순차 표시한다 — 닫으면 다음 건이 뜬다.

"오늘 하루 보지 않기"를 체크하고 닫으면 `localStorage`에 기록한다(2-5). **팝업 닫기는 읽음 처리를 하지 않으므로** 상단바 배지와 목록 NEW는 그대로 남는다.

### 4-4. 대시보드 위젯

```
공지사항                              더보기 →
┌──────────────────────────────────────────────┐
│ 📌 서버 점검 안내             🔴NEW   07-28  │
│ 📌 이용약관 개정 안내                 07-25  │
│    v1.2 업데이트 내용         🔴NEW   07-20  │
└──────────────────────────────────────────────┘

내 프로젝트                        [프로젝트 이동]
...
```

`MemberSection` 위에 놓는다. `GET /api/notices` 결과의 상위 5건을 자르고, 행을 누르면 그 공지의 상세(`/notices/:id`)로 바로 간다 — 읽음 처리와 배지 갱신은 상세 화면이 맡으므로 목록을 한 번 더 거칠 이유가 없다. 공지가 없으면 섹션 자체를 그리지 않는다.

### 4-5. 관리자 공지 관리 `/admin/notices`

```
공지 관리
┌────────────────────────────────────────────────────────────┐
│ [전체][게시중][예약][임시저장][종료]  [검색]   [+ 새 공지] │
│ ────────────────────────────────────────────────────────── │
│ 번호 제목            상태   고정 팝업 게시기간      작성자 │
│  5  서버 점검 안내   게시중  📌  💬  07-28~07-31   김관리 │
│  4  이용약관 개정    게시중  📌   -   07-25~       김관리 │
│  3  8월 이벤트       예약    -    💬  08-01~08-31  이운영 │
│  2  v1.2 업데이트    게시중  -    -   07-20~       김관리 │
│  1  초안 작성 중     임시저장 -   -   -            김관리 │
│ ────────────────────────────────────────────────────────── │
│                        총 5건   ‹ 1 ›                      │
└────────────────────────────────────────────────────────────┘
     ↓ 행 클릭 / [+ 새 공지]
┌─ 모달: 공지 수정 ─────────────────────────┐
│ 제목  [서버 점검 안내             ]       │
│ 내용  [                           ]       │
│       [                           ]       │
│       [                           ]       │
│ 게시  [2026-07-28 09:00] ~                │
│       [2026-07-31 00:00]  (비우면 무기한) │
│ ☑ 목록 상단 고정   ☑ 메인 팝업으로 노출   │
│ ───────────────────────────────────────── │
│ [삭제]             [임시저장] [게시하기]  │
└───────────────────────────────────────────┘
```

상태 탭은 `AdminUsers`의 `STATUS_TABS`와 같은 방식으로, 서버가 준 `status`·`starts_at`·`ends_at`에서 파생 상태를 계산해 클라이언트에서 거른다. 검색도 사용자 목록과 같이 제목 + 본문을 대상으로 하는 클라이언트 필터다.

`[임시저장]`은 `status = 'DRAFT'`로, `[게시하기]`는 `status = 'PUBLISHED'`로 저장한다. `[삭제]`는 `window.confirm`으로 한 번 확인한 뒤 소프트 삭제한다. 새 공지 모달에는 `[삭제]`가 없다.

### 4-6. 신규·수정 파일

| 파일 | 내용 |
|---|---|
| `web/src/lib/notices.ts` | `Notice` 타입(`pinned_yn`·`popup_yn`은 `'Y' \| 'N'`) + 사용자 API (`list`, `detail`, `popups`, `unreadCount`, `markRead`) + `isY(v)` / `toYn(checked)` 변환 헬퍼 |
| `web/src/lib/unreadNotices.tsx` | `UnreadNoticesProvider` + `useUnreadNotices()` — `lib/auth.tsx`와 같은 컨텍스트 패턴 |
| `web/src/pages/notices/Notices.tsx` | 사용자 목록 (검색어·페이지는 URL 쿼리) |
| `web/src/pages/notices/NoticeDetail.tsx` | 사용자 상세 화면 + 읽음 처리 |
| `web/src/pages/admin/AdminNotices.tsx` | 관리자 목록 + 등록/수정 모달 |
| `web/src/components/NoticePopup.tsx` | 메인 팝업 (`Modal` 재사용) |
| `web/src/lib/admin.ts` | `AdminNotice` 타입 + `adminNotices` + 파생 상태 `noticePhase` 추가 (`adminUsers`·`adminProjects` 옆) |
| `web/src/lib/api.ts` | `patch`·`del` 추가 — 지금은 `get`·`post`만 있어 관리자 수정·삭제를 보낼 수단이 없다 |
| `web/src/lib/nav.ts` | `📢 공지사항`(`/notices`), `🗞️ 공지 관리`(`/admin/notices`, adminOnly) |
| `web/src/App.tsx` | 세 라우트 등록 (`/notices`, `/notices/:id`, `/admin/notices` — 마지막은 `RequireAdmin` 안) |
| `web/src/layouts/AppLayout.tsx` | Provider로 감싸고 `NoticePopup` 렌더 |
| `web/src/components/layout/Topbar.tsx` | 📢 배지 |
| `web/src/pages/Dashboard.tsx` | `NoticeSection` 추가 |

메뉴 순서는 일반 항목이 `대시보드 · 프로젝트 · 공지사항 · 설정`, 관리자 항목이 `가입 승인 · 사용자 관리 · 전체 프로젝트 · 공지 관리 · 시스템 설정`이다.

## 5. 에러 처리

**백엔드**는 기존 방식 그대로다 — 도메인 오류는 `Errors.*`로 던지고 `main.py`의 `app_error_handler`가 `{code, message}`로 응답한다. 예상 못한 예외는 `DEFAULT_ERROR`로 덮인다.

**프론트엔드**는 화면별로 실패의 무게가 다르다.

| 상황 | 처리 |
|---|---|
| 목록 조회 실패 | `FormError`로 메시지 표시 (기존 `AdminUsers` 패턴) |
| 저장·삭제 실패 | 모달 안에 `FormError` 표시, 모달은 닫지 않음 |
| 읽음 처리 실패 | 조용히 넘어간다. 본문은 이미 열려 있고, NEW 배지가 남았다가 다음 열람 때 다시 시도된다 |
| 배지 조회 실패 | 배지를 그리지 않는다 (`count = 0`으로 취급) |
| 팝업 조회 실패 | 조용히 넘어간다 |

읽음 처리·배지·팝업은 부가 정보라, 실패했다고 사용자에게 에러를 띄우면 본래 하려던 일(공지 읽기)을 방해한다.

## 6. 테스트

**백엔드** (`tests/`, 기존 conftest의 testcontainers 기반 DB 픽스처 사용)

`tests/test_notices.py` — 사용자 API

- 게시중 공지만 목록에 나온다 (임시저장 · 예약 · 종료 · 삭제된 공지는 빠진다)
- 정렬이 `pinned_yn DESC, starts_at DESC, id DESC`다 (고정 공지가 맨 위)
- 읽은 공지의 `is_read`가 true다
- `unread/count`가 안 읽은 건수와 맞는다
- `POST /{id}/read`를 두 번 불러도 `notice_reads` 행이 하나다
- 노출 조건을 만족하지 않는 id로 읽음 처리하면 404
- 다른 사용자의 읽음 기록이 내 `is_read`·배지에 새지 않는다
- 비로그인 요청은 401

`tests/test_admin_notices.py` — 관리자 API

- MEMBER 권한은 403
- 생성 시 `status = 'PUBLISHED'`이고 `starts_at`이 비면 서버가 채운다
- `DRAFT`로 되돌리면 `starts_at`이 NULL이 된다
- `ends_at <= starts_at`이면 400
- 공백뿐인 `title`·`body`는 422
- `pinned_yn`·`popup_yn`에 `'Y'`/`'N'` 아닌 값을 넣으면 422 (요청 모델이 `YN`으로 선언되어 FastAPI가 거른다)
- 삭제는 행을 지우지 않고 `deleted_at`/`deleted_by`만 채우며, 이후 관리자 목록과 사용자 목록 양쪽에서 빠진다

`tests/test_alembic_migration.py`는 이미 마이그레이션 왕복을 검증하므로 새 테이블이 자동으로 범위에 들어온다. 새 리비전 추가 후 이 테스트가 통과하는지 확인한다.

**프론트엔드**는 이 프로젝트에 자동화 테스트가 없다. 수동 확인 항목만 남긴다.

- 관리자로 공지를 게시 → 일반 사용자 계정에서 배지 · 목록 · 대시보드 위젯 · 팝업 네 곳에 모두 뜬다
- 목록에서 공지를 열면 배지가 즉시 줄고 NEW가 사라진다
- 팝업에서 "오늘 하루 보지 않기" 후 새로고침하면 팝업이 안 뜨지만 배지는 그대로다
- 예약 게시한 공지가 시작 전에는 사용자 화면에 안 보인다
- 다크모드에서 배지 · 팝업 · 상태 뱃지 색이 깨지지 않는다

## 7. 구현 순서

1. 모델(`notice.py`, `notice_read.py`) + `NoticeStatus` 상수 + alembic 리비전
2. `notices.sql` 쿼리
3. 관리자 API + 테스트
4. 사용자 API + 테스트
5. 프론트 lib(`notices.ts`, `unreadNotices.tsx`, `admin.ts`) + 라우트/메뉴
6. 관리자 화면 → 사용자 목록 화면 → 상단바 배지 → 대시보드 위젯 → 메인 팝업

관리자 화면을 먼저 만들어야 사용자 화면을 확인할 공지 데이터를 UI로 넣을 수 있다.
