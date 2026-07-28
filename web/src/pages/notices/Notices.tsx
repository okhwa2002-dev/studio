import { useEffect, useState } from 'react'
import { FormError } from '../../components/FormError'
import { Modal } from '../../components/Modal'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { ApiError } from '../../lib/api'
import { isY, notices, type Notice } from '../../lib/notices'
import { useUnreadNotices } from '../../lib/unreadNotices'

const PAGE_SIZE = 10
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

function NoticeDetailModal({ notice, onClose }: { notice: Notice; onClose: () => void }) {
  return (
    <Modal title={notice.title} onClose={onClose}>
      <div className="text-xs text-fg-muted">{formatDate(notice.starts_at)}</div>
      {/* 본문은 일반 텍스트다. 줄바꿈을 살려서 그대로 보여준다. */}
      <p className="mt-3 border-t border-line-subtle pt-3 text-sm whitespace-pre-wrap text-fg-body">
        {notice.body}
      </p>
    </Modal>
  )
}

export function Notices() {
  const [rows, setRows] = useState<Notice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Notice | null>(null)
  const { refresh } = useUnreadNotices()

  useEffect(() => {
    notices
      .list()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  const open = (notice: Notice) => {
    setSelected(notice)
    if (notice.is_read) return
    // 읽음 처리는 부가 정보다. 실패해도 본문은 이미 열려 있으므로 조용히 넘어가고,
    // NEW 배지가 남았다가 다음 열람 때 다시 시도된다.
    // 거절 핸들러를 then의 두 번째 인자로 두는 것은, 성공 콜백 안에서 나는 예외까지
    // 함께 삼키지 않기 위해서다(체인 끝의 .catch였다면 그것까지 먹는다).
    notices.markRead(notice.id).then(
      () => {
        setRows((prev) => prev.map((n) => (n.id === notice.id ? { ...n, is_read: true } : n)))
        // 같은 화면에 머문 채 읽어도 상단바 배지가 즉시 줄어든다.
        refresh()
      },
      () => {},
    )
  }

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter(
    (n) =>
      !keyword ||
      n.title.toLowerCase().includes(keyword) ||
      n.body.toLowerCase().includes(keyword),
  )

  // 고정 공지는 최신순 일련번호 바깥에 있다. 번호를 붙이면 목록의 번호가
  // 뒤죽박죽이 되므로 '-'를 보여주고, 나머지에만 이어지는 번호를 준다.
  const unpinnedTotal = filteredRows.filter((n) => !isY(n.pinned_yn)).length

  const columns: Column<Notice>[] = [
    {
      header: 'No',
      align: 'center',
      cell: (notice) => {
        if (isY(notice.pinned_yn)) return '-'
        const order = filteredRows.filter((n) => !isY(n.pinned_yn)).indexOf(notice)
        return unpinnedTotal - order
      },
    },
    {
      header: '제목',
      cell: (notice) => (
        <span className="flex items-center gap-2">
          {isY(notice.pinned_yn) && <span aria-label="고정">📌</span>}
          <span className="truncate">{notice.title}</span>
          {!notice.is_read && <NewBadge />}
        </span>
      ),
    },
    { header: '게시일', cell: (notice) => formatDate(notice.starts_at), align: 'center' },
  ]

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE))
  const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
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
      ) : (
        <>
          <Table
            columns={columns}
            rows={pageRows}
            rowKey={(n) => n.id}
            onRowClick={open}
            empty={keyword ? '검색 결과가 없습니다.' : '등록된 공지가 없습니다.'}
          />
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={filteredRows.length}
          />
        </>
      )}

      {selected && <NoticeDetailModal notice={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
