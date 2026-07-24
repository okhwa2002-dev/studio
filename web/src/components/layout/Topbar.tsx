import { Logo } from './Logo'
import { UserMenu } from './UserMenu'

type Props = {
  menuOpen: boolean
  onToggleMenu: () => void
}

// 상단바는 브랜드와 전역 조작(메뉴·사용자)만 맡는다.
// "지금 어디인지"는 본문 상단의 제목이 알려준다(AppLayout).
export function Topbar({ menuOpen, onToggleMenu }: Props) {
  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        {/* 메뉴 서랍은 기본이 닫힘이다. 여는 길은 항상 여기 하나뿐이다. */}
        <button
          onClick={onToggleMenu}
          aria-label={menuOpen ? '메뉴 닫기' : '메뉴 열기'}
          aria-expanded={menuOpen}
          className="rounded-md px-2 py-1 text-slate-600 hover:bg-slate-100"
        >
          ☰
        </button>
        <Logo />
      </div>
      <UserMenu />
    </header>
  )
}
