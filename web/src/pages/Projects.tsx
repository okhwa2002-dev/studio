import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FormError } from '../components/FormError'
import { Table, type Column } from '../components/table/Table'
import { ApiError } from '../lib/api'
import { projects, type ProjectSummary } from '../lib/projects'

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
  const [rows, setRows] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    projects
      .list()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const columns: Column<ProjectSummary>[] = [
    { header: '제목', cell: (p) => <Link to={`/projects/${p.id}`} className="text-slate-900 hover:underline">{p.title}</Link> },
    { header: '주제', cell: (p) => p.topic },
    { header: '상태', cell: (p) => PROJECT_STATUS_LABEL[p.status] },
    { header: '생성일', cell: (p) => formatDate(p.created_at), align: 'right' },
  ]

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">프로젝트</h1>
        <Link
          to="/projects/new"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
        >
          새 프로젝트
        </Link>
      </div>

      {error && (
        <div className="mb-4">
          <FormError message={error} />
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-sm text-slate-500">불러오는 중…</div>
      ) : (
        <Table columns={columns} rows={rows} rowKey={(p) => p.id} empty="아직 프로젝트가 없습니다." />
      )}
    </div>
  )
}
