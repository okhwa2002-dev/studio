import { NavLink } from 'react-router-dom'
import { useAuth } from '../../lib/auth'
import { NAV, type NavItem } from '../../lib/nav'

function NavItemLink({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.path}
      className={({ isActive }) =>
        `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
          isActive ? 'bg-slate-900 font-medium text-white' : 'text-slate-700 hover:bg-slate-100'
        }`
      }
    >
      <span aria-hidden>{item.icon}</span>
      {item.label}
    </NavLink>
  )
}

export function Sidebar() {
  const { user } = useAuth()
  const common = NAV.filter((item) => !item.adminOnly)
  // 메뉴를 숨기는 것은 UX일 뿐이다. 보안은 서버의 require_admin이 강제한다.
  const admin = user?.role === 'ADMIN' ? NAV.filter((item) => item.adminOnly) : []

  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="px-5 py-4 text-lg font-semibold text-slate-900">Studio</div>
      <nav className="flex flex-col gap-1 px-3">
        {common.map((item) => (
          <NavItemLink key={item.path} item={item} />
        ))}
        {admin.length > 0 && (
          <>
            <div className="mt-4 border-t border-slate-200 px-3 pt-4 pb-1 text-xs font-medium text-slate-500">
              관리자
            </div>
            {admin.map((item) => (
              <NavItemLink key={item.path} item={item} />
            ))}
          </>
        )}
      </nav>
    </aside>
  )
}
