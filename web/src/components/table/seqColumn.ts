import type { Column } from './Table'

// 전체 기준 연속 내림차순 순번. 목록이 최신순이므로 맨 위(최신)가 가장 큰 번호를 갖고,
// 페이지를 넘겨도 번호가 이어진다(2페이지 첫 줄 = total - pageSize).
// 새 항목이 앞에 추가돼도 기존 항목의 번호는 그대로다 — 오름차순이면 전부 밀린다.
export function seqColumn<T>(total: number, page: number, pageSize: number): Column<T> {
  return {
    header: '순번',
    cell: (_row, index) => total - ((page - 1) * pageSize + index),
    align: 'center',
  }
}
