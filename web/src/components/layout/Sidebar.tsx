import { NavLink } from 'react-router-dom'
import { useAuth } from '../../lib/auth'
import { NAV, type NavItem } from '../../lib/nav'

function NavItemLink({ item, onNavigate }: { item: NavItem; onNavigate: () => void }) {
  return (
    <NavLink
      to={item.path}
      onClick={onNavigate}
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

// 콘텐츠 위에 떠서 열리는 서랍이다. 레이아웃 공간을 차지하지 않는다(fixed).
// 여닫는 것은 AppLayout이 정한다 — 여기서는 "메뉴를 골랐다"(onNavigate)와
// "닫기 버튼을 눌렀다"(onClose)만 알린다.
export function Sidebar({ onNavigate, onClose }: { onNavigate: () => void; onClose: () => void }) {
  const { user } = useAuth()
  const common = NAV.filter((item) => !item.adminOnly)
  // 메뉴를 숨기는 것은 UX일 뿐이다. 보안은 서버의 require_admin이 강제한다.
  const admin = user?.role === 'ADMIN' ? NAV.filter((item) => item.adminOnly) : []

  return (
    // 화면 최상단(top-0)부터 전체 높이로 열린다. 맨 위 행의 ☰가 닫기 버튼이고,
    // 상단바 좌측(여는 ☰)을 덮는다. h-14로 상단바와 높이를 맞춘다.
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-slate-200 bg-white shadow-xl">
      <div className="flex h-14 items-center gap-3 border-b border-slate-200 px-4">
        <button
          onClick={onClose}
          aria-label="메뉴 닫기"
          className="rounded-md px-2 py-1 text-slate-600 hover:bg-slate-100"
        >
          ☰
        </button>
        <span className="text-lg font-semibold text-slate-900">Studio</span>
      </div>
      <nav className="flex flex-col gap-1 px-3 pt-3">
        {common.map((item) => (
          <NavItemLink key={item.path} item={item} onNavigate={onNavigate} />
        ))}
        {admin.length > 0 && (
          <>
            <div className="mt-4 border-t border-slate-200 px-3 pt-4 pb-1 text-xs font-medium text-slate-500">
              관리자
            </div>
            {admin.map((item) => (
              <NavItemLink key={item.path} item={item} onNavigate={onNavigate} />
            ))}
          </>
        )}
      </nav>
    </aside>
  )
}
