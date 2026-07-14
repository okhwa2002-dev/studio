import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

// 이 가드는 UX일 뿐이다. /admin/*의 실제 차단은 서버의 require_admin이 강제한다.
export function RequireAdmin() {
  const { user } = useAuth()

  if (user?.role !== 'ADMIN') {
    return <Navigate to="/dashboard" replace />
  }
  return <Outlet />
}
