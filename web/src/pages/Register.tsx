import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'
import { Button } from '../components/Button'
import { FormError } from '../components/FormError'
import { TextField } from '../components/TextField'
import { ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

type FieldErrors = {
  email?: string
  password?: string
  confirm?: string
}

// 클라이언트 검증은 UX 보조일 뿐 신뢰 경계가 아니다. 진짜 검증은 서버가 한다.
function validate(email: string, password: string, confirm: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = '올바른 이메일 형식이 아닙니다.'
  }
  if (password.length < 8) {
    errors.password = '비밀번호는 8자 이상이어야 합니다.'
  }
  if (password !== confirm) {
    errors.confirm = '비밀번호가 일치하지 않습니다.'
  }
  return errors
}

export function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(undefined)

    const errors = validate(email, password, confirm)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return

    setPending(true)
    try {
      await register(email, password)
      // 가입한 사용자는 status=pending이라 로그인할 수 없다. 대기 안내로 보낸다.
      navigate('/pending', { replace: true })
    } catch (e) {
      // 409 = 이미 등록된 이메일. 서버 메시지를 그대로 보여준다.
      setError(e instanceof ApiError ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthCard title="회원가입">
      <form onSubmit={onSubmit} className="space-y-4">
        <FormError message={error} />
        <TextField
          id="email"
          label="이메일"
          type="email"
          autoComplete="email"
          required
          value={email}
          error={fieldErrors.email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField
          id="password"
          label="비밀번호"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          error={fieldErrors.password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          id="confirm"
          label="비밀번호 확인"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          error={fieldErrors.confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <Button type="submit" pending={pending}>
          가입하기
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">
        이미 계정이 있으신가요?{' '}
        <Link to="/login" className="font-medium text-slate-900 underline">
          로그인
        </Link>
      </p>
    </AuthCard>
  )
}
