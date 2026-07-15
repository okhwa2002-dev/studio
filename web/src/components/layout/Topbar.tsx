import { useLocation } from 'react-router-dom'
import { navTitle } from '../../lib/nav'
import { UserMenu } from './UserMenu'

type Props = {
  menuOpen: boolean
  onToggleMenu: () => void
}

export function Topbar({ menuOpen, onToggleMenu }: Props) {
  const { pathname } = useLocation()

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
        <h1 className="text-base font-semibold text-slate-900">{navTitle(pathname)}</h1>
      </div>
      <UserMenu />
    </header>
  )
}
