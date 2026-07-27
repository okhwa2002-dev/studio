import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { seqColumn } from '../../components/table/seqColumn'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { adminProjects, type AdminProject } from '../../lib/admin'
import { ApiError } from '../../lib/api'
import { STAGE_LABEL, type ProjectStatus } from '../../lib/projects'

// 'ALL'은 상태 무관 전체를 뜻하는 UI 전용 값이다(백엔드 필터는 없다 — 목록을 한 번에 받아 클라이언트에서 거른다).
type StatusFilter = ProjectStatus | 'ALL'

const STATUS_TABS: { status: StatusFilter; label: string }[] = [
  { status: 'ALL', label: '전체' },
  { status: 'DRAFT', label: '작성 중' },
  { status: 'REVIEW', label: '검토 중' },
  { status: 'DONE', label: '완료' },
]

const PROJECT_STATUS_LABEL: Record<ProjectStatus, string> = {
  DRAFT: '작성 중',
  REVIEW: '검토 중',
  DONE: '완료',
}

const PAGE_SIZE = 10
const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

function formatDate(iso: string) {
  return iso.slice(0, 10)
}

export function AdminProjects() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [rows, setRows] = useState<AdminProject[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminProjects
      .list()
      .then((data) => {
        setRows(data)
        setPage(1)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter((p) => {
    if (status !== 'ALL' && p.status !== status) return false
    if (!keyword) return true
    return (
      p.title.toLowerCase().includes(keyword) ||
      p.topic.toLowerCase().includes(keyword) ||
      p.owner_name.toLowerCase().includes(keyword) ||
      p.owner_email.toLowerCase().includes(keyword)
    )
  })

  const columns: Column<AdminProject>[] = [
    // 제목·주제·소유자는 길이가 제각각이라 좌측정렬, 나머지 짧은 값만 중앙정렬한다.
    seqColumn<AdminProject>(filteredRows.length, page, PAGE_SIZE),
    { header: '제목', cell: (p) => <span className="font-medium text-fg">{p.title}</span> },
    { header: '주제', cell: (p) => p.topic },
    {
      header: '소유자',
      cell: (p) => (
        <div>
          <div className="text-fg">{p.owner_name}</div>
          <div className="text-xs text-fg-faint">{p.owner_email}</div>
        </div>
      ),
    },
    { header: '상태', cell: (p) => PROJECT_STATUS_LABEL[p.status], align: 'center' },
    {
      header: '현재 단계',
      cell: (p) => STAGE_LABEL[p.current_stage] ?? p.current_stage,
      align: 'center',
    },
    { header: '생성일', cell: (p) => formatDate(p.created_at), align: 'center' },
  ]

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE))
  const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex gap-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.status}
              onClick={() => {
                setStatus(tab.status)
                setPage(1)
              }}
              className={`rounded-md px-3 py-1.5 text-sm ${
                status === tab.status
                  ? 'bg-primary font-medium text-on-primary'
                  : 'text-fg-muted hover:bg-surface-muted'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
          placeholder="제목·주제·소유자 검색"
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
            rowKey={(p) => p.id}
            onRowClick={(p) => navigate(`/admin/projects/${p.id}`)}
            empty={keyword || status !== 'ALL' ? '조건에 맞는 프로젝트가 없습니다.' : '아직 프로젝트가 없습니다.'}
          />
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={filteredRows.length}
          />
        </>
      )}
    </div>
  )
}
