import { useCallback, useEffect, useState } from 'react'
import { FormError } from '../../components/FormError'
import { Modal } from '../../components/Modal'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { adminFaqs, type AdminFaq, type FaqPayload } from '../../lib/admin'
import { ApiError } from '../../lib/api'
import { FAQ_CATEGORIES, FAQ_CATEGORY_LABEL, type FaqCategory } from '../../lib/faqs'

type StatusFilter = AdminFaq['status'] | 'ALL'

const STATUS_TABS: { status: StatusFilter; label: string }[] = [
  { status: 'ALL', label: '전체' },
  { status: 'PUBLISHED', label: '게시중' },
  { status: 'DRAFT', label: '임시저장' },
]

// 공지와 달리 파생 상태(예약·종료)가 없어 status 값이 곧 표시 상태다.
const STATUS_BADGE: Record<AdminFaq['status'], { label: string; className: string }> = {
  DRAFT: { label: '임시저장', className: 'bg-surface-muted text-fg-muted' },
  PUBLISHED: {
    label: '게시중',
    className: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  },
}

const PAGE_SIZE = 10
const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

const INPUT_CLASS =
  'w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-fg focus:border-fg-muted focus:outline-none'

function StatusBadge({ status }: { status: AdminFaq['status'] }) {
  const badge = STATUS_BADGE[status]
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

// 등록·수정 공용 폼. faq가 null이면 새 FAQ다(삭제 버튼이 없다).
function FaqFormModal({
  faq,
  onSave,
  onDelete,
  onClose,
}: {
  faq: AdminFaq | null
  onSave: (payload: FaqPayload) => Promise<void>
  onDelete: () => Promise<void>
  onClose: () => void
}) {
  const [question, setQuestion] = useState(faq?.question ?? '')
  const [answer, setAnswer] = useState(faq?.answer ?? '')
  const [category, setCategory] = useState<FaqCategory>(faq?.category ?? 'ETC')
  // 입력 중에 빈 문자열이 될 수 있어 문자열로 들고 있다가 보낼 때 숫자로 바꾼다.
  const [sortOrder, setSortOrder] = useState(String(faq?.sort_order ?? 0))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (status: FaqPayload['status']) => {
    setPending(true)
    setError(null)
    try {
      await onSave({
        question,
        answer,
        category,
        status,
        sort_order: Number(sortOrder) || 0,
      })
      // 성공하면 부모가 목록을 다시 불러오고 모달을 닫는다.
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
      setPending(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('이 FAQ를 삭제할까요?')) return
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
    <Modal title={faq ? 'FAQ 수정' : '새 FAQ'} onClose={onClose}>
      <div className="space-y-4">
        <Field label="분류">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as FaqCategory)}
            className={INPUT_CLASS}
          >
            {FAQ_CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {FAQ_CATEGORY_LABEL[value]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="질문">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className={INPUT_CLASS}
            placeholder="렌더링은 얼마나 걸리나요?"
          />
        </Field>
        <Field label="답변">
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={6}
            className={INPUT_CLASS}
            placeholder="줄바꿈은 그대로 보입니다."
          />
        </Field>
        <Field label="정렬 순서 (작을수록 위, 10·20·30처럼 띄워 쓰면 사이에 끼워 넣기 쉽습니다)">
          <input
            type="number"
            min={0}
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
            className={INPUT_CLASS}
          />
        </Field>

        {error && <FormError message={error} />}

        <div className="flex items-center justify-between border-t border-line-subtle pt-4">
          {faq ? (
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
              onClick={() => submit('PUBLISHED')}
              disabled={pending}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-on-primary disabled:opacity-50"
            >
              게시하기
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

export function AdminFaqs() {
  const [rows, setRows] = useState<AdminFaq[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  // null = 닫힘, 'new' = 새 FAQ, 그 외 = 수정 대상
  const [editing, setEditing] = useState<AdminFaq | 'new' | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminFaqs
      .list()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter((f) => {
    if (status !== 'ALL' && f.status !== status) return false
    if (!keyword) return true
    return f.question.toLowerCase().includes(keyword) || f.answer.toLowerCase().includes(keyword)
  })

  const columns: Column<AdminFaq>[] = [
    // 관리자가 조정해야 하는 값이라 목록에 그대로 보여준다 — 보이지 않으면
    // 순서를 바꿀 때마다 모달을 열어 확인해야 한다.
    { header: '순서', cell: (f) => f.sort_order, align: 'center', width: 72 },
    { header: '질문', cell: (f) => f.question },
    { header: '분류', cell: (f) => FAQ_CATEGORY_LABEL[f.category], align: 'center' },
    { header: '상태', cell: (f) => <StatusBadge status={f.status} />, align: 'center' },
    { header: '작성자', cell: (f) => f.created_by_name ?? '-', align: 'center' },
  ]

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE))
  const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const save = async (payload: FaqPayload) => {
    if (editing === 'new') await adminFaqs.create(payload)
    else if (editing) await adminFaqs.update(editing.id, payload)
    setEditing(null)
    load()
  }

  const remove = async () => {
    if (editing && editing !== 'new') await adminFaqs.remove(editing.id)
    setEditing(null)
    load()
  }

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
        <div className="flex items-center gap-2">
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setPage(1)
            }}
            placeholder="질문 또는 답변 검색"
            className="w-64 rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
          />
          <button
            onClick={() => setEditing('new')}
            className="shrink-0 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-on-primary"
          >
            + 새 FAQ
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
            rowKey={(f) => f.id}
            onRowClick={setEditing}
            empty={keyword ? '검색 결과가 없습니다.' : '등록된 FAQ가 없습니다.'}
          />
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={setPage}
            total={filteredRows.length}
          />
        </>
      )}

      {editing && (
        <FaqFormModal
          faq={editing === 'new' ? null : editing}
          onSave={save}
          onDelete={remove}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
