import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { PendingApproval } from './pages/PendingApproval'
import { Register } from './pages/Register'
import { RequireAuth } from './routes/RequireAuth'
import { RequireGuest } from './routes/RequireGuest'

function Routing() {
  const { loading } = useAuth()

  // 세션 복원(GET /auth/me)이 끝나기 전에 라우트를 그리면, user가 아직 null이라
  // 가드가 로그인된 사용자를 순간적으로 /login으로 튕긴다(새로고침 깜빡임).
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        불러오는 중…
      </div>
    )
  }

  return (
    <Routes>
      <Route element={<RequireGuest />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>
      <Route path="/pending" element={<PendingApproval />} />
      <Route element={<RequireAuth />}>
        <Route path="/dashboard" element={<Dashboard />} />
      </Route>
      {/* 알 수 없는 경로는 /dashboard로. 미로그인이면 RequireAuth가 /login으로 보낸다. */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routing />
      </AuthProvider>
    </BrowserRouter>
  )
}
