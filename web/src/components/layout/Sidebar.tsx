import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { adminUsers } from '../../lib/admin'
import { useAuth } from '../../lib/auth'
import { ADMIN_USERS_PATH, NAV, type NavItem } from '../../lib/nav'

// badge가 0이면 아무것도 그리지 않는다 — 0을 보여주면 눈길만 끈다(상단바 종과 같은 규칙).
function NavItemLink({
  item,
  badge = 0,
  onNavigate,
}: {
  item: NavItem
  badge?: number
  onNavigate: () => void
}) {
  return (
    <NavLink
      to={item.path}
      onClick={onNavigate}
      className={({ isActive }) =>
        `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
          isActive ? 'bg-primary font-medium text-on-primary' : 'text-fg-body hover:bg-surface-muted'
        }`
      }
    >
      <span aria-hidden>{item.icon}</span>
      <span className="flex-1">{item.label}</span>
      {badge > 0 && (
        <span
          aria-label={`가입 승인 대기 ${badge}건`}
          className="min-w-5 rounded-full bg-red-600 px-1.5 text-center text-[10px] font-medium leading-5 text-white"
        >
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </NavLink>
  )
}

// 사용자 관리 항목에 붙는 가입 승인 대기 건수. 서랍은 열 때마다 새로 마운트되므로
// (AppLayout이 menuOpen일 때만 그린다) 여는 순간의 최신 값을 보여준다 — 폴링하지 않는다.
function usePendingUserCount(enabled: boolean): number {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!enabled) return
    let alive = true
    // 배지는 부가 정보다. 조회가 실패하면 0으로 두고 그리지 않는다.
    adminUsers
      .list('PENDING')
      .then((rows) => alive && setCount(rows.length))
      .catch(() => alive && setCount(0))
    return () => {
      alive = false
    }
  }, [enabled])

  return count
}

// 콘텐츠 위에 떠서 열리는 서랍이다. 레이아웃 공간을 차지하지 않는다(fixed).
// 여닫는 것은 AppLayout이 정한다 — 여기서는 "메뉴를 골랐다"(onNavigate)와
// "닫기 버튼을 눌렀다"(onClose)만 알린다.
export function Sidebar({ onNavigate, onClose }: { onNavigate: () => void; onClose: () => void }) {
  const { user } = useAuth()
  const common = NAV.filter((item) => !item.adminOnly)
  // 메뉴를 숨기는 것은 UX일 뿐이다. 보안은 서버의 require_admin이 강제한다.
  const isAdmin = user?.role === 'ADMIN'
  const admin = isAdmin ? NAV.filter((item) => item.adminOnly) : []
  const pending = usePendingUserCount(isAdmin)

  return (
    // 화면 최상단(top-0)부터 전체 높이로 열린다. 맨 위 행의 ☰가 닫기 버튼이고,
    // 상단바 좌측(여는 ☰)을 덮는다. h-14로 상단바와 높이를 맞춘다.
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-line bg-surface shadow-xl">
      <div className="flex h-14 items-center gap-3 border-b border-line px-4">
        <button
          onClick={onClose}
          aria-label="메뉴 닫기"
          className="rounded-md px-2 py-1 text-fg-muted hover:bg-surface-muted"
        >
          ☰
        </button>
        <span className="text-lg font-semibold text-fg">Studio</span>
      </div>
      <nav className="flex flex-col gap-1 px-3 pt-3">
        {common.map((item) => (
          <NavItemLink key={item.path} item={item} onNavigate={onNavigate} />
        ))}
        {admin.length > 0 && (
          <>
            <div className="mt-4 border-t border-line px-3 pt-4 pb-1 text-xs font-medium text-fg-muted">
              관리자
            </div>
            {admin.map((item) => (
              <NavItemLink
                key={item.path}
                item={item}
                badge={item.path === ADMIN_USERS_PATH ? pending : 0}
                onNavigate={onNavigate}
              />
            ))}
          </>
        )}
      </nav>
    </aside>
  )
}
