import { AuthProvider, useAuth } from './lib/auth'

function AuthProbe() {
  const { user, loading, logout } = useAuth()

  if (loading) return <p className="text-slate-500">세션 확인 중…</p>

  return (
    <div className="space-y-3 text-center">
      <p className="text-lg font-semibold text-slate-900">
        {user ? `로그인됨: ${user.email} (${user.role})` : '로그인되지 않음'}
      </p>
      {user && (
        <button onClick={logout} className="rounded-md bg-slate-900 px-3 py-2 text-white">
          로그아웃
        </button>
      )}
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="rounded-lg bg-white px-6 py-4 shadow">
          <AuthProbe />
        </div>
      </div>
    </AuthProvider>
  )
}
