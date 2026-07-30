import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './layouts/AppLayout'
import { AuthProvider, useAuth } from './lib/auth'
import { ToastProvider } from './lib/toast'
import { AdminFaqs } from './pages/admin/AdminFaqs'
import { AdminNotices } from './pages/admin/AdminNotices'
import { AdminProjects } from './pages/admin/AdminProjects'
import { AdminSystem } from './pages/admin/AdminSystem'
import { AdminUsers } from './pages/admin/AdminUsers'
import { ChangePasswordRequired } from './pages/ChangePasswordRequired'
import { Dashboard } from './pages/Dashboard'
import { Faqs } from './pages/faqs/Faqs'
import { Login } from './pages/Login'
import { Notices } from './pages/notices/Notices'
import { PendingApproval } from './pages/PendingApproval'
import { ProjectDetail } from './pages/projects/ProjectDetail'
import { Projects } from './pages/projects/Projects'
import { Register } from './pages/Register'
import { Settings } from './pages/Settings'
import { RequireAdmin } from './routes/RequireAdmin'
import { RequireAuth } from './routes/RequireAuth'
import { RequireGuest } from './routes/RequireGuest'

function Routing() {
  const { loading } = useAuth()

  // 세션 복원(GET /auth/me)이 끝나기 전에 라우트를 그리면, user가 아직 null이라
  // 가드가 로그인된 사용자를 순간적으로 /login으로 튕긴다(새로고침 깜빡임).
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-muted text-fg-muted">
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
        {/* AppLayout 밖이다 — 강제 변경 중에는 사이드바의 어느 메뉴도 쓸 수 없다
            (서버가 403으로 막는다). RequireAuth가 이 경로로 보내고, 플래그가
            내려가면 다시 대시보드로 돌려보낸다. */}
        <Route path="/change-password" element={<ChangePasswordRequired />} />
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/notices" element={<Notices />} />
          <Route path="/faqs" element={<Faqs />} />
          <Route path="/settings" element={<Settings />} />
          <Route element={<RequireAdmin />}>
            {/* 가입 승인 전용 화면은 두지 않는다 — 승인·거절은 사용자 관리의 "대기" 탭이 맡는다.
                예전 /admin/approvals 링크는 여기서 그 탭으로 넘긴다. */}
            <Route
              path="/admin/approvals"
              element={<Navigate to="/admin/users?status=PENDING" replace />}
            />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/admin/projects" element={<AdminProjects />} />
            <Route path="/admin/projects/:id" element={<ProjectDetail readOnly />} />
            <Route path="/admin/notices" element={<AdminNotices />} />
            <Route path="/admin/faqs" element={<AdminFaqs />} />
            <Route path="/admin/system" element={<AdminSystem />} />
          </Route>
        </Route>
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
        <ToastProvider>
          <Routing />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
