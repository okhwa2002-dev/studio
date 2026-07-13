import { useState } from 'react'
import { Button } from '../components/Button'
import { useAuth } from '../lib/auth'

// 앞으로 사이드바와 프로젝트 목록이 들어올 자리다. 지금은 인증 확인용 빈 화면.
export function Dashboard() {
  const { user, logout } = useAuth()
  const [pending, setPending] = useState(false)

  const onLogout = async () => {
    setPending(true)
    try {
      await logout()
    } catch {
      // 요청이 실패해도 logout()이 로컬 세션은 이미 정리한다. 여기서는 미처리
      // 거부(unhandled rejection)로 새지 않도록 삼키기만 한다.
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <header className="mx-auto flex max-w-3xl items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">대시보드</h1>
          <p className="mt-1 text-sm text-slate-600">
            {user?.email} · {user?.role}
          </p>
        </div>
        {/* Button은 w-full로 스타일되어 있어, 헤더 안에서 늘어나지 않도록 감싼다. */}
        <div className="w-auto">
          <Button onClick={onLogout} pending={pending}>
            로그아웃
          </Button>
        </div>
      </header>
    </div>
  )
}
