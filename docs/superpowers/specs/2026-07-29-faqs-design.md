# FAQ 설계

- 작성일: 2026-07-29
- 범위: FAQ 신규 기능 (테이블 · API · 화면)

## 1. 목적과 범위

관리자가 자주 묻는 질문과 답변을 등록하고, 로그인한 사용자가 한 화면에서 훑어보며 궁금한 항목만 펼쳐 읽는 기능을 추가한다.

관리자 화면은 공지사항(`2026-07-28-notices-design.md`)의 구조를 그대로 따르고, 사용자 화면만 아코디언으로 다르게 간다. 공지는 "한 건을 정독"하는 성격이라 목록 + 상세 모달이 맞지만, FAQ는 "여러 질문을 훑다가 궁금한 것만 펼치는" 소비 패턴이라 모달을 열고 닫으면 흐름이 끊긴다.

**하는 것**

- 관리자 작성/수정/삭제 (임시저장 · 게시)
- 분류(카테고리)와 관리자가 지정하는 정렬 순서
- 사용자 화면: 분류 탭 + 검색 + 아코디언 (한 번에 하나만 열림)

**하지 않는 것**

- 읽음 기록 · NEW 배지 · 상단바 배지 · 메인 팝업 · 대시보드 위젯 — FAQ는 "새 글이 올라왔으니 확인하라"가 아니라 "궁금할 때 찾아보는" 참고 문서다. 공지사항이 이 네 곳에 노출되는 이유가 FAQ에는 없다
- 예약 게시 · 게시 종료 일시 — "8월 31일까지만 답변" 같은 수요가 없다
- 마크다운/리치 텍스트 답변 (일반 텍스트 + 줄바꿈 유지, 공지와 동일)
- 첨부파일, 도움됐어요 투표, 조회수
- 비로그인 공개 노출

## 2. 데이터 모델

### 2-1. `faqs`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BIGINT PK | 기본키, BIGINT 자동 증가 |
| `question` | VARCHAR NOT NULL | 질문 |
| `answer` | TEXT NOT NULL | 답변 (일반 텍스트, 줄바꿈 그대로 표시) |
| `category` | VARCHAR NOT NULL | 분류: `ACCOUNT` \| `PROJECT` \| `PRODUCTION` \| `ETC` |
| `status` | VARCHAR NOT NULL `'DRAFT'` | 상태: `DRAFT` \| `PUBLISHED` |
| `sort_order` | INTEGER NOT NULL `0` | 목록 정렬 순서 (작을수록 위) |
| `deleted_at` | TIMESTAMP NULL | 소프트 삭제 일시 (NULL = 미삭제) |
| `deleted_by` | BIGINT NULL → `users.id` | 삭제한 관리자 |
| `created_at` / `created_by` | | `base.py` 헬퍼 |
| `updated_at` / `updated_by` | | `base.py` 헬퍼 |

컬럼 순서는 프로젝트 규칙대로 `id` → 업무 컬럼 → 감사 컬럼이다. 모델은 `app/models/faq.py`에 `BaseEntity`를 상속해 선언하고, 감사 컬럼은 클래스 본문 맨 아래에서 `created_at_field()` 등 헬퍼로 명시 선언한다(`app/models/notice.py`와 같은 모양).

**`notice_reads`에 대응하는 테이블을 두지 않는다.** 읽음 기록이 없으므로 조인도, 안 읽은 건수 집계도, 읽음 처리 API도 없다.

**게시 기간 컬럼(`starts_at`·`ends_at`)을 두지 않는다.** 노출 조건이 `status` 하나로 끝나므로, 공지에서 필요했던 `:now` 파라미터 전달(SQL의 `now()`가 DB 세션 타임존 UTC 기준이라 이 프로젝트의 Asia/Seoul naive 저장 규칙과 9시간 어긋나는 문제를 피하려는 장치)이 통째로 사라진다. FAQ 쿼리에는 시각 비교가 없다.

**`pinned_yn` 대신 `sort_order`를 쓴다.** FAQ에서 중요한 것은 "맨 위 한 건"이 아니라 전체 순서다. 두 수단을 함께 두면 관리자가 어느 쪽으로 순서를 잡아야 할지 헷갈리므로 하나만 남긴다.

### 2-2. 노출 조건과 정렬

사용자에게 보이는 FAQ의 조건은 한 줄이다.

```sql
deleted_at IS NULL AND status = 'PUBLISHED'
```

정렬은 사용자·관리자 목록 모두 `sort_order ASC, id ASC`다. 공지는 최신순 DESC지만 FAQ는 관리자가 정한 순서가 곧 목록이고, `sort_order`가 같으면 먼저 등록된 것이 위로 간다.

관리자 화면의 상태 표시는 `status` 값을 그대로 쓴다. 공지의 `noticePhase` 같은 파생 함수가 필요 없다.

| 표시 | 조건 |
|---|---|
| 임시저장 | `status = 'DRAFT'` |
| 게시중 | `status = 'PUBLISHED'` |

### 2-3. 상수와 마이그레이션

`app/constants.py`에 추가한다. 파일 안에서는 `NoticeStatus` 아래에 둔다.

```python
class FaqCategory(StrEnum):
    """faqs.category 코드값. DB에 대문자로 저장된다."""

    ACCOUNT = "ACCOUNT"  # 계정
    PROJECT = "PROJECT"  # 프로젝트
    PRODUCTION = "PRODUCTION"  # 영상제작
    ETC = "ETC"  # 기타


class FaqStatus(StrEnum):
    """faqs.status 코드값. DB에 대문자로 저장된다."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
```

**`FaqStatus`는 `NoticeStatus`와 값이 같지만 공유하지 않는다.** `UserStatus`·`ProjectStatus`·`StageStatus`가 각자 자기 열거형을 갖는 기존 규칙을 따르고, 한쪽 도메인에 상태를 추가할 때 다른 도메인이 딸려 오지 않게 하기 위해서다.

한글 라벨은 백엔드에 두지 않는다. 코드값만 내려주고 화면 표기는 프론트의 `FAQ_CATEGORY_LABEL` 한 곳에서 정한다(4-4).

마이그레이션은 기존 방식대로 alembic autogenerate로 만든 뒤 컬럼 코멘트를 다듬는다. 테이블 코멘트는 `"자주 묻는 질문 (관리자 작성, 전체 사용자 열람)"`이다.

## 3. API

모든 경로는 `main.py`에서 `prefix="/api"`로 등록한다.

### 3-1. 사용자용 — `app/api/faqs.py` (prefix `/faqs`, `current_user` 의존)

| 메서드 | 경로 | 응답 |
|---|---|---|
| GET | `/api/faqs` | 게시중 FAQ 전체 (`answer` 포함) |

엔드포인트가 하나다.

**목록 응답에 `answer`를 포함시켜 상세 조회 API를 두지 않는다.** 아코디언은 애초에 "이미 받아온 답변을 펼치는" 구조라, 상세 API가 있으면 질문을 누를 때마다 왕복이 생기고 펼침 애니메이션 중에 빈 영역이 보인다. 공지도 같은 이유로 목록에 `body`를 담는다.

응답 필드는 `id`, `question`, `answer`, `category`다. `sort_order`는 서버가 정렬해서 내려주므로 응답에 넣지 않는다 — 사용자 화면이 다시 정렬할 일이 없다.

### 3-2. 관리자용 — `app/api/admin_faqs.py` (prefix `/admin/faqs`, `require_admin` 의존)

| 메서드 | 경로 | 동작 |
|---|---|---|
| GET | `/api/admin/faqs` | 삭제되지 않은 전체 목록 (작성자 이름 조인) |
| POST | `/api/admin/faqs` | 생성 (201) |
| PATCH | `/api/admin/faqs/{id}` | 수정 |
| DELETE | `/api/admin/faqs/{id}` | 소프트 삭제 (`deleted_at`/`deleted_by` 기록) |

상태 필터·검색은 `admin_notices.py`와 같은 방침으로 프론트에서 처리한다.

### 3-3. 요청 검증

요청 본문은 `NoticeRequest`와 같이 pydantic `BaseModel` + `field_validator`로 받는다. 생성과 수정이 같은 모델을 쓴다 — 관리자 모달이 항상 편집 가능한 전체를 보낸다.

```python
class FaqRequest(BaseModel):
    question: str
    answer: str
    category: FaqCategory
    status: FaqStatus = FaqStatus.DRAFT
    sort_order: int = Field(default=0, ge=0)
```

- `question`·`answer`: 앞뒤 공백을 다듬고 공백뿐인 값은 거부한다 → FastAPI가 422
- `category`·`status`: 열거형 타입으로 선언해 코드값 외의 값을 FastAPI가 422로 거른다 (`NoticeRequest`의 `pinned_yn: YN`과 같은 방식)
- `sort_order`: `ge=0`이라 음수는 422. 음수를 허용하면 "맨 위로 올리기"를 음수로도, 0으로도 할 수 있게 되어 같은 목적의 값이 두 갈래가 된다
- 없거나 이미 삭제된 id면 → `Errors.not_found("FAQ를 찾을 수 없습니다.")`

공지의 `_resolve_period` 같은 게시 전환 규칙은 없다. `status`는 요청 값 그대로 저장한다.

### 3-4. `app/queries/faqs.sql`

aiosql 이름 붙은 쿼리로 다음을 둔다.

| 쿼리 | 용도 |
|---|---|
| `list_published_faqs` | 사용자 목록 — `deleted_at IS NULL AND status = 'PUBLISHED'`, `ORDER BY sort_order, id` |
| `list_faqs_for_admin` | 관리자 목록 (`users` LEFT JOIN으로 작성자 이름), 같은 정렬 |
| `find_faq_by_id^` | 수정·삭제 전 존재 확인 (삭제된 행 제외) |
| `insert_faq<!` | 생성 |
| `update_faq!` | 수정 |
| `soft_delete_faq!` | `deleted_at`/`deleted_by` 기록 |

`soft_delete_faq!`는 `soft_delete_notice!`와 같이 `updated_at`/`updated_by`도 함께 갱신한다.

## 4. 화면

### 4-1. 사용자 FAQ `/faqs`

```
FAQ
┌────────────────────────────────────────────────┐
│ [전체][계정][프로젝트][영상제작][기타]         │
│                        [질문 또는 답변 검색]   │
│ ────────────────────────────────────────────── │
│ Q  렌더링은 얼마나 걸리나요?              ⌄    │
│    1분 영상 기준 3~5분입니다.                  │
│    대기열이 길면 더 걸릴 수 있어요.            │
│ ────────────────────────────────────────────── │
│ Q  프로젝트를 삭제할 수 있나요?           ›    │
│ ────────────────────────────────────────────── │
│ Q  음성을 바꿀 수 있나요?                 ›    │
└────────────────────────────────────────────────┘
```

`web/src/pages/faqs/Faqs.tsx` 한 파일이다. 열린 항목은 `openId: number | null` 하나로 들고, 같은 항목을 다시 누르면 닫는다. 새 항목을 열면 이전 것은 자동으로 접힌다 — 화면이 짧게 유지되어 목록을 훑던 스크롤 위치가 크게 밀리지 않는다.

**`Table`을 재사용하지 않는다.** `Table`은 "행 = 열들의 나열"이 전제인데 아코디언은 행 아래로 열 구분 없는 본문이 펼쳐진다. 억지로 끼워 넣으면 `colSpan` 트릭이 들어가고, 이후 `Table`을 손볼 때 FAQ 화면까지 확인해야 한다. 대신 `<ul>` 기반 목록을 이 파일 안에 `FaqItem` 컴포넌트로 둔다.

질문 행 전체를 `<button type="button">`으로 만들어 키보드로도 열린다. 답변은 공지와 같이 `whitespace-pre-wrap`으로 줄바꿈을 살린다.

**페이지네이션을 두지 않는다.** FAQ는 훑어 내려가며 찾는 화면이라 페이지를 넘기면 "다음 장에 있나" 확인하러 왕복하게 된다. 분류 탭과 검색이 그 역할을 대신한다.

분류 탭과 검색은 `AdminNotices`의 `PHASE_TABS`와 같은 클라이언트 필터다. 탭은 `[전체]`를 포함해 5개이고, 검색 대상은 질문 + 답변이다. 검색어가 답변에만 걸린 항목도 접힌 채로 보인다 — 자동으로 펼치면 "한 번에 하나만"이라는 규칙과 부딪히고, 검색 결과가 여러 건일 때 어느 것을 펼칠지 정할 근거가 없다.

탭이나 검색어를 바꾸면 `openId`를 `null`로 되돌린다. 필터 때문에 사라진 항목이 열린 상태로 남아 있으면, 필터를 되돌렸을 때 예상치 못한 항목이 펼쳐져 있다.

빈 상태 문구는 검색 중이면 `검색 결과가 없습니다.`, 아니면 `등록된 FAQ가 없습니다.`다.

### 4-2. 관리자 FAQ 관리 `/admin/faqs`

```
FAQ 관리
┌──────────────────────────────────────────────────────────┐
│ [전체][게시중][임시저장]     [검색]        [+ 새 FAQ]    │
│ ──────────────────────────────────────────────────────── │
│ No    질문                  분류      상태    작성자     │
│  4   렌더링은 얼마나…      영상제작  게시중   김관리     │
│  3   음성을 바꿀 수…       영상제작  게시중   김관리     │
│  2   프로젝트를 삭제…      프로젝트  게시중   이운영     │
│  1   결제는 어떻게…        기타      임시저장 김관리     │
│ ──────────────────────────────────────────────────────── │
│                       총 4건   ‹ 1 ›                     │
└──────────────────────────────────────────────────────────┘
     ↓ 행 클릭 / [+ 새 FAQ]
┌─ 모달: FAQ 수정 ──────────────────────────┐
│ 분류      [영상제작 ▾]                    │
│ 질문      [렌더링은 얼마나 걸리나요?   ]  │
│ 답변      [                            ]  │
│           [                            ]  │
│ 정렬 순서 [10]  작을수록 위에 표시됩니다  │
│ ───────────────────────────────────────── │
│ [삭제]             [임시저장] [게시하기]  │
└───────────────────────────────────────────┘
```

`AdminNotices.tsx`의 구조를 그대로 따른다 — 상태 탭, 검색, `Table` + `TableFooter`(10건), 등록·수정 공용 모달, `window.confirm` 후 소프트 삭제, 새 항목 모달에는 `[삭제]`가 없다.

공지와 다른 점은 두 가지다.

첫째, 상태 탭이 `[전체][게시중][임시저장]` 셋뿐이고 `status` 값을 그대로 비교한다. 파생 상태 계산이 없으므로 `localNowIso()`도 쓰지 않는다.

둘째, 첫 컬럼이 `badgedSeqColumn`이 아니라 `seqColumn`이다 — 상단 고정 개념이 없어 순번 바깥에 놓일 행이 없다.

**`sort_order` 값은 목록에 보여주지 않는다.** 관리자가 조정하는 값이라 목록에 두는 안(案)도 검토했으나, 그러면 이 표의 첫 컬럼만 다른 관리자 화면과 다른 것(헤더 이름·폭·의미)이 되어 화면을 옮겨 다닐 때 걸린다. `No`는 `AdminUsers`·`AdminProjects`·`Projects`와 같은 `seqColumn`을 그대로 쓴다. 현재 값은 행을 클릭해 모달에서 확인하고, 모달 도움말에 `10, 20, 30`처럼 띄워 쓰면 사이에 끼워 넣기 쉽다고 안내한다.

`seqColumn`은 내림차순(`total - 오프셋`)이라 FAQ 목록에서는 맨 아래가 1번이 된다. 오름차순 목록에 내림차순 번호가 붙는 셈이지만, 순번 열의 규칙을 화면마다 다르게 두지 않는 편을 택했다.

`[임시저장]`은 `status = 'DRAFT'`로, `[게시하기]`는 `status = 'PUBLISHED'`로 저장한다.

### 4-3. 경로 이름

화면 경로는 API와 같이 복수형 `/faqs`·`/admin/faqs`로 통일한다. `/faq`가 더 흔한 표기이지만, 공지가 `/notices`·`/admin/notices`인 것과 규칙이 갈리면 "이 도메인은 어느 쪽이었더라"를 매번 확인하게 된다.

### 4-4. 신규·수정 파일

| 파일 | 내용 |
|---|---|
| `app/models/faq.py` | `Faq` 모델 |
| `app/constants.py` | `FaqCategory` · `FaqStatus` 추가 |
| `app/queries/faqs.sql` | 쿼리 6개 |
| `app/api/faqs.py` | 사용자 API |
| `app/api/admin_faqs.py` | 관리자 API |
| `app/main.py` | 라우터 2개 등록 |
| `web/src/lib/faqs.ts` | `Faq` 타입 + `faqs.list()` + `FAQ_CATEGORY_LABEL` |
| `web/src/pages/faqs/Faqs.tsx` | 사용자 아코디언 목록 |
| `web/src/pages/admin/AdminFaqs.tsx` | 관리자 목록 + 등록/수정 모달 |
| `web/src/lib/admin.ts` | `AdminFaq` 타입 + `FaqPayload` + `adminFaqs` 추가 (`adminNotices` 옆) |
| `web/src/lib/nav.ts` | `❓ FAQ`(`/faqs`), `📖 FAQ 관리`(`/admin/faqs`, adminOnly) |
| `web/src/App.tsx` | 두 라우트 등록 (`/admin/faqs`는 `RequireAdmin` 안) |
| `docs/schema.sql` | `faqs` DDL 추가 (파일 머리말의 "테이블을 추가할 때마다 갱신" 규칙) |

`FAQ_CATEGORY_LABEL`은 코드값 → 한글 라벨 매핑이다. 사용자 화면의 분류 탭, 관리자 목록의 분류 셀, 관리자 모달의 셀렉트가 모두 이 하나를 읽으므로 라벨이 세 곳에서 어긋날 수 없다.

메뉴 순서는 일반 항목이 `대시보드 · 프로젝트 · 공지사항 · FAQ · 설정`, 관리자 항목이 `가입 승인 · 사용자 관리 · 전체 프로젝트 · 공지 관리 · FAQ 관리 · 시스템 설정`이다.

`docs/schema.sql`은 머리말에 "테이블을 추가/변경할 때마다 이 파일을 갱신한다"고 적혀 있지만 현재 `users`·`refresh_tokens` 두 개만 있고 그 뒤에 추가된 테이블들이 빠져 있다. 이 작업에서는 `faqs`만 규칙대로 추가하고, 밀린 나머지 테이블 backfill은 범위 밖으로 둔다 — 이 기능과 무관한 변경이 섞이면 리뷰가 어려워진다.

## 5. 에러 처리

**백엔드**는 기존 방식 그대로다 — 도메인 오류는 `Errors.*`로 던지고 `main.py`의 `app_error_handler`가 `{code, message}`로 응답한다.

**프론트엔드**

| 상황 | 처리 |
|---|---|
| 목록 조회 실패 | `FormError`로 메시지 표시, 목록 영역은 그리지 않음 |
| 저장·삭제 실패 | 모달 안에 `FormError` 표시, 모달은 닫지 않음 |

공지에 있던 "조용히 넘어가는" 경로(읽음 처리·배지·팝업)가 FAQ에는 없다. 두 요청 모두 사용자가 방금 한 행동의 결과라 실패를 감추면 안 된다.

## 6. 테스트

**백엔드** (`tests/`, 기존 conftest의 testcontainers 기반 DB 픽스처 사용)

`tests/test_faqs.py` — 사용자 API

- 게시중 FAQ만 목록에 나온다 (임시저장 · 삭제된 항목은 빠진다)
- 정렬이 `sort_order ASC, id ASC`다 (같은 `sort_order`면 먼저 등록된 것이 위)
- 응답에 `answer`와 `category`가 들어 있다
- 비로그인 요청은 401

`tests/test_admin_faqs.py` — 관리자 API

- MEMBER 권한은 403
- 생성은 201이고 `id`를 돌려준다
- 공백뿐인 `question`·`answer`는 422
- `category`에 코드값 아닌 값을 넣으면 422
- 음수 `sort_order`는 422
- 수정이 `question`·`answer`·`category`·`status`·`sort_order`를 모두 반영한다
- 삭제는 행을 지우지 않고 `deleted_at`/`deleted_by`만 채우며, 이후 관리자 목록과 사용자 목록 양쪽에서 빠진다
- 없는 id로 수정·삭제하면 404

`tests/test_alembic_migration.py`는 이미 마이그레이션 왕복을 검증하므로 새 테이블이 자동으로 범위에 들어온다. 새 리비전 추가 후 이 테스트가 통과하는지 확인한다.

**프론트엔드**는 이 프로젝트에 자동화 테스트가 없다. 수동 확인 항목만 남긴다.

- 관리자로 FAQ를 게시 → 일반 사용자 화면 목록에 정렬 순서대로 나온다
- 임시저장한 FAQ는 사용자 화면에 안 보인다
- 질문을 열면 이전에 열린 항목이 접힌다
- 분류 탭을 바꾸면 열린 항목이 접히고, 해당 분류만 남는다
- 답변에만 있는 단어로 검색해도 그 항목이 목록에 남는다
- 답변의 줄바꿈이 그대로 보인다
- 다크모드에서 탭 · 아코디언 경계선 · 상태 뱃지 색이 깨지지 않는다

## 7. 구현 순서

1. 모델(`faq.py`) + `FaqCategory`·`FaqStatus` 상수 + alembic 리비전
2. `faqs.sql` 쿼리
3. 관리자 API + 테스트
4. 사용자 API + 테스트
5. 프론트 lib(`faqs.ts`, `admin.ts`) + 라우트/메뉴
6. 관리자 화면 → 사용자 화면

공지와 같은 이유로 관리자 화면을 먼저 만든다 — 사용자 화면을 확인할 FAQ 데이터를 UI로 넣을 수 있어야 한다.
