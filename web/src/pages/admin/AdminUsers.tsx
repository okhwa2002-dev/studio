import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { FormError } from '../../components/FormError'
import { Modal } from '../../components/Modal'
import { seqColumn } from '../../components/table/seqColumn'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { useClientPagination } from '../../components/table/usePagination'
import { adminUsers, type AdminUser } from '../../lib/admin'
import { ApiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useToast } from '../../lib/toast'

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

// 필터는 URL 하나만 보고 정한다. 알 수 없는 값(또는 파라미터 없음)은 '전체'다.
// (?locked=1은 예전 링크 호환용 별칭이다.)
function readStatus(params: URLSearchParams): StatusFilter {
  if (params.get('locked') === '1') return 'LOCKED'
  const s = params.get('status')
  return s && STATUS_VALUES.has(s) ? (s as StatusFilter) : 'ALL'
}

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
    // min-h로 행 높이를 고정한다 — 값이 텍스트인 행과 버튼·뱃지가 있는 행의 높이가
    // 들쭉날쭉하지 않게 맞춘다(버튼 쪽이 내용만으로도 더 높아진다).
    <div className="flex min-h-11 items-center justify-between gap-4 py-3 text-sm">
      <dt className="shrink-0 text-fg-muted">{label}</dt>
      <dd className="text-right text-fg">{children}</dd>
    </div>
  )
}

// 비밀번호 초기화 후 발급된 임시 비밀번호를 보여주는 자리. 관리자가 사용자에게
// 전달해야 하는 값이라 눈으로 옮겨 적게 하지 않고 복사 버튼을 함께 둔다.
function TempPassword({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
    } catch {
      // 복사 실패는 알리지 않는다 — 값이 화면에 그대로 보이므로 손으로 옮겨 적을 수 있고,
      // 실패를 알려도 사용자가 달리 할 수 있는 일이 없다.
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <code className="rounded bg-surface-muted px-2 py-0.5 font-mono text-xs text-fg">
        {value}
      </code>
      <button
        onClick={copy}
        className="rounded-md border border-line-strong px-2 py-0.5 text-xs font-medium text-fg-body hover:bg-surface-muted"
      >
        {copied ? '복사됨' : '복사'}
      </button>
      <span className="text-xs text-fg-muted">변경 대기</span>
    </span>
  )
}

// 목록 행을 클릭했을 때 뜨는 상세. 값은 이미 받아온 행을 그대로 쓴다(추가 요청 없음).
// 실패 횟수 초기화와 비밀번호 초기화만 서버 액션이며, 성공하면 부모가 행을 갱신한다.
function UserDetailModal({
  user,
  isSelf,
  onResetFailures,
  onResetPassword,
  onClose,
}: {
  user: AdminUser
  isSelf: boolean
  onResetFailures: (id: number) => Promise<void>
  onResetPassword: (id: number) => Promise<string>
  onClose: () => void
}) {
  const [resetting, setResetting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resettingPassword, setResettingPassword] = useState(false)
  const [tempPassword, setTempPassword] = useState<string | null>(null)

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

  const resetPassword = async () => {
    // 되돌릴 수 없고 이 사용자의 모든 세션을 끊는다 — 실패 횟수 초기화와 달리 한 번 묻는다.
    const ok = window.confirm(
      `${user.name}(${user.email})의 비밀번호를 초기화하시겠습니까?\n\n` +
        '이 사용자의 모든 로그인 세션이 종료되고, 다음 로그인 시 새 비밀번호를 설정해야 합니다.',
    )
    if (!ok) return

    setResettingPassword(true)
    setError(null)
    try {
      setTempPassword(await onResetPassword(user.id))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setResettingPassword(false)
    }
  }

  return (
    <Modal title="회원 상세" width="lg" onClose={onClose}>
      <dl className="divide-y divide-line-subtle">
        <DetailRow label="이름">{user.name}</DetailRow>
        <DetailRow label="이메일">{user.email}</DetailRow>
        <DetailRow label="역할">{roleLabel(user.role)}</DetailRow>
        <DetailRow label="상태">
          <StatusBadge status={user.status} />
        </DetailRow>
        <DetailRow label="비밀번호">
          {tempPassword !== null ? (
            <TempPassword value={tempPassword} />
          ) : isSelf ? (
            // 서버가 400으로 막는다. 항상 실패하는 버튼은 버그로 보이므로 감춘다 —
            // 본인 비밀번호는 설정 화면에서 바꾼다.
            <span className="text-xs text-fg-muted">본인은 설정 화면에서 변경</span>
          ) : (
            <span className="inline-flex items-center gap-2">
              {user.must_change_password && (
                <span className="text-xs text-fg-muted">초기화됨 (변경 대기)</span>
              )}
              <button
                onClick={resetPassword}
                disabled={resettingPassword}
                className="rounded-md border border-line-strong px-2 py-0.5 text-xs font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
              >
                {resettingPassword ? '초기화 중…' : '초기화'}
              </button>
            </span>
          )}
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

type ActionKey = 'approve' | 'reject' | 'unlock'

// 승인/거절/잠금 해제 실행 전 확인 문구. 되돌리기 어려운 '거절'만 danger 톤이다.
const ACTION_CONFIRM: Record<
  ActionKey,
  {
    title: string
    confirmLabel: string
    tone: 'default' | 'danger'
    message: (name: string) => string
    success: string // 완료 토스트 문구
  }
> = {
  approve: {
    title: '사용자 승인',
    confirmLabel: '승인',
    tone: 'default',
    message: (n) => `${n} 님을 승인하시겠습니까? 승인하면 로그인할 수 있습니다.`,
    success: '승인했습니다.',
  },
  reject: {
    title: '사용자 거절',
    confirmLabel: '거절',
    tone: 'danger',
    message: (n) => `${n} 님을 거절하시겠습니까? 거절하면 로그인할 수 없습니다.`,
    success: '거절했습니다.',
  },
  unlock: {
    title: '잠금 해제',
    confirmLabel: '잠금 해제',
    tone: 'default',
    message: (n) => `${n} 님의 계정 잠금을 해제하시겠습니까?`,
    success: '잠금을 해제했습니다.',
  },
}

export function AdminUsers() {
  const [rows, setRows] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actingId, setActingId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<AdminUser | null>(null)
  // 승인/거절/잠금 해제 확인 대화상자의 대상. null이면 닫힘.
  const [confirming, setConfirming] = useState<{ id: number; action: ActionKey; name: string } | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  // 상세에서 본인 행의 비밀번호 초기화 버튼을 감추는 데만 쓴다(서버도 400으로 막는다).
  const { user: currentUser } = useAuth()
  const toast = useToast()

  // 탭 상태를 따로 두지 않고 URL에서 읽는다. 탭 클릭도 URL을 고치므로 둘이 어긋날 수
  // 없고, 대시보드에서 같은 카드를 다시 눌러도(주소가 그대로여도) 탭이 딴 데 가 있지 않다.
  const status = readStatus(searchParams)

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows
    .filter((u) => {
      if (status === 'LOCKED' && !u.locked_at) return false
      if (!keyword) return true
      return u.name.toLowerCase().includes(keyword) || u.email.toLowerCase().includes(keyword)
    })
    // 승인 대기가 관리자의 할 일이다 — 상태를 섞어 보는 탭('전체'·'잠김')에서 맨 위로 올린다.
    // 정렬은 여기서 한다: 페이지 자르기(pageRows)보다 앞서야 1페이지에 모이고,
    // filter가 만든 새 배열이라 rows 원본은 건드리지 않는다.
    // sort는 안정 정렬이므로 같은 그룹 안에서는 서버 정렬(가입일 오름차순)이 그대로 남는다.
    .sort((a, b) => Number(b.status === 'PENDING') - Number(a.status === 'PENDING'))

  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)

  // 탭을 바꾸면 목록이 통째로 바뀐다 — 이전 탭에서 보던 페이지 번호는 의미가 없다.
  useEffect(() => {
    setPage(1)
  }, [status, setPage])

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
  }, [status, setPage])

  useEffect(() => {
    load()
  }, [load])

  const act = async (id: number, action: ActionKey) => {
    setActingId(id)
    setError(null)
    try {
      await adminUsers[action](id)
      load() // 처리된 사용자는 현재(대기) 목록에서 빠진다
      toast.success(ACTION_CONFIRM[action].success)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : UNKNOWN)
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

  // 발급된 임시 비밀번호를 모달에 돌려준다(모달이 그 값을 표시한다).
  // 목록을 다시 불러오지 않는다 — 초기화는 status를 바꾸지 않아 행이 현재 탭에 그대로
  // 남으므로, 서버가 UPDATE한 컬럼과 같은 값으로 그 행만 갱신하면 화면과 DB가 맞는다.
  const resetPassword = async (id: number) => {
    const { temp_password, unlocked_at } = await adminUsers.resetPassword(id)
    const patch = {
      must_change_password: true,
      failed_login_count: 0,
      locked_at: null,
      unlocked_at,
    }
    setSelected((prev) => (prev && prev.id === id ? { ...prev, ...patch } : prev))
    setRows((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)))
    return temp_password
  }

  const columns: Column<AdminUser>[] = [
    seqColumn<AdminUser>(total, page, pageSize),
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
                onClick={() => setConfirming({ id: u.id, action: 'approve', name: u.name })}
                disabled={actingId !== null}
                className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-on-primary disabled:opacity-50"
              >
                승인
              </button>
              <button
                onClick={() => setConfirming({ id: u.id, action: 'reject', name: u.name })}
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
                onClick={() => setConfirming({ id: u.id, action: 'unlock', name: u.name })}
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

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.status}
              // 필터를 URL에 적어 탭·주소·딥링크가 한 값을 보게 한다. replace라서
              // 탭을 여러 번 눌러도 뒤로 가기가 대시보드로 한 번에 돌아간다.
              // (예전 별칭 ?locked=1도 이때 함께 지워진다)
              onClick={() => setSearchParams({ status: tab.status }, { replace: true })}
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
            total={total}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
        </>
      )}

      {selected && (
        <UserDetailModal
          user={selected}
          isSelf={selected.id === currentUser?.id}
          onResetFailures={resetFailures}
          onResetPassword={resetPassword}
          onClose={() => setSelected(null)}
        />
      )}

      {confirming && (
        <ConfirmDialog
          title={ACTION_CONFIRM[confirming.action].title}
          message={ACTION_CONFIRM[confirming.action].message(confirming.name)}
          confirmLabel={ACTION_CONFIRM[confirming.action].confirmLabel}
          tone={ACTION_CONFIRM[confirming.action].tone}
          busy={actingId !== null}
          onConfirm={async () => {
            await act(confirming.id, confirming.action)
            setConfirming(null)
          }}
          onClose={() => setConfirming(null)}
        />
      )}
    </div>
  )
}
