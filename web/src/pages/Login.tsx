import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'
import { Button } from '../components/Button'
import { FormError } from '../components/FormError'
import { TextField } from '../components/TextField'
import { ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/dashboard'

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    setPending(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        // 승인 대기·거절·비활성. 서버가 셋을 하나의 403으로 응답하므로 프론트도 구분하지 않는다.
        navigate('/pending', { replace: true })
        return
      }
      // 401 메시지는 서버가 계정 열거 방지를 위해 통일해 둔 문구다. 그대로 보여준다.
      setError(e instanceof ApiError ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthCard title="로그인">
      <form onSubmit={onSubmit} className="space-y-4">
        <FormError message={error} />
        <TextField
          id="email"
          label="이메일"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          id="password"
          label="비밀번호"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" pending={pending}>
          로그인
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        계정이 없으신가요?{' '}
        <Link to="/register" className="font-medium text-slate-900 underline">
          회원가입
        </Link>
      </p>
    </AuthCard>
  )
}
