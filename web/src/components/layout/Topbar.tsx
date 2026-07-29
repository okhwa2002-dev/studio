import { Link } from 'react-router-dom'
import { useUnreadNotices } from '../../lib/unreadNotices'
import { Logo } from './Logo'
import { UserMenu } from './UserMenu'

type Props = {
  menuOpen: boolean
  onToggleMenu: () => void
}

// 안 읽은 공지가 없으면 아무것도 그리지 않는다 — 0을 보여주면 눈길만 끈다.
function NoticeBell() {
  const { count } = useUnreadNotices()

  return (
    <Link
      to="/notices"
      aria-label={count > 0 ? `공지사항 ${count}건 안 읽음` : '공지사항'}
      className="relative rounded-md px-2 py-1 text-fg-muted hover:bg-surface-muted"
    >
      <span aria-hidden>📢</span>
      {count > 0 && (
        <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-red-600 px-1 text-center text-[10px] font-medium leading-4 text-white">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </Link>
  )
}

// 상단바는 브랜드와 전역 조작(메뉴·공지·사용자)만 맡는다.
// "지금 어디인지"는 본문 상단의 제목이 알려준다(AppLayout).
export function Topbar({ menuOpen, onToggleMenu }: Props) {
  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-6">
      <div className="flex items-center gap-3">
        {/* 메뉴 서랍은 기본이 닫힘이다. 여는 길은 항상 여기 하나뿐이다. */}
        <button
          onClick={onToggleMenu}
          aria-label={menuOpen ? '메뉴 닫기' : '메뉴 열기'}
          aria-expanded={menuOpen}
          className="rounded-md px-2 py-1 text-fg-muted hover:bg-surface-muted"
        >
          ☰
        </button>
        <Logo />
      </div>
      <div className="flex items-center gap-3">
        <NoticeBell />
        <UserMenu />
      </div>
    </header>
  )
}
