import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'
import { Button } from '../components/Button'
import { FormError } from '../components/FormError'
import { PasswordResetModal } from '../components/PasswordResetModal'
import { TextField } from '../components/TextField'
import { ApiError, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)
  const [showReset, setShowReset] = useState(false)
  // 재설정 팝업이 성공하면 로그인 폼 상단에 안내를 남긴다(팝업은 닫힌다).
  const [resetNotice, setResetNotice] = useState<string>()

  const state = location.state as { from?: string; notice?: string } | null
  const from = state?.from ?? '/dashboard'
  // 다른 화면이 남긴 1회성 안내(예: 가입 자동 승인으로 곧바로 로그인 가능해진 경우).
  const notice = state?.notice

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
      setError(errorMessage(e))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthCard title="로그인">
      <form onSubmit={onSubmit} className="space-y-4">
        {/* 재설정 안내가 우선이다 — 방금 이 화면에서 일어난 일이라, 다른 화면이 남긴
            1회성 안내보다 최신이다. */}
        {(resetNotice || notice) && (
          <p className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700 dark:bg-green-500/10 dark:text-green-300">
            {resetNotice || notice}
          </p>
        )}
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
      <p className="mt-4 text-center text-sm text-fg-muted">
        계정이 없으신가요?{' '}
        <Link to="/register" className="font-medium text-fg underline">
          회원가입
        </Link>
      </p>
      <p className="mt-2 text-center text-sm text-fg-muted">
        <button
          type="button"
          onClick={() => setShowReset(true)}
          className="font-medium text-fg underline"
        >
          비밀번호를 잊으셨나요?
        </button>
      </p>
      {showReset && (
        <PasswordResetModal
          onClose={() => setShowReset(false)}
          onDone={(msg) => {
            setShowReset(false)
            setResetNotice(msg)
          }}
        />
      )}
    </AuthCard>
  )
}
