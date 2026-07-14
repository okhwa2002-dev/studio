import { useLocation } from 'react-router-dom'
import { navTitle } from '../../lib/nav'
import { UserMenu } from './UserMenu'

export function Topbar() {
  const { pathname } = useLocation()

  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <h1 className="text-base font-semibold text-slate-900">{navTitle(pathname)}</h1>
      <UserMenu />
    </header>
  )
}
