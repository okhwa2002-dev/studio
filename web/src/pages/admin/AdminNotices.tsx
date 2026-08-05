import { useCallback, useEffect, useState } from 'react'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { FormError } from '../../components/FormError'
import { Modal } from '../../components/Modal'
import { PinnedBadge } from '../../components/PinnedBadge'
import { badgedSeqColumn } from '../../components/table/seqColumn'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { useClientPagination } from '../../components/table/useClientPagination'
import {
  adminNotices,
  localNowIso,
  noticePhase,
  type AdminNotice,
  type NoticePayload,
  type NoticePhase,
} from '../../lib/admin'
import { ApiError } from '../../lib/api'
import { isY, toYn } from '../../lib/notices'

type PhaseFilter = NoticePhase | 'ALL'

const PHASE_TABS: { phase: PhaseFilter; label: string }[] = [
  { phase: 'ALL', label: '전체' },
  { phase: 'ACTIVE', label: '게시중' },
  { phase: 'SCHEDULED', label: '예약' },
  { phase: 'DRAFT', label: '임시저장' },
  { phase: 'ENDED', label: '종료' },
]

const PHASE_BADGE: Record<NoticePhase, { label: string; className: string }> = {
  DRAFT: { label: '임시저장', className: 'bg-surface-muted text-fg-muted' },
  SCHEDULED: {
    label: '예약',
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
  },
  ACTIVE: {
    label: '게시중',
    className: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  },
  ENDED: { label: '종료', className: 'bg-surface-muted text-fg-muted' },
}

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

// 백엔드가 로컬 naive ISO 문자열을 주고 datetime-local 입력은 'YYYY-MM-DDTHH:mm'을
// 원한다. Date로 파싱하면 타임존 보정이 끼어드니 문자열을 그대로 자른다.
function toInputValue(iso: string | null): string {
  return iso ? iso.slice(0, 16) : ''
}

function fromInputValue(value: string): string | null {
  return value ? value : null
}

function formatPeriod(notice: AdminNotice): string {
  if (notice.starts_at === null) return '-'
  const start = notice.starts_at.slice(5, 10).replace('-', '/')
  const end = notice.ends_at ? notice.ends_at.slice(5, 10).replace('-', '/') : ''
  return `${start}~${end}`
}

function PhaseBadge({ phase }: { phase: NoticePhase }) {
  const badge = PHASE_BADGE[phase]
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
      {badge.label}
    </span>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-fg-muted">{label}</span>
      {children}
    </label>
  )
}

const INPUT_CLASS =
  'w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-fg focus:border-fg-muted focus:outline-none'

// 등록·수정 공용 폼. notice가 null이면 새 공지다(삭제 버튼이 없다).
function NoticeFormModal({
  notice,
  onSave,
  onDelete,
  onClose,
}: {
  notice: AdminNotice | null
  onSave: (payload: NoticePayload) => Promise<void>
  onDelete: () => Promise<void>
  onClose: () => void
}) {
  const [title, setTitle] = useState(notice?.title ?? '')
  const [body, setBody] = useState(notice?.body ?? '')
  const [startsAt, setStartsAt] = useState(toInputValue(notice?.starts_at ?? null))
  const [endsAt, setEndsAt] = useState(toInputValue(notice?.ends_at ?? null))
  const [pinned, setPinned] = useState(notice ? isY(notice.pinned_yn) : false)
  const [popup, setPopup] = useState(notice ? isY(notice.popup_yn) : false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmingPublish, setConfirmingPublish] = useState(false)

  // 게시는 되돌리기 어렵다 — 누르는 순간 모든 사용자가 보고, 팝업까지 켜져 있으면
  // 대시보드에 바로 뜬다. 무슨 일이 일어나는지 문장으로 보여주고 한 번 더 받는다.
  const publishMessage = (): string => {
    // 시작 일시를 비워두면 서버가 지금 시각으로 채운다. 미래면 그때부터 보인다.
    // 폭이 다른 문자열을 비교하면 같은 시각이 어긋나므로 분까지로 잘라 맞춘다.
    const scheduled = startsAt && startsAt > localNowIso().slice(0, 16)
    const when = scheduled ? `${startsAt.replace('T', ' ')}부터` : '지금부터'
    const popupNote = popup ? ' 대시보드 팝업으로도 뜹니다.' : ''
    return `${when} 모든 사용자에게 보입니다.${popupNote} 게시할까요?`
  }

  const submit = async (status: NoticePayload['status']) => {
    setPending(true)
    setError(null)
    try {
      await onSave({
        title,
        body,
        status,
        pinned_yn: toYn(pinned),
        popup_yn: toYn(popup),
        starts_at: fromInputValue(startsAt),
        ends_at: fromInputValue(endsAt),
      })
      // 성공하면 부모가 목록을 다시 불러오고 모달을 닫는다.
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
      setPending(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('이 공지를 삭제할까요?')) return
    setPending(true)
    setError(null)
    try {
      await onDelete()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
      setPending(false)
    }
  }

  return (
    <>
      <Modal title={notice ? '공지 수정' : '새 공지'} onClose={onClose}>
        <div className="space-y-4">
          <Field label="제목">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={INPUT_CLASS}
              placeholder="공지 제목"
            />
          </Field>
          <Field label="내용">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              className={INPUT_CLASS}
              placeholder="줄바꿈은 그대로 보입니다."
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="게시 시작 (비우면 게시 시각)">
              <input
                type="datetime-local"
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
                className={INPUT_CLASS}
              />
            </Field>
            <Field label="게시 종료 (비우면 무기한)">
              <input
                type="datetime-local"
                value={endsAt}
                onChange={(e) => setEndsAt(e.target.value)}
                className={INPUT_CLASS}
              />
            </Field>
          </div>
          <div className="flex gap-6 text-sm text-fg-body">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={pinned}
                onChange={(e) => setPinned(e.target.checked)}
              />
              목록 상단 고정
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={popup} onChange={(e) => setPopup(e.target.checked)} />
              메인 팝업으로 노출
            </label>
          </div>

          {error && <FormError message={error} />}

          <div className="flex items-center justify-between border-t border-line-subtle pt-4">
            {notice ? (
              <button
                onClick={remove}
                disabled={pending}
                className="rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-surface-muted disabled:opacity-50 dark:text-red-300"
              >
                삭제
              </button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <button
                onClick={() => submit('DRAFT')}
                disabled={pending}
                className="rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
              >
                임시저장
              </button>
              <button
                onClick={() => setConfirmingPublish(true)}
                disabled={pending}
                className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
              >
                게시하기
              </button>
            </div>
          </div>
        </div>
      </Modal>

      {/* 확인창을 먼저 닫고 저장한다 — 실패 메시지는 폼 안에 뜨고, 제목이 비었거나
          기간이 어긋난 경우처럼 입력을 고쳐야 하는 오류가 대부분이라 폼이 보여야 한다. */}
      {confirmingPublish && (
        <ConfirmDialog
          title="공지 게시"
          message={publishMessage()}
          confirmLabel="게시하기"
          onConfirm={() => {
            setConfirmingPublish(false)
            submit('PUBLISHED')
          }}
          onClose={() => setConfirmingPublish(false)}
        />
      )}
    </>
  )
}

export function AdminNotices() {
  const [rows, setRows] = useState<AdminNotice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [phase, setPhase] = useState<PhaseFilter>('ALL')
  const [query, setQuery] = useState('')
  // null = 닫힘, 'new' = 새 공지, 그 외 = 수정 대상
  const [editing, setEditing] = useState<AdminNotice | 'new' | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminNotices
      .list()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const now = localNowIso()
  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter((n) => {
    if (phase !== 'ALL' && noticePhase(n, now) !== phase) return false
    if (!keyword) return true
    return n.title.toLowerCase().includes(keyword) || n.body.toLowerCase().includes(keyword)
  })

  const { page, setPage, pageSize, setPageSize, totalPages, total, pageRows } =
    useClientPagination(filteredRows)

  const columns: Column<AdminNotice>[] = [
    // 고정 공지는 순번 바깥이다 — 번호 대신 '공지' 배지를 놓는다(사용자 목록과 같은 규칙).
    badgedSeqColumn<AdminNotice>(filteredRows, (n) => isY(n.pinned_yn), <PinnedBadge />),
    { header: '제목', cell: (n) => n.title },
    {
      header: '상태',
      cell: (n) => <PhaseBadge phase={noticePhase(n, now)} />,
      align: 'center',
    },
    { header: '고정', cell: (n) => (isY(n.pinned_yn) ? '📌' : '-'), align: 'center' },
    { header: '팝업', cell: (n) => (isY(n.popup_yn) ? '💬' : '-'), align: 'center' },
    { header: '게시기간', cell: formatPeriod, align: 'center' },
    { header: '작성자', cell: (n) => n.created_by_name ?? '-', align: 'center' },
  ]

  const save = async (payload: NoticePayload) => {
    if (editing === 'new') await adminNotices.create(payload)
    else if (editing) await adminNotices.update(editing.id, payload)
    setEditing(null)
    load()
  }

  const remove = async () => {
    if (editing && editing !== 'new') await adminNotices.remove(editing.id)
    setEditing(null)
    load()
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          {PHASE_TABS.map((tab) => (
            <button
              key={tab.phase}
              onClick={() => {
                setPhase(tab.phase)
                setPage(1)
              }}
              className={`rounded-md px-3 py-1.5 text-sm ${
                phase === tab.phase
                  ? 'bg-primary font-medium text-on-primary'
                  : 'text-fg-muted hover:bg-surface-muted'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
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
          <button
            onClick={() => setEditing('new')}
            className="shrink-0 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-on-primary"
          >
            + 새 공지
          </button>
        </div>
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
            onRowClick={setEditing}
            empty={keyword ? '검색 결과가 없습니다.' : '등록된 공지가 없습니다.'}
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

      {editing && (
        <NoticeFormModal
          notice={editing === 'new' ? null : editing}
          onSave={save}
          onDelete={remove}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
