import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { PinnedBadge } from '../../components/PinnedBadge'
import { errorMessage, UNKNOWN_MESSAGE } from '../../lib/api'
import { isY, notices, type Notice } from '../../lib/notices'
import { useUnreadNotices } from '../../lib/unreadNotices'

const NOT_FOUND = '공지사항을 찾을 수 없습니다.'

// 목록에서 넘어왔다면 그때의 검색어·페이지를 state로 받아 두고, [목록으로]가
// 그 자리로 되돌려 준다. URL로 바로 들어온 경우에는 값이 없어 기본 목록으로 간다.
type FromList = { from?: string }

export function NoticeDetail() {
  const { id } = useParams<{ id: string }>()
  const noticeId = Number(id)
  const listSearch = (useLocation().state as FromList | null)?.from ?? ''
  const [notice, setNotice] = useState<Notice | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { refresh } = useUnreadNotices()

  useEffect(() => {
    // /notices/abc 같은 주소로 들어오면 서버까지 갈 것도 없다.
    if (!Number.isInteger(noticeId)) {
      setError(NOT_FOUND)
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)
    notices.detail(noticeId).then(
      (row) => {
        setNotice(row)
        setLoading(false)
        if (row.is_read) return
        // 읽음 처리는 부가 정보다. 실패해도 본문은 이미 보이므로 조용히 넘어가고,
        // NEW 배지가 남았다가 다음 열람 때 다시 시도된다. 거절 핸들러를 then의 두 번째
        // 인자로 두는 것은, 성공 콜백 안에서 나는 예외까지 삼키지 않기 위해서다.
        notices.markRead(row.id).then(() => refresh(), () => {})
      },
      (e) => {
        setError(errorMessage(e))
        setLoading(false)
      },
    )
  }, [noticeId, refresh])

  if (loading) return <div className="p-10 text-center text-sm text-fg-muted">불러오는 중…</div>
  if (!notice) return <FormError message={error ?? UNKNOWN_MESSAGE} />

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-2">
        {isY(notice.pinned_yn) && <PinnedBadge />}
        <h1 className="text-lg font-semibold text-fg">{notice.title}</h1>
      </div>
      {/* 백엔드가 로컬 naive ISO 문자열을 준다. Date로 파싱하면 타임존 보정이 끼어드니
          문자열을 그대로 자른다. */}
      <p className="mt-1 text-sm text-fg-muted">{notice.starts_at.slice(0, 10)}</p>

      {/* 본문은 일반 텍스트다. 줄바꿈을 살려서 그대로 보여준다.
          테두리 상자는 프로젝트 상세의 단계 카드와 같은 형태다. */}
      <div className="mt-4 rounded-lg border border-line p-4">
        <p className="text-sm whitespace-pre-wrap text-fg-body">{notice.body}</p>
      </div>

      <div className="mt-6">
        <Link
          to={`/notices${listSearch}`}
          className="inline-block rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-fg-body hover:bg-surface-muted"
        >
          ← 목록으로
        </Link>
      </div>
    </div>
  )
}
