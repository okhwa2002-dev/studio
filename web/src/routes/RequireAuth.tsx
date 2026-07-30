import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// 이 가드는 UX일 뿐이다. 실제 보안은 서버의 current_user/require_admin이 강제한다.
export function RequireAuth() {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    // 원래 가려던 경로를 기억해 두고, 로그인 성공 후 그곳으로 돌려보낸다.
    // 쿼리스트링·해시까지 포함해야 딥링크(예: /dashboard?tab=x)가 보존된다.
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search + location.hash }}
      />
    )
  }

  // 관리자가 비밀번호를 초기화한 계정은 바꾸기 전까지 이 화면 밖으로 못 나간다.
  // 반대로 플래그가 내려간 뒤 이 경로에 남아 있으면 대시보드로 돌려보낸다.
  //
  // 로그인 직후에는 /login → (RequireGuest가) /dashboard → 여기서 /change-password로
  // 두 번 튄다. RequireGuest에도 같은 판단을 넣으면 한 번에 갈 수 있지만, 그러면 플래그를
  // 보는 곳이 두 곳이 되어 한쪽만 고치는 실수가 생긴다. 리다이렉트는 네트워크 왕복 없는
  // 렌더 한 번이므로 게이트를 여기 한 곳에만 둔다.
  const atChangePage = location.pathname === '/change-password'
  if (user.must_change_password && !atChangePage) {
    return <Navigate to="/change-password" replace />
  }
  if (!user.must_change_password && atChangePage) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
