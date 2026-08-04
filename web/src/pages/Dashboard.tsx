import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FormError } from '../components/FormError'
import { ApiError } from '../lib/api'
import { dashboard, type DashboardSummary } from '../lib/dashboard'
import { isY, notices as noticesApi, type Notice } from '../lib/notices'
import { STAGE_LABEL } from '../lib/projects'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

// 지표 한 칸. to를 주면 해당 화면으로 가는 링크가 되고, 없으면 정적 카드다.
function StatCard({ label, value, to }: { label: string; value: number; to?: string }) {
  const inner = (
    <>
      <div className="text-2xl font-semibold text-fg">{value}</div>
      <div className="mt-1 text-xs text-fg-muted">{label}</div>
    </>
  )
  const base = 'rounded-lg border border-line bg-surface p-4'
  return to ? (
    <Link to={to} className={`${base} block transition-colors hover:bg-surface-muted`}>
      {inner}
    </Link>
  ) : (
    <div className={base}>{inner}</div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-3 text-sm font-semibold text-fg">{children}</h2>
}

function AttentionBadges({ needsReview, failed }: { needsReview: boolean; failed: boolean }) {
  return (
    <span className="flex shrink-0 gap-1">
      {needsReview && (
        <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300">
          검토 필요
        </span>
      )}
      {failed && (
        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-500/15 dark:text-red-300">
          실패
        </span>
      )}
    </span>
  )
}

const NOTICE_PREVIEW_LIMIT = 5

// 최근 공지 요약. 각 줄은 해당 공지의 상세 화면으로 바로 보낸다 — 읽음 처리와
// 배지 갱신은 상세 화면이 맡으므로, 목록을 한 번 더 거칠 이유가 없다.
function NoticeSection() {
  const [rows, setRows] = useState<Notice[]>([])

  useEffect(() => {
    // 공지는 대시보드의 곁다리다. 실패하면 섹션을 그리지 않고 넘어간다.
    noticesApi
      .list()
      .then((data) => setRows(data.slice(0, NOTICE_PREVIEW_LIMIT)))
      .catch(() => setRows([]))
  }, [])

  if (rows.length === 0) return null

  return (
    <div className="mb-6">
      <div className="mb-3 flex items-center justify-between">
        <SectionTitle>공지사항</SectionTitle>
        <Link to="/notices" className="text-sm text-fg-muted hover:text-fg">
          더보기 →
        </Link>
      </div>
      <div className="rounded-lg border border-line bg-surface">
        <ul className="divide-y divide-line-subtle">
          {rows.map((notice) => (
            <li key={notice.id}>
              <Link
                to={`/notices/${notice.id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-surface-muted"
              >
                <span className="flex min-w-0 items-center gap-2">
                  {isY(notice.pinned_yn) && <span aria-label="고정">📌</span>}
                  <span className="truncate text-sm text-fg">{notice.title}</span>
                  {!notice.is_read && (
                    <span className="shrink-0 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-500/15 dark:text-red-300">
                      NEW
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-fg-muted">
                  {notice.starts_at.slice(5, 10)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function MemberSection({ data }: { data: DashboardSummary }) {
  const { projects, attention } = data

  if (projects.total === 0) {
    return (
      <section className="rounded-lg border border-line bg-surface p-8 text-center">
        <p className="text-sm text-fg-muted">아직 프로젝트가 없습니다.</p>
        <Link
          to="/projects"
          className="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary"
        >
          프로젝트 이동
        </Link>
      </section>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-3 flex items-center justify-between">
          <SectionTitle>내 프로젝트</SectionTitle>
          <Link
            to="/projects"
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-on-primary"
          >
            프로젝트 이동
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="전체" value={projects.total} to="/projects" />
          <StatCard label="작성 중" value={projects.draft} to="/projects" />
          <StatCard label="검토 중" value={projects.review} to="/projects" />
          <StatCard label="완료" value={projects.done} to="/projects" />
        </div>
      </div>

      <div>
        <SectionTitle>조치 필요</SectionTitle>
        <div className="rounded-lg border border-line bg-surface">
          {attention.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-fg-muted">
              검토하거나 다시 실행할 항목이 없습니다.
            </p>
          ) : (
            <ul className="divide-y divide-line-subtle">
              {attention.map((p) => (
                <li key={p.id}>
                  <Link
                    to={`/projects/${p.id}`}
                    className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-surface-muted"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-fg">{p.title}</span>
                      <span className="text-xs text-fg-muted">
                        현재 단계: {STAGE_LABEL[p.current_stage] ?? p.current_stage}
                      </span>
                    </span>
                    <AttentionBadges needsReview={p.needs_review} failed={p.failed} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function AdminSection({ admin }: { admin: NonNullable<DashboardSummary['admin']> }) {
  return (
    <div className="mt-8 border-t border-line pt-6">
      <SectionTitle>운영 현황</SectionTitle>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatCard label="가입 승인 대기" value={admin.users.pending} to="/admin/users?status=PENDING" />
          <StatCard label="잠긴 계정" value={admin.users.locked} to="/admin/users?status=LOCKED" />
          <StatCard label="활성 사용자" value={admin.users.active} to="/admin/users?status=ACTIVE" />
        </div>

        <div>
          <div className="mb-2 text-xs font-medium text-fg-muted">전체 프로젝트</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="전체" value={admin.projects.total} to="/admin/projects?status=ALL" />
            <StatCard label="작성 중" value={admin.projects.draft} to="/admin/projects?status=DRAFT" />
            <StatCard label="검토 중" value={admin.projects.review} to="/admin/projects?status=REVIEW" />
            <StatCard label="완료" value={admin.projects.done} to="/admin/projects?status=DONE" />
          </div>
        </div>

        <div>
          <div className="mb-2 text-xs font-medium text-fg-muted">파이프라인</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="실행 중" value={admin.stages.running} to="/admin/projects" />
            <StatCard label="실패" value={admin.stages.failed} to="/admin/projects" />
            <StatCard label="검토 필요" value={admin.stages.needs_review} to="/admin/projects" />
          </div>
        </div>
      </div>
    </div>
  )
}

export function Dashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    dashboard
      .summary()
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="p-10 text-center text-sm text-fg-muted">불러오는 중…</div>
  }
  if (!data) {
    return <FormError message={error ?? UNKNOWN} />
  }

  return (
    <div className="max-w-3xl">
      <NoticeSection />
      <MemberSection data={data} />
      {data.admin && <AdminSection admin={data.admin} />}
    </div>
  )
}
