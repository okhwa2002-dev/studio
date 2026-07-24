import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { seqColumn } from '../../components/table/seqColumn'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { ApiError } from '../../lib/api'
import { projects, STAGE_LABEL, type ProjectSummary } from '../../lib/projects'
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
    // 제목·주제는 길이가 제각각이라 좌측정렬을 유지하고, 나머지 짧은 값들만 중앙정렬한다.
    seqColumn<ProjectSummary>(rows.length, page, PAGE_SIZE),
    { header: '제목', cell: (p) => <span className="font-medium text-slate-900">{p.title}</span> },
    { header: '주제', cell: (p) => p.topic },
    { header: '상태', cell: (p) => PROJECT_STATUS_LABEL[p.status], align: 'center' },
    // current_stage는 완료된 프로젝트에도 마지막 단계(render)가 남는다 — 그대로 보여준다.
    {
      header: '현재 단계',
      cell: (p) => STAGE_LABEL[p.current_stage] ?? p.current_stage,
      align: 'center',
    },
    { header: '생성일', cell: (p) => formatDate(p.created_at), align: 'center' },
  ]

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      {/* 제목은 AppLayout이 NAV에서 그린다 — 여기는 이 화면의 조작만 둔다. */}
      <div className="mb-4 flex justify-end">
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
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={rows.length}
          />
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
