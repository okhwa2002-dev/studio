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
  return <Outlet />
}
