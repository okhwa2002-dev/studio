import { useEffect, useState } from 'react'
import { DEFAULT_PAGE_SIZE } from './PageSizeSelect'

// 전량을 받아 프론트가 잘라 보여주는 목록(감사 로그를 뺀 여섯 화면)의 공통 계산.
// 화면마다 복붙되던 세 줄(useState(1) · totalPages · slice)에 더해, 페이지 크기가
// 사용자 선택으로 바뀌면서 생긴 보정 규칙 둘을 한곳에 모은다.
//
// seqColumn이 total과 pageSize를 함께 받으므로 total도 돌려준다 — 화면이 rows.length를
// 두 번 세지 않게 한다.
export function useClientPagination<T>(rows: T[]) {
  const [page, setPage] = useState(1)
  // 리터럴 20으로 좁혀지면 50·100을 넣을 수 없다. number로 못박는다.
  const [pageSize, setPageSizeState] = useState<number>(DEFAULT_PAGE_SIZE)

  const total = rows.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  // 행이 줄어 지금 페이지가 사라지는 경우를 막는다(마지막 페이지의 마지막 항목을
  // 지우고 목록을 다시 부르는 상황). 렌더에서 먼저 보정해야 빈 표가 한 프레임
  // 스쳐 보이지 않는다.
  const safePage = Math.min(page, totalPages)

  // 상태에도 써 넣는다. 화면에만 보정하고 두면 목록이 다시 늘었을 때 예전 페이지
  // 번호가 되살아난다.
  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  // 크기를 줄이면 있던 페이지가 통째로 사라지므로 언제나 1페이지로 돌아간다.
  // 필터를 바꿀 때의 setPage(1)은 화면이 그대로 들고 있다 — 그쪽은 아직 유효한
  // 페이지를 굳이 되돌리는 규칙이라 위의 범위 보정으로는 표현되지 않는다.
  const setPageSize = (size: number) => {
    setPageSizeState(size)
    setPage(1)
  }

  return {
    page: safePage,
    setPage,
    pageSize,
    setPageSize,
    totalPages,
    total,
    pageRows: rows.slice((safePage - 1) * pageSize, safePage * pageSize),
  }
}
