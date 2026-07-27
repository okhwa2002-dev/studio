import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { Modal } from '../../components/Modal'
import { seqColumn } from '../../components/table/seqColumn'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { adminUsers, type AdminUser } from '../../lib/admin'
import { ApiError } from '../../lib/api'

// UI 전용 필터 값. 'ALL'은 상태 무관 전체, 'LOCKED'는 상태와 무관하게 잠긴 계정만
// (둘 다 백엔드에는 status 없이 요청하고 잠김은 클라이언트에서 거른다).
type StatusFilter = AdminUser['status'] | 'ALL' | 'LOCKED'

const STATUS_TABS: { status: StatusFilter; label: string }[] = [
  { status: 'ALL', label: '전체' },
  { status: 'ACTIVE', label: '활성' },
  { status: 'PENDING', label: '대기' },
  { status: 'REJECTED', label: '거절' },
  { status: 'DISABLED', label: '비활성' },
  { status: 'LOCKED', label: '잠김' },
]

// URL ?status= 로 넘어온 값이 유효한 탭인지 검사한다(대시보드 딥링크 대비).
const STATUS_VALUES = new Set<string>(STATUS_TABS.map((t) => t.status))

const PAGE_SIZE = 10
const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

function roleLabel(role: AdminUser['role']) {
  return role === 'ADMIN' ? '관리자' : '일반'
}

const STATUS_BADGE: Record<AdminUser['status'], { label: string; className: string }> = {
  PENDING: { label: '대기', className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300' },
  ACTIVE: { label: '활성', className: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300' },
  REJECTED: { label: '거절', className: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300' },
  DISABLED: { label: '비활성', className: 'bg-surface-muted text-fg-muted' },
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
    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-500/15 dark:text-red-300">
      🔒 잠김
    </span>
  )
}

function formatDate(iso: string) {
  // 백엔드가 로컬 naive ISO 문자열(예: 2026-07-15T12:34:56)을 준다. 앞 10글자가 날짜다.
  // Date로 파싱하면 타임존 보정이 끼어드니, 문자열을 그대로 자른다.
  return iso.slice(0, 10)
}

function formatDateTime(iso: string) {
  // 날짜와 분까지(예: 2026-07-15 12:34). formatDate와 같은 이유로 문자열을 그대로 자른다.
  return iso.slice(0, 16).replace('T', ' ')
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-fg-muted">{label}</dt>
      <dd className="text-right text-fg">{children}</dd>
    </div>
  )
}

// 목록 행을 클릭했을 때 뜨는 상세. 값은 이미 받아온 행을 그대로 쓴다(추가 요청 없음).
// 실패 횟수 초기화만 서버 액션이며, 성공하면 부모가 행을 갱신해 화면에 반영한다.
function UserDetailModal({
  user,
  onResetFailures,
  onClose,
}: {
  user: AdminUser
  onResetFailures: (id: number) => Promise<void>
  onClose: () => void
}) {
  const [resetting, setResetting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reset = async () => {
    setResetting(true)
    setError(null)
    try {
      await onResetFailures(user.id)
      // 성공하면 부모가 failed_login_count를 0으로 갱신 → 이 행의 버튼이 사라진다.
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
      setResetting(false)
    }
  }

  return (
    <Modal title="회원 상세" onClose={onClose}>
      <dl className="divide-y divide-line-subtle">
        <DetailRow label="이름">{user.name}</DetailRow>
        <DetailRow label="이메일">{user.email}</DetailRow>
        <DetailRow label="역할">{roleLabel(user.role)}</DetailRow>
        <DetailRow label="상태">
          <StatusBadge status={user.status} />
        </DetailRow>
        <DetailRow label="로그인 실패 횟수">
          <span className="inline-flex items-center gap-2">
            {user.failed_login_count}
            {user.failed_login_count > 0 && (
              <button
                onClick={reset}
                disabled={resetting}
                className="rounded-md border border-line-strong px-2 py-0.5 text-xs font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
              >
                {resetting ? '초기화 중…' : '초기화'}
              </button>
            )}
          </span>
        </DetailRow>
        <DetailRow label="계정 잠김">
          {user.locked_at ? `잠김 (${formatDateTime(user.locked_at)})` : '아니오'}
        </DetailRow>
        <DetailRow label="잠금 해제 일시">
          {user.unlocked_at ? formatDateTime(user.unlocked_at) : '-'}
        </DetailRow>
        <DetailRow label="승인 일시">
          {user.approved_at ? formatDateTime(user.approved_at) : '-'}
        </DetailRow>
        <DetailRow label="가입일">{formatDate(user.created_at)}</DetailRow>
      </dl>
      {error && (
        <div className="mt-4">
          <FormError message={error} />
        </div>
      )}
    </Modal>
  )
}

export function AdminUsers() {
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [rows, setRows] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [actingId, setActingId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [searchParams] = useSearchParams()

  // 대시보드 딥링크의 필터를 반영한다: ?status=PENDING·LOCKED 등 → 해당 탭.
  // (?locked=1은 예전 링크 호환용 별칭이다.)
  useEffect(() => {
    const s = searchParams.get('status')
    if (searchParams.get('locked') === '1') setStatus('LOCKED')
    else if (s && STATUS_VALUES.has(s)) setStatus(s as StatusFilter)
    setPage(1)
  }, [searchParams])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminUsers
      .list(status === 'ALL' || status === 'LOCKED' ? undefined : status)
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

  const resetFailures = async (id: number) => {
    await adminUsers.resetFailures(id)
    // 실패 횟수 초기화는 잠김도 함께 해제한다 → 열려 있는 상세와 목록 양쪽에 즉시 반영한다.
    const cleared = { failed_login_count: 0, locked_at: null }
    setSelected((prev) => (prev && prev.id === id ? { ...prev, ...cleared } : prev))
    setRows((prev) => prev.map((u) => (u.id === id ? { ...u, ...cleared } : u)))
  }

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter((u) => {
    if (status === 'LOCKED' && !u.locked_at) return false
    if (!keyword) return true
    return u.name.toLowerCase().includes(keyword) || u.email.toLowerCase().includes(keyword)
  })

  const columns: Column<AdminUser>[] = [
    seqColumn<AdminUser>(filteredRows.length, page, PAGE_SIZE),
    { header: '이름', cell: (u) => u.name, align: 'center' },
    { header: '이메일', cell: (u) => u.email },
    { header: '역할', cell: (u) => roleLabel(u.role), align: 'center' },
    { header: '상태', cell: (u) => <StatusBadge status={u.status} />, align: 'center' },
    { header: '실패', cell: (u) => (u.failed_login_count > 0 ? u.failed_login_count : '-'), align: 'center' },
    { header: '잠김', cell: (u) => (u.locked_at ? <LockBadge /> : '-'), align: 'center' },
    { header: '가입일', cell: (u) => formatDate(u.created_at), align: 'center' },
    { header: '해제일시', cell: (u) => (u.unlocked_at ? formatDate(u.unlocked_at) : '-'), align: 'center' },
    {
      header: '관리',
      align: 'center',
      cell: (u) => {
        if (u.status === 'PENDING') {
          return (
            // 행 클릭(상세 열기)과 겹치지 않게 버튼 영역의 클릭은 전파를 막는다.
            <div className="flex justify-center gap-2" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => act(u.id, 'approve')}
                disabled={actingId !== null}
                className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-on-primary disabled:opacity-50"
              >
                승인
              </button>
              <button
                onClick={() => act(u.id, 'reject')}
                disabled={actingId !== null}
                className="rounded-md border border-line-strong px-3 py-1 text-xs font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
              >
                거절
              </button>
            </div>
          )
        }
        if (u.locked_at) {
          return (
            <div className="flex justify-center" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => act(u.id, 'unlock')}
                disabled={actingId !== null}
                className="rounded-md border border-line-strong px-3 py-1 text-xs font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
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

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE))
  const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
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
          placeholder="이름 또는 이메일 검색"
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
            columns={columnsWithAction}
            rows={pageRows}
            rowKey={(u) => u.id}
            onRowClick={setSelected}
            empty={
              keyword
                ? '검색 결과가 없습니다.'
                : status === 'LOCKED'
                  ? '잠긴 계정이 없습니다.'
                  : '해당 상태의 사용자가 없습니다.'
            }
          />
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={filteredRows.length}
          />
        </>
      )}

      {selected && (
        <UserDetailModal
          user={selected}
          onResetFailures={resetFailures}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
