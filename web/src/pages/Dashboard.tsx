import { useAuth } from '../lib/auth'

// 앞으로 사이드바와 프로젝트 목록이 들어올 자리다. 지금은 인증 확인용 빈 화면.
export function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <header className="mx-auto flex max-w-3xl items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">대시보드</h1>
          <p className="mt-1 text-sm text-slate-600">
            {user?.email} · {user?.role}
          </p>
        </div>
        <button
          onClick={logout}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700"
        >
          로그아웃
        </button>
      </header>
    </div>
  )
}
