import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { Pagination } from '../../components/table/Pagination'
import { Table, type Column } from '../../components/table/Table'
import { ApiError } from '../../lib/api'
import { projects, type ProjectSummary } from '../../lib/projects'
import { NewProjectModal } from './NewProjectModal'

const PAGE_SIZE = 10
const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

const PROJECT_STATUS_LABEL: Record<ProjectSummary['status'], string> = {
  DRAFT: '작성 중',
  REVIEW: '검토 중',
  DONE: '완료',
}

function formatDate(iso: string) {
  return iso.slice(0, 10)
}

export function Projects() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [showNew, setShowNew] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    projects
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

  const columns: Column<ProjectSummary>[] = [
    { header: '제목', cell: (p) => <span className="font-medium text-slate-900">{p.title}</span> },
    { header: '주제', cell: (p) => p.topic },
    { header: '상태', cell: (p) => PROJECT_STATUS_LABEL[p.status] },
    { header: '생성일', cell: (p) => formatDate(p.created_at), align: 'right' },
  ]

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">프로젝트</h1>
        <button
          onClick={() => setShowNew(true)}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
        >
          새 프로젝트
        </button>
      </div>

      {error && (
        <div className="mb-4">
          <FormError message={error} />
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-sm text-slate-500">불러오는 중…</div>
      ) : (
        <>
          <Table
            columns={columns}
            rows={pageRows}
            rowKey={(p) => p.id}
            empty="아직 프로젝트가 없습니다."
            onRowClick={(p) => navigate(`/projects/${p.id}`)}
          />
          {/* 페이지 버튼은 가운데, 전체 건수는 우측. 3열 그리드라 버튼이 건수 폭에 밀리지 않고 항상 중앙에 온다. */}
          <div className="mt-4 grid grid-cols-3 items-center text-sm text-slate-600">
            <div />
            <div className="flex justify-center">
              <Pagination page={page} totalPages={totalPages} onChange={setPage} />
            </div>
            <div className="text-right">전체 {rows.length}건</div>
          </div>
        </>
      )}

      {showNew && (
        <NewProjectModal
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false)
            load() // 목록에 머문 채 새 프로젝트가 상단에 뜨도록 갱신
          }}
        />
      )}
    </div>
  )
}
