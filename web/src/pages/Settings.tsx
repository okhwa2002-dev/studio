import { useState } from 'react'
import { FormError } from '../components/FormError'
import { Modal } from '../components/Modal'
import { SettingRow } from '../components/SettingRow'
import { TextField } from '../components/TextField'
import { account } from '../lib/account'
import { usePasswordMinLen } from '../lib/policy'
import { setThemePref, useThemePref, type ThemePref } from '../lib/theme'
import { useSubmit } from '../lib/useSubmit'

const THEME_OPTIONS: { value: ThemePref; label: string }[] = [
  { value: 'system', label: '시스템' },
  { value: 'light', label: '라이트' },
  { value: 'dark', label: '다크' },
]

// 시스템/라이트/다크 3-way 세그먼트. 선택 즉시 setThemePref가 적용·저장한다.
function ThemeControl() {
  const pref = useThemePref()
  return (
    <div className="flex shrink-0 rounded-md border border-line-strong p-0.5">
      {THEME_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => setThemePref(opt.value)}
          className={`rounded px-3 py-1 text-sm ${
            pref === opt.value
              ? 'bg-primary font-medium text-on-primary'
              : 'text-fg-muted hover:bg-surface-muted'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// 비밀번호 변경 폼을 담은 팝업. 성공하면 토스트가 알리고 스스로 닫힌다.
function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const passwordMinLen = usePasswordMinLen()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const { pending: submitting, error, run } = useSubmit()

  // 서버가 최종 강제하지만, 즉각적인 피드백을 위해 클라이언트에서도 먼저 막는다.
  const tooShort = next.length > 0 && next.length < passwordMinLen
  const mismatch = confirm.length > 0 && next !== confirm
  const canSubmit =
    !submitting && current.length > 0 && next.length >= passwordMinLen && next === confirm

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    // 현재 세션은 서버가 쿠키를 회전해 그대로 유지된다. "다른 기기는 다시 로그인해야
    // 한다"는 안내는 원래 설정 화면의 초록 배너가 하던 말이다 — 문장을 잃지 않도록
    // 토스트가 그대로 이어받는다.
    run(() => account.changePassword({ current_password: current, new_password: next }), {
      success: '비밀번호를 변경했습니다. 다른 기기는 다시 로그인해야 합니다.',
      onDone: onClose,
    })
  }

  return (
    <Modal title="비밀번호 변경" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <TextField
          id="current-password"
          label="현재 비밀번호"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <TextField
          id="new-password"
          label="새 비밀번호"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          error={tooShort ? `${passwordMinLen}자 이상 입력해 주세요.` : undefined}
        />
        <TextField
          id="confirm-password"
          label="새 비밀번호 확인"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={mismatch ? '새 비밀번호와 일치하지 않습니다.' : undefined}
        />

        {error && <FormError message={error} />}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-fg-body hover:bg-surface-muted"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
          >
            {submitting ? '변경 중…' : '변경'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export function Settings() {
  const [showPassword, setShowPassword] = useState(false)

  return (
    <div className="max-w-2xl space-y-4">
      <section className="divide-y divide-line-subtle rounded-lg border border-line bg-surface px-6">
        <SettingRow label="테마" description="화면 밝기 모드를 선택합니다.">
          <ThemeControl />
        </SettingRow>
        <SettingRow label="비밀번호" description="계정 로그인에 사용하는 비밀번호를 변경합니다.">
          <button
            onClick={() => setShowPassword(true)}
            className="shrink-0 rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-fg-body hover:bg-surface-muted"
          >
            변경
          </button>
        </SettingRow>
      </section>

      {showPassword && <ChangePasswordModal onClose={() => setShowPassword(false)} />}
    </div>
  )
}
