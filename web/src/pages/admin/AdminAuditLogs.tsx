import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { DEFAULT_PAGE_SIZE } from '../../components/table/PageSizeSelect'
import { seqColumn } from '../../components/table/seqColumn'
import { Table, type Column } from '../../components/table/Table'
import { TableFooter } from '../../components/table/TableFooter'
import { ApiError } from '../../lib/api'
import { AUDIT_ACTION_LABEL, auditLogs, type AuditLog } from '../../lib/auditLogs'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

// 오늘 / N일 전을 YYYY-MM-DD로. 로컬 기준이라 toISOString(UTC)을 쓰지 않는다.
function isoDate(daysAgo = 0): string {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// 백엔드가 로컬 naive ISO 문자열을 준다. Date로 파싱하면 타임존 보정이 끼어드니
// 문자열을 그대로 자른다(AdminUsers의 formatDateTime과 같은 이유).
function formatDateTime(iso: string) {
  return iso.slice(0, 19).replace('T', ' ')
}

function ResultBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-500/15 dark:text-green-300">
      성공
    </span>
  ) : (
    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-500/15 dark:text-red-300">
      실패
    </span>
  )
}

export function AdminAuditLogs() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [rows, setRows] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // 검색어만 입력 중 상태를 따로 둔다 — 글자마다 요청하지 않고 Enter/버튼에서 URL에 반영한다.
  const [keyword, setKeyword] = useState(searchParams.get('q') ?? '')
  // 서버 페이징이라 useClientPagination을 쓰지 않는다 — 자를 배열이 손에 없다.
  // 크기만 화면이 들고, 자르는 일은 서버가 한다. 기본값은 나머지 여섯 화면과 같은 상수를
  // 본다 — 페이징 방식이 달라도 사용자가 보는 기본 건수까지 달라질 이유는 없다.
  // 리터럴 20으로 좁혀지면 50·100을 넣을 수 없어 number로 못박는다.
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)

  // 필터는 URL 하나만 보고 정한다. 새로고침해도 유지되고, 조건이 걸린 화면을
  // 링크로 넘길 수 있다(AdminUsers와 같은 방침).
  const from = searchParams.get('from') ?? isoDate(7)
  const to = searchParams.get('to') ?? isoDate(0)
  const action = searchParams.get('action') ?? ''
  const success = searchParams.get('success') ?? ''
  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1')

  // 필터를 바꾸면 페이지는 1로 돌아간다 — 3페이지에서 조건을 좁히면 결과가 없는
  // 페이지에 남아 "기록이 없다"로 잘못 읽힌다.
  const setFilter = (patch: Record<string, string>) => {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (!('page' in patch)) next.delete('page')
    setSearchParams(next, { replace: true })
  }

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    auditLogs
      .list({
        from,
        to,
        action: action || undefined,
        success: (success || undefined) as 'Y' | 'N' | undefined,
        q: q || undefined,
        page,
        size: pageSize,
      })
      .then((data) => {
        setRows(data.items)
        setTotal(data.total)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [from, to, action, success, q, page, pageSize])

  useEffect(() => {
    load()
  }, [load])

  const columns: Column<AuditLog>[] = [
    seqColumn<AuditLog>(total, page, pageSize),
    { header: '시각', cell: (r) => formatDateTime(r.created_at), align: 'center' },
    {
      header: '행위',
      align: 'center',
      cell: (r) => AUDIT_ACTION_LABEL[r.action] ?? r.action,
    },
    {
      header: '행위자',
      cell: (r) => (
        // 이름과 이메일을 한 줄에 둔다. 이메일은 작고 흐리게 남겨 이름이 먼저 읽히게 하고,
        // baseline 정렬로 크기가 다른 두 텍스트의 밑선을 맞춘다.
        <span className="inline-flex items-baseline gap-1.5">
          {r.actor_name && <span>{r.actor_name}</span>}
          <span className="text-xs text-fg-muted">{r.actor_email ?? '—'}</span>
        </span>
      ),
    },
    { header: '대상', cell: (r) => r.target_label ?? '—' },
    { header: '결과', cell: (r) => <ResultBadge ok={r.success_yn === 'Y'} />, align: 'center' },
    {
      // 호출 API는 별도 열이 아니라 title 툴팁으로 붙인다 — 가로 폭이 빠듯하고 이차 정보라서.
      header: '설명',
      cell: (r) => (
        <span title={r.http_method ? `${r.http_method} ${r.http_path}` : undefined}>
          {r.summary ?? '—'}
        </span>
      ),
    },
  ]

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={from}
          onChange={(e) => setFilter({ from: e.target.value })}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
        />
        <span className="text-fg-muted">~</span>
        <input
          type="date"
          value={to}
          onChange={(e) => setFilter({ to: e.target.value })}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
        />
        <select
          value={action}
          onChange={(e) => setFilter({ action: e.target.value })}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
        >
          <option value="">전체 행위</option>
          {Object.entries(AUDIT_ACTION_LABEL).map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={success}
          onChange={(e) => setFilter({ success: e.target.value })}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
        >
          <option value="">전체 결과</option>
          <option value="Y">성공</option>
          <option value="N">실패</option>
        </select>
        <input
          type="search"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') setFilter({ q: keyword })
          }}
          placeholder="이름·이메일·대상·설명 검색"
          className="w-64 rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
        />
        <button
          onClick={() => setFilter({ q: keyword })}
          className="rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-fg-body hover:bg-surface-muted"
        >
          검색
        </button>
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
            rows={rows}
            rowKey={(r) => r.id}
            empty="조건에 맞는 기록이 없습니다."
          />
          <TableFooter
            page={page}
            totalPages={totalPages}
            onChange={(next) => setFilter({ page: String(next) })}
            total={total}
            pageSize={pageSize}
            onPageSizeChange={(size) => {
              setPageSize(size)
              // 빈 patch를 넘기면 setFilter가 URL에서 page를 지운다 → 1페이지.
              // 필터를 바꿀 때와 같은 경로를 타므로 규칙이 하나뿐이다.
              setFilter({})
            }}
          />
        </>
      )}
    </div>
  )
}
