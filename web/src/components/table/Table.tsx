import type { ReactNode } from 'react'

export type Align = 'left' | 'center' | 'right'

export type Column<T> = {
  header: string
  // 셀 내용을 직접 그린다 — 배지·버튼도 여기서.
  // index는 이 페이지 안에서의 0-based 위치다. 전체 기준 순번이 필요하면
  // 쓰는 쪽이 페이지 오프셋을 더한다(표는 페이징을 모른다).
  cell: (row: T, index: number) => ReactNode
  align?: Align // 기본 left
}

const ALIGN_CLASS: Record<Align, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
}

// 책임은 하나: 스타일된 표를 그린다. 데이터를 가져오지 않고, 정렬·페이징도 없고,
// 무슨 도메인인지 모른다. rows가 비면 헤더는 그대로 두고 데이터 영역에 empty를 보여준다.
export function Table<T>({
  columns,
  rows,
  rowKey,
  empty,
  onRowClick,
  headerAlign,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  empty?: ReactNode
  onRowClick?: (row: T) => void // 주면 행 전체가 클릭 대상이 된다(커서·hover 포함)
  headerAlign?: Align // 헤더는 기본 중앙정렬. 다르게 할 때만 준다(예: 셀과 맞춰 우측)
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            {columns.map((col) => (
              <th
                key={col.header}
                className={`px-4 py-3 font-medium ${ALIGN_CLASS[headerAlign ?? 'center']}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            // 데이터가 없어도 헤더는 남기고, 데이터 영역에만 안내 문구를 채운다.
            <tr>
              <td colSpan={columns.length} className="px-4 py-10 text-center text-sm text-slate-500">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={`border-b border-slate-100 last:border-0 ${
                  onRowClick ? 'cursor-pointer hover:bg-slate-50' : ''
                }`}
              >
                {columns.map((col) => (
                  <td
                    key={col.header}
                    className={`px-4 py-3 text-slate-700 ${ALIGN_CLASS[col.align ?? 'left']}`}
                  >
                    {col.cell(row, index)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
