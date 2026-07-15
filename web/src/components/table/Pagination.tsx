// 페이지가 하나뿐이거나 건수가 0이어도 항상 표시한다(양쪽 버튼은 비활성).
// 도메인을 모르고 숫자만 안다. 바깥 여백·정렬은 두지 않는다 — 배치는 쓰는 쪽이 정한다.
export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
}) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <button
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        aria-label="이전 페이지"
        className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
      >
        {'<<'}
      </button>
      <span className="text-slate-600">
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        aria-label="다음 페이지"
        className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
      >
        {'>>'}
      </button>
    </div>
  )
}
