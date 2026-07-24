import { useState } from 'react'
import { useAuth } from '../../lib/auth'

export function UserMenu() {
  const { user, logout } = useAuth()
  const [pending, setPending] = useState(false)

  const onLogout = async () => {
    setPending(true)
    try {
      await logout()
      // user가 null이 되면 RequireAuth가 /login으로 보낸다. 여기서 navigate하지 않는다.
    } catch {
      // 요청이 실패해도 logout()이 로컬 세션은 이미 정리한다.
      // 여기서는 미처리 거부(unhandled rejection)로 새지 않도록 삼키기만 한다.
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-slate-600">
        {user?.name} · {user?.role}
      </span>
      <button
        onClick={onLogout}
        disabled={pending}
        className="rounded-md border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {pending ? '처리 중…' : '로그아웃'}
      </button>
    </div>
  )
}
