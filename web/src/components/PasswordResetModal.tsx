import { useState, type FormEvent } from 'react'
import { Button } from './Button'
import { FormError } from './FormError'
import { Modal } from './Modal'
import { TextField } from './TextField'
import { api, errorMessage } from '../lib/api'
import { usePasswordMinLen } from '../lib/policy'

export function PasswordResetModal({
  onClose,
  onDone,
}: {
  onClose: () => void
  onDone: (msg: string) => void
}) {
  const passwordMinLen = usePasswordMinLen()
  const [step, setStep] = useState<'email' | 'code' | 'password'>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)

  async function requestCode(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    setPending(true)
    try {
      await api.post('/auth/password-reset/request', { email })
      setStep('code')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setPending(false)
    }
  }

  // 2단계: 인증코드가 맞는지만 확인한다(아직 바꾸지 않는다). 맞으면 3단계로 넘어가며
  // 입력한 코드는 그대로 들고 있다가 마지막 변경 요청에 함께 보낸다.
  async function verifyCode(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    setPending(true)
    try {
      await api.post('/auth/password-reset/verify', { email, code })
      setStep('password')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setPending(false)
    }
  }

  // 3단계: 확인된 코드로 새 비밀번호를 실제로 변경한다.
  async function confirmReset(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    if (next.length < passwordMinLen) {
      setError(`새 비밀번호는 ${passwordMinLen}자 이상이어야 합니다.`)
      return
    }
    if (next !== confirm) {
      setError('새 비밀번호가 일치하지 않습니다.')
      return
    }
    setPending(true)
    try {
      await api.post('/auth/password-reset/confirm', { email, code, new_password: next })
      onDone('비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal title="비밀번호 재설정" onClose={onClose}>
      {step === 'email' ? (
        <form onSubmit={requestCode} className="space-y-4">
          <FormError message={error} />
          <TextField
            id="reset-email"
            label="이메일"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Button type="submit" pending={pending}>
            인증코드 받기
          </Button>
        </form>
      ) : step === 'code' ? (
        <form onSubmit={verifyCode} className="space-y-4">
          <p className="rounded-md bg-surface-muted px-4 py-2 text-sm text-fg-muted">
            인증코드를 발송했습니다. 메일함을 확인해 주세요.
          </p>
          <FormError message={error} />
          <TextField
            id="reset-code"
            label="인증코드(6자리)"
            inputMode="numeric"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <Button type="submit" pending={pending}>
            인증코드 확인
          </Button>
        </form>
      ) : (
        <form onSubmit={confirmReset} className="space-y-4">
          <p className="rounded-md bg-surface-muted px-4 py-2 text-sm text-fg-muted">
            인증이 완료되었습니다. 새 비밀번호를 입력하세요.
          </p>
          <FormError message={error} />
          <TextField
            id="reset-new"
            label="새 비밀번호"
            type="password"
            autoComplete="new-password"
            required
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <TextField
            id="reset-confirm"
            label="새 비밀번호 확인"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          <Button type="submit" pending={pending}>
            비밀번호 변경
          </Button>
        </form>
      )}
    </Modal>
  )
}
