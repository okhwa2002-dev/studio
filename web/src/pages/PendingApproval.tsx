import { Link } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'

// 폴링하지 않는 정적 안내 화면이다. 승인 여부는 다시 로그인해 보면 알 수 있다.
export function PendingApproval() {
  return (
    <AuthCard title="승인 대기 중">
      <p className="text-sm leading-relaxed text-slate-700">
        관리자 승인 후 로그인할 수 있습니다. 승인이 완료되면 다시 로그인해 주세요.
      </p>
      <p className="mt-6 text-center text-sm text-slate-600">
        <Link to="/login" className="font-medium text-slate-900 underline">
          로그인 화면으로
        </Link>
      </p>
    </AuthCard>
  )
}
