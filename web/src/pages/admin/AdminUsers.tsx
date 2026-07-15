import { useCallback, useEffect, useState } from 'react'
import { FormError } from '../../components/FormError'
import { Pagination } from '../../components/table/Pagination'
import { Table, type Column } from '../../components/table/Table'
import { adminUsers, type AdminUser } from '../../lib/admin'
import { ApiError } from '../../lib/api'

const STATUS_TABS: { status: AdminUser['status']; label: string }[] = [
  { status: 'ACTIVE', label: '활성' },
  { status: 'PENDING', label: '대기' },
  { status: 'REJECTED', label: '거절' },
  { status: 'DISABLED', label: '비활성' },
]

const PAGE_SIZE = 10
const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

function roleLabel(role: AdminUser['role']) {
  return role === 'ADMIN' ? '관리자' : '일반'
}

const STATUS_BADGE: Record<AdminUser['status'], { label: string; className: string }> = {
  PENDING: { label: '대기', className: 'bg-yellow-100 text-yellow-800' },
  ACTIVE: { label: '활성', className: 'bg-green-100 text-green-800' },
  REJECTED: { label: '거절', className: 'bg-red-100 text-red-800' },
  DISABLED: { label: '비활성', className: 'bg-slate-100 text-slate-600' },
}

function StatusBadge({ status }: { status: AdminUser['status'] }) {
  const badge = STATUS_BADGE[status]
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
      {badge.label}
    </span>
  )
}

function LockBadge() {
  return (
    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
      🔒 잠김
    </span>
  )
}

function formatDate(iso: string) {
  // 백엔드가 로컬 naive ISO 문자열(예: 2026-07-15T12:34:56)을 준다. 앞 10글자가 날짜다.
  // Date로 파싱하면 타임존 보정이 끼어드니, 문자열을 그대로 자른다.
  return iso.slice(0, 10)
}

export function AdminUsers() {
  const [status, setStatus] = useState<AdminUser['status']>('ACTIVE')
  const [rows, setRows] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [actingId, setActingId] = useState<number | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminUsers
      .list(status)
      .then((data) => {
        setRows(data)
        setPage(1)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [status])

  useEffect(() => {
    load()
  }, [load])

  const act = async (id: number, action: 'approve' | 'reject' | 'unlock') => {
    setActingId(id)
    setError(null)
    try {
      await adminUsers[action](id)
      load() // 처리된 사용자는 현재(대기) 목록에서 빠진다
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setActingId(null)
    }
  }

  const columns: Column<AdminUser>[] = [
    { header: '이메일', cell: (u) => u.email },
    { header: '역할', cell: (u) => roleLabel(u.role) },
    { header: '상태', cell: (u) => <StatusBadge status={u.status} /> },
    { header: '실패', cell: (u) => (u.failed_login_count > 0 ? u.failed_login_count : '-'), align: 'right' },
    { header: '잠김', cell: (u) => (u.locked_at ? <LockBadge /> : '-') },
    { header: '가입일', cell: (u) => formatDate(u.created_at), align: 'right' },
    { header: '해제일시', cell: (u) => (u.unlocked_at ? formatDate(u.unlocked_at) : '-'), align: 'right' },
    {
      header: '관리',
      align: 'right',
      cell: (u) => {
        if (u.status === 'PENDING') {
          return (
            <div className="flex justify-end gap-2">
              <button
                onClick={() => act(u.id, 'approve')}
                disabled={actingId !== null}
                className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                승인
              </button>
              <button
                onClick={() => act(u.id, 'reject')}
                disabled={actingId !== null}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                거절
              </button>
            </div>
          )
        }
        if (u.locked_at) {
          return (
            <div className="flex justify-end">
              <button
                onClick={() => act(u.id, 'unlock')}
                disabled={actingId !== null}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                잠금 해제
              </button>
            </div>
          )
        }
        return null
      },
    },
  ]

  const columnsWithAction = columns

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <div className="mb-4 flex gap-1">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.status}
            onClick={() => setStatus(tab.status)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              status === tab.status
                ? 'bg-slate-900 font-medium text-white'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
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
            columns={columnsWithAction}
            rows={pageRows}
            rowKey={(u) => u.id}
            empty="해당 상태의 사용자가 없습니다."
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
    </div>
  )
}
