import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { PinnedBadge } from '../../components/PinnedBadge'
import { badgedSeqColumn } from '../../components/table/seqColumn'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { useClientPagination } from '../../components/table/useClientPagination'
import { ApiError } from '../../lib/api'
import { isY, notices, type Notice } from '../../lib/notices'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

// 백엔드가 로컬 naive ISO 문자열을 준다. Date로 파싱하면 타임존 보정이
// 끼어드니 문자열을 그대로 자른다.
function formatDate(iso: string) {
  return iso.slice(0, 10)
}

function NewBadge() {
  return (
    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-500/15 dark:text-red-300">
      NEW
    </span>
  )
}

export function Notices() {
  const [rows, setRows] = useState<Notice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // 검색어와 페이지를 URL에 둔다 — 상세를 보고 돌아왔을 때 보던 자리가 그대로 살아 있다.
  // 기본값(빈 검색어·1페이지)은 아예 적지 않아 주소가 지저분해지지 않는다.
  const [params, setParams] = useSearchParams()
  const { search } = useLocation()
  const navigate = useNavigate()

  const query = params.get('q') ?? ''
  const page = Number(params.get('page')) || 1

  // replace인 이유: 페이지를 넘길 때마다 히스토리가 쌓이면 목록을 빠져나가는 데
  // 뒤로가기를 그만큼 눌러야 한다.
  const patch = (next: { q?: string; page?: number }) => {
    const merged = new URLSearchParams(params)
    if (next.q !== undefined) {
      if (next.q) merged.set('q', next.q)
      else merged.delete('q')
    }
    if (next.page !== undefined) {
      if (next.page > 1) merged.set('page', String(next.page))
      else merged.delete('page')
    }
    setParams(merged, { replace: true })
  }

  useEffect(() => {
    notices
      .list()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter(
    (n) =>
      !keyword ||
      n.title.toLowerCase().includes(keyword) ||
      n.body.toLowerCase().includes(keyword),
  )

  // safePage를 다시 받는 이유: URL에 범위 밖 숫자(?page=99)가 적혀 있어도 표는
  // 마지막 페이지를 그린다. 페이지 표시가 표와 어긋나지 않게 보정된 값을 쓴다.
  const {
    page: safePage,
    setPage,
    pageSize,
    setPageSize,
    totalPages,
    total,
    pageRows,
  } = useClientPagination(filteredRows, { page, setPage: (next) => patch({ page: next }) })

  const columns: Column<Notice>[] = [
    // 고정 공지는 최신순 일련번호 바깥에 있다. 번호를 붙이면 목록의 번호가
    // 뒤죽박죽이 되므로 '공지' 배지를 놓고, 나머지에만 이어지는 번호를 준다.
    badgedSeqColumn<Notice>(filteredRows, (n) => isY(n.pinned_yn), <PinnedBadge />),
    {
      header: '제목',
      cell: (notice) => (
        <span className="flex items-center gap-2">
          <span className="truncate">{notice.title}</span>
          {!notice.is_read && <NewBadge />}
        </span>
      ),
    },
    { header: '게시일', cell: (notice) => formatDate(notice.starts_at), align: 'center' },
  ]

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <input
          type="search"
          value={query}
          onChange={(e) => patch({ q: e.target.value, page: 1 })}
          placeholder="제목 또는 내용 검색"
          className="w-64 rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
        />
      </div>

      {error && (
        <div className="mb-4">
          <FormError message={error} />
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-sm text-fg-muted">불러오는 중…</div>
      ) : error ? null : (
        <>
          <Table
            columns={columns}
            rows={pageRows}
            rowKey={(n) => n.id}
            // 지금 보던 검색어·페이지를 함께 넘긴다 — 상세의 [목록으로]가 이 자리로 되돌린다.
            onRowClick={(notice) => navigate(`/notices/${notice.id}`, { state: { from: search } })}
            empty={keyword ? '검색 결과가 없습니다.' : '등록된 공지가 없습니다.'}
          />
          <TableFooter
            page={safePage}
            totalPages={totalPages}
            onChange={setPage}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
        </>
      )}
    </div>
  )
}
