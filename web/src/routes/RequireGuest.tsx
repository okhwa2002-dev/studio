import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export function RequireGuest() {
  const { user } = useAuth()

  if (user) {
    return <Navigate to="/dashboard" replace />
  }
  return <Outlet />
}
