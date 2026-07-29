import type { ReactNode } from 'react'
import type { Column } from './Table'

// 자릿수가 늘어도(9 → 10 → 100) 열 폭이 흔들리지 않게 고정한다.
// 두 순번 열이 같은 값을 쓰므로 화면이 달라도 No 열의 폭은 항상 같다.
// 80인 이유: 번호만 보면 더 좁아도 되지만, 배지('공지')가 들어가는 열이 여백까지
// 합쳐 70을 넘겨 혼자 넓어졌다. 가장 넓은 내용에 맞춰야 화면끼리 폭이 맞는다.
const WIDTH = 80

// 전체 기준 연속 내림차순 순번. 목록이 최신순이므로 맨 위(최신)가 가장 큰 번호를 갖고,
// 페이지를 넘겨도 번호가 이어진다(2페이지 첫 줄 = total - pageSize).
// 새 항목이 앞에 추가돼도 기존 항목의 번호는 그대로다 — 오름차순이면 전부 밀린다.
export function seqColumn<T>(total: number, page: number, pageSize: number): Column<T> {
  return {
    header: 'No',
    cell: (_row, index) => total - ((page - 1) * pageSize + index),
    align: 'center',
    width: WIDTH,
  }
}

// 일부 행이 순번 바깥에 있는 목록용(예: 상단 고정 공지). 제외된 행은 번호 대신
// badge를 보여주고, 나머지 행에만 이어지는 내림차순 번호를 준다.
//
// 페이지가 아니라 목록 전체(rows)를 받는 이유: 제외된 행이 앞에 몇 개 끼어 있는지는
// 페이지 인덱스만으로 알 수 없다. rows에는 필터링된 전체 목록을 넘기고 표에는 그
// 배열을 잘라낸 페이지를 넘겨야 번호가 페이지를 넘어 이어진다(행 객체가 같은
// 참조여야 위치를 찾을 수 있다).
export function badgedSeqColumn<T>(
  rows: T[],
  isBadged: (row: T) => boolean,
  badge: ReactNode,
): Column<T> {
  const numbered = rows.filter((row) => !isBadged(row))
  return {
    header: 'No',
    cell: (row) => (isBadged(row) ? badge : numbered.length - numbered.indexOf(row)),
    align: 'center',
    width: WIDTH,
  }
}
