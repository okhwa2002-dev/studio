import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthCard } from '../components/AuthCard'
import { FormError } from '../components/FormError'
import { TextField } from '../components/TextField'
import { account } from '../lib/account'
import { useAuth } from '../lib/auth'
import { usePasswordMinLen } from '../lib/policy'
import { useSubmit } from '../lib/useSubmit'

// 관리자가 비밀번호를 초기화한 사용자가 로그인하면 RequireAuth가 이 화면으로 보낸다.
// AppLayout 밖의 전체 화면이다 — 강제 변경 중에는 다른 메뉴를 눌러도 서버가 403으로
// 막으므로, 사이드바를 보여주면 눌러볼 수 있는 것처럼 오해만 준다.
//
// Settings의 ChangePasswordModal과 폼 구조가 거의 같지만 공용화하지 않는다: 하나는
// 모달이고 하나는 전체 화면이며, 취소 버튼 유무·성공 후 동작·라벨·도움말이 모두 다르다.
// 차이를 전부 props로 받는 컴포넌트가 되면 지금 두 파일로 나뉘어 있는 것보다 읽기 어렵다.
export function ChangePasswordRequired() {
  const passwordMinLen = usePasswordMinLen()
  const { refresh, logout } = useAuth()
  const navigate = useNavigate()
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
    run(
      async () => {
        await account.changePassword({ current_password: current, new_password: next })
        // 서버가 쿠키를 회전해 현재 세션은 유지된다. /auth/me를 다시 읽어
        // must_change_password가 내려간 것을 반영하면 아래 가드가 통과한다.
        // refresh까지 run 안에 넣는 이유: 둘 중 하나라도 못 끝내면 이 화면을 떠나면
        // 안 되고, 버튼도 그때까지 잠겨 있어야 한다.
        try {
          await refresh()
        } catch {
          // 비밀번호는 이미 바뀌었다. 세션 상태를 못 읽었을 뿐인데 오류를 띄우면, 사용자는
          // 못 쓰게 된 임시 비밀번호가 남은 폼을 보고 다시 시도하다 "틀렸다"는 말을 듣는다.
          // 틀린 안내 대신 깨끗하게 다시 로그인시킨다.
          await logout().catch(() => {
            // 로그아웃 요청이 실패해도 로컬 세션은 이미 지워졌으므로(auth.tsx의 finally)
            // 재로그인 유도는 그대로 진행한다.
          })
          return false
        }
        return true
      },
      {
        // 화면이 통째로 바뀌므로 무슨 일이 일어났는지 말해 주는 문장이 필요하다.
        success: '비밀번호를 변경했습니다.',
        onDone: (refreshed) => {
          // 로그아웃된 경우 RequireAuth가 이미 로그인 화면으로 보내므로, 여기서
          // 대시보드로 옮기면 두 이동이 서로 충돌한다.
          if (refreshed) navigate('/dashboard', { replace: true })
        },
      },
    )
  }

  return (
    <AuthCard title="비밀번호 변경 필요">
      <p className="mb-6 text-sm leading-relaxed text-fg-body">
        관리자가 비밀번호를 초기화했습니다. 계속하려면 새 비밀번호를 설정해 주세요.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <TextField
          id="temp-password"
          label="임시 비밀번호"
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

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          {submitting ? '변경 중…' : '변경하기'}
        </button>
      </form>
      {/* 임시 비밀번호를 관리자에게 다시 물어봐야 하는 사용자가 이 화면에 갇히지 않게 한다. */}
      <p className="mt-6 text-center text-sm text-fg-muted">
        <button onClick={logout} className="font-medium text-fg underline">
          로그아웃
        </button>
      </p>
    </AuthCard>
  )
}
