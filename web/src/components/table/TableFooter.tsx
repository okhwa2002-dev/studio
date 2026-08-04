import { PageSizeSelect } from './PageSizeSelect'
import { Pagination } from './Pagination'

// 표 아래 줄의 배치만 책임진다. 페이지 이동은 Pagination에, 건수 선택은 PageSizeSelect에
// 그대로 위임하고, 여기서는 "좌측 건수 선택 · 가운데 버튼 · 우측 건수" 규칙만 안다.
// 3열 그리드라 버튼이 양옆 폭에 밀리지 않고 항상 정중앙에 온다(양 끝 칸이 폭을 나눠 가짐).
export function TableFooter({
  page,
  totalPages,
  onChange,
  total,
  pageSize,
  onPageSizeChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
  total: number // 페이지가 아니라 전체 행 수
  // 화면을 하나씩 옮기는 동안만 옵셔널이다. 전부 옮기면 필수로 바꿔, 빠뜨린 화면을
  // 타입 검사가 잡게 한다.
  pageSize?: number
  onPageSizeChange?: (size: number) => void
}) {
  return (
    <div className="mt-4 grid grid-cols-3 items-center text-sm text-fg-muted">
      <div>
        {pageSize !== undefined && onPageSizeChange && (
          <PageSizeSelect value={pageSize} onChange={onPageSizeChange} />
        )}
      </div>
      <div className="flex justify-center">
        <Pagination page={page} totalPages={totalPages} onChange={onChange} />
      </div>
      <div className="text-right">전체 {total}건</div>
    </div>
  )
}
