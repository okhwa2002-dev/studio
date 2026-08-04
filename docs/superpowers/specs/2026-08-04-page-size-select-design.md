# 페이지당 건수 선택 설계 (Design Spec)

- **작성일:** 2026-08-04
- **한 줄 요약:** 목록 화면 7곳에 하드코딩된 페이지 크기(`PAGE_SIZE = 10` / `50`)를 사용자가 **20 · 50 · 100** 중에서 고를 수 있게 한다. 셀렉터는 `TableFooter` 왼쪽 빈 칸에 한 번만 넣고, 클라이언트 페이징 6개 화면의 중복된 페이징 계산은 `useClientPagination` 훅으로 모은다.

---

## 1. 배경 & 목표

### 문제

페이지당 건수가 소스에 상수로 박혀 있어 사용자가 바꿀 수 없다.

- **서버 페이징 1곳** — [`app/api/admin_audit_logs.py`](../../../app/api/admin_audit_logs.py)의 `size: int = Query(50, ge=1, le=200)`. API는 이미 `size`를 받지만 프론트가 `PAGE_SIZE = 50` 상수만 보낸다.
- **클라이언트 페이징 6곳** — 전량을 받아 프론트가 `slice`한다. 전부 `PAGE_SIZE = 10` 고정.

건수가 적은 화면에서는 10건이 답답하고, 감사 로그처럼 훑어보는 화면에서는 50건도 부족하다. 판단은 그때그때 사용자에게 있는데 코드가 대신 정해 두고 있다.

### 목표

목록 화면 어디서나 표 아래에서 페이지당 건수를 고른다. 7개 화면이 **같은 자리, 같은 선택지, 같은 동작**을 갖는다.

### 이번 범위

`PageSizeSelect` 컴포넌트 · `useClientPagination` 훅 · `TableFooter` props 확장 · 7개 화면 적용 · 감사 로그 API 기본값 정렬.

### 결정 사항

| 항목 | 결정 | 이유 |
|------|------|------|
| 적용 범위 | 7개 화면 전부 | 공통 컴포넌트에 한 번 넣으면 되고, 화면마다 UX가 갈리지 않는다 |
| 선택지 | 20 · 50 · 100 | 10은 뺀다. 세 단계면 "조금 / 보통 / 많이"가 충분히 갈린다 |
| 기본값 | 20 (전 화면 통일) | 화면마다 10 / 50으로 갈려 있던 것을 하나로 맞춘다. 감사 로그만 50으로 두는 안을 한 번 넣었다가 되돌렸다 — 화면마다 기본값이 다르면 "이 화면은 왜 다르지"를 설명할 곳이 코드 주석밖에 없고, 많이 보고 싶은 사람은 셀렉터를 올리면 된다. 그 화면이 특별히 많은 건수를 원한다는 관찰은 유효하지만, 답은 기본값 예외가 아니라 선택지(100)다 |
| 상태 유지 | 화면 안에서만 (`useState`) | 화면을 떠나거나 새로고침하면 20으로 돌아간다. 기존 `page` 상태와 같은 수명이라 규칙이 하나뿐이다 |
| UI 위치 | `TableFooter` 왼쪽 칸 | 이미 비어 있는 칸이라 3열 그리드를 건드리지 않고, 페이지 버튼의 정중앙 정렬이 유지된다 |

### 비범위 (YAGNI)

- **localStorage · URL 저장** — 선택을 화면 밖으로 들고 다니지 않는다. 필요해지면 훅 안쪽만 바꾸면 되므로 지금 결정하지 않아도 손해가 없다.
- **화면별 다른 선택지** — 7곳이 같은 `[20, 50, 100]`을 쓴다.
- **서버 페이징으로의 전환** — 클라이언트 페이징 6곳은 그대로 전량을 받는다. 100건씩 보기가 이 판단을 바꾸지 않는다(이미 전량이 메모리에 있다).
- **`PaginatedTable` 통합 컴포넌트** — 화면마다 필터·컬럼 구성이 달라 추상화가 샌다.

---

## 2. 설계

### 2.1 `PageSizeSelect` — 숫자만 아는 셀렉터

새 파일 `web/src/components/table/PageSizeSelect.tsx`.

```
PageSizeSelect({ value: number, onChange: (n: number) => void })
```

`Pagination.tsx`와 같은 방침이다 — 도메인을 모르고 숫자만 안다. 바깥 여백·정렬은 두지 않고 배치는 쓰는 쪽(`TableFooter`)이 정한다.

선택지 `[20, 50, 100]`은 이 파일의 상수(`PAGE_SIZE_OPTIONS`)로 두고 export한다. 기본값 `DEFAULT_PAGE_SIZE`(20)는 훅(`useClientPagination`)과 감사 로그 화면이 모두 참조하므로, 목록과 기본값이 한 파일에만 있다 — 바꾸려면 이 파일 한 곳만 고치면 7개 화면이 함께 움직인다.

라벨은 `20건씩`. 표시 요소(`<select>`)의 테두리·글자 크기는 옆의 `Pagination` 버튼과 같은 클래스를 쓴다.

### 2.2 `useClientPagination` — 클라이언트 페이징 6곳의 공통 계산

새 파일 `web/src/components/table/useClientPagination.ts`. `seqColumn.ts`가 그렇듯 표 컴포넌트 옆에 둔다 — `TableFooter`와 짝으로만 쓰인다. 파일명은 `components/table/`의 다른 파일들처럼 단일 export명(`useClientPagination`)과 맞춘다(최초에는 `usePagination.ts`였다가 최종 브랜치 리뷰에서 rename됐다).

```
useClientPagination<T>(rows: T[]) → {
  page, setPage,          // 1-base, 보정된 값
  pageSize, setPageSize,
  totalPages,
  pageRows,               // rows를 잘라낸 현재 페이지
  total,                  // rows.length — TableFooter의 "전체 N건"
}
```

지금 6개 화면이 똑같은 네 줄을 복붙하고 있다.

```ts
const [page, setPage] = useState(1)
const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE))
const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
```

여기에 `pageSize`가 얹히면 "크기를 바꾸면 1페이지로"라는 새 규칙이 6곳에 흩어진다. 훅이 그 규칙을 한 곳에 둔다.

**규칙 1 — `setPageSize`는 항상 `page`를 1로 되돌린다.** 100건씩 보다가 20건씩으로 줄이면 있던 5페이지가 사라져 빈 표가 된다.

**규칙 2 — `rows`가 줄어 `page`가 범위를 벗어나면 마지막 페이지로 당긴다.** 렌더 중에 `safePage = Math.min(page, totalPages)`를 계산해 그 값으로 자르고(빈 표가 한 프레임 스쳐 보이지 않는다), `useEffect`로 상태에도 써 넣는다. 상태를 그대로 두면 목록이 다시 늘었을 때 예전 페이지 번호가 되살아난다.

이건 **필터 변경 시 1페이지 복귀를 대신하는 것이 아니다.** 그쪽은 유효한 페이지를 굳이 1로 되돌리는 규칙이라 클램프로 표현되지 않는다. 6개 화면이 이미 검색어·탭 핸들러에서 `setPage(1)`을 부르고 있으므로(`Notices.tsx:110`, `AdminFaqs.tsx:245`·`263`, `AdminNotices.tsx:293`·`311`, `AdminUsers.tsx:450`, `AdminProjects.tsx`의 딥링크 `useEffect`, `Projects.tsx`·`AdminUsers.tsx`의 `load()`) **그 호출들은 그대로 둔다.**

클램프가 실제로 막는 것은 행이 줄어드는 경우다 — 마지막 페이지의 마지막 FAQ를 지우고 `load()`가 돌면 지금은 빈 표가 남는다. 어느 화면도 이걸 처리하지 않는다.

### 2.3 `TableFooter` — 왼쪽 칸에 셀렉터

`pageSize: number`와 `onPageSizeChange: (n: number) => void`를 **필수** props로 받는다. 옵셔널로 두면 빠뜨린 화면을 아무도 잡아 주지 않는데, 7개 화면 전부가 쓰기로 했으므로 타입 검사가 누락을 잡게 한다.

지금 자리채움용으로 있는 `<div />`가 셀렉터 자리가 된다. 3열 그리드는 그대로라 페이지 버튼은 계속 정중앙이다.

```
[20건씩 ▾]          << 1 / 5 >>            전체 92건
```

### 2.4 순번(No) 열

`seqColumn(total, page, pageSize)`는 이미 `pageSize`를 인자로 받으므로 상수 대신 훅의 `pageSize`를 넘기면 그대로 이어지는 번호가 나온다.

`badgedSeqColumn(rows, isBadged, badge)`는 페이지가 아니라 목록 전체를 받아 번호를 매기므로 `pageSize`와 무관하다 — `Notices` · `AdminNotices`는 이 열을 건드리지 않는다.

### 2.5 감사 로그 — 서버 페이징이라 훅을 쓰지 않는다

[`AdminAuditLogs.tsx`](../../../web/src/pages/admin/AdminAuditLogs.tsx)는 필터·페이지를 URL에 두고 서버가 잘라 준 결과를 그대로 그린다. `useClientPagination`은 배열을 자르는 훅이라 맞지 않는다.

- `const PAGE_SIZE = 50` → `const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)`. 페이징 방식은 달라도 기본값은 여섯 화면과 같은 상수를 본다.
- `pageSize`가 `load`의 `useCallback` 의존성에 들어간다 — 바뀌면 다시 조회한다.
- 크기를 바꿀 때 `setFilter({})`를 함께 호출한다. 기존 `setFilter`는 `page`가 patch에 없으면 URL에서 `page`를 지우므로, 1페이지 복귀 규칙이 필터 변경과 똑같이 처리된다.

`pageSize`를 URL이 아니라 `useState`에 두는 이유는 "화면 안에서만 유지" 결정 그대로다. 필터는 링크로 넘길 값이지만 페이지 크기는 보는 사람의 취향이다.

### 2.6 백엔드 — 기본값만 맞춘다

[`app/api/admin_audit_logs.py`](../../../app/api/admin_audit_logs.py)의 `size` 기본값을 `50 → 20`으로 바꿔 화면 기본값과 맞춘다. 프론트가 항상 `size`를 명시하므로 실동작에는 영향이 없고, API 문서상 기본값을 화면과 맞추는 목적이다.

`_MAX_SIZE = 200`은 그대로 둔다. 최대 선택지 100에 여유가 있고, `test_size_over_limit_is_422`가 201로 상한을 검사한다.

---

## 3. 화면별 변경

| 화면 | 훅에 넘길 배열 | 순번 열 |
|------|----------------|---------|
| [`Projects.tsx`](../../../web/src/pages/projects/Projects.tsx) | `rows` | `seqColumn`에 `pageSize` 전달 |
| [`AdminProjects.tsx`](../../../web/src/pages/admin/AdminProjects.tsx) | `filteredRows` | `seqColumn`에 `pageSize` 전달 |
| [`AdminUsers.tsx`](../../../web/src/pages/admin/AdminUsers.tsx) | `filteredRows` | `seqColumn`에 `pageSize` 전달 |
| [`AdminFaqs.tsx`](../../../web/src/pages/admin/AdminFaqs.tsx) | `filteredRows` | `seqColumn`에 `pageSize` 전달 |
| [`AdminNotices.tsx`](../../../web/src/pages/admin/AdminNotices.tsx) | `filteredRows` | `badgedSeqColumn` — 변경 없음 |
| [`Notices.tsx`](../../../web/src/pages/notices/Notices.tsx) | `filteredRows` | `badgedSeqColumn` — 변경 없음 |
| [`AdminAuditLogs.tsx`](../../../web/src/pages/admin/AdminAuditLogs.tsx) | — (서버 페이징) | 2.5 참조 |

여섯 화면 모두 `const PAGE_SIZE = 10` 상수와 `useState(1)` · `totalPages` · `pageRows` 세 줄이 사라진다. **기존 `setPage(1)` 호출은 전부 유지한다**(2.2 규칙 2 참조) — 훅이 같은 이름의 `setPage`를 돌려주므로 호출부는 그대로 컴파일된다.

---

## 4. 검증

이 저장소의 `npm test`는 백엔드 pytest를 돌리고, 프론트엔드 테스트 프레임워크는 없다. 따라서 검증은 타입 검사 · 린트 · 수동 확인으로 한다.

- `npm run build` — `tsc -b`가 `TableFooter`의 새 필수 props 누락과 `seqColumn` 인자 타입을 잡는다. 7개 화면을 빠짐없이 고쳤다는 근거가 여기서 나온다.
- `npm run lint` — oxlint. 훅 의존성 배열과 미사용 상수(`PAGE_SIZE` 잔재)를 잡는다.
- `uv run pytest tests/test_api_audit_logs.py` — 기본값 변경이 기존 페이징·상한 테스트를 깨지 않는지 확인.
- **수동 확인 2가지**
  - 감사 로그(서버 페이징): 3페이지에서 100건씩으로 변경 → 1페이지로 돌아가고 재조회된다. No 열 번호가 이어진다.
  - 관리자 사용자(클라이언트 페이징): 100건씩에서 마지막 페이지로 간 뒤 20건씩으로 축소 → 빈 표가 아니라 1페이지가 보인다.
  - 관리자 FAQ(클램프): 마지막 페이지에 항목이 하나만 남게 한 뒤 그것을 삭제 → 빈 표가 아니라 직전 페이지가 보인다.

---

## 5. 열린 질문

없음.
