import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from './api'
import { useToast } from './toast'

type RunOptions<T> = {
  // 성공 토스트 문구. 넘기지 않으면 토스트를 띄우지 않는다 — 결과가 화면에 곧바로
  // 드러나는 동작(단계 실행 → 배지가 RUNNING, 비밀번호 초기화 → 임시 비번 표시)은
  // 토스트가 화면이 이미 한 말을 반복하는 꼴이 된다.
  success?: string
  // 실패를 어디에 보여줄지. 기본은 인라인이다 — 저장 실패의 대부분은 "제목이 비었다"
  // 처럼 입력을 고쳐야 하는 오류라, 고칠 대상 옆에 붙어 있어야 하고 3.5초 뒤 사라지면
  // 안 된다. 목록에서 바로 누르는 승인·잠금 해제처럼 붙일 폼이 없을 때만 toast를 쓴다.
  errorAs?: 'inline' | 'toast'
  // 성공 후 처리 — 모달 닫기 · 목록 새로고침 · 화면 이동.
  onDone?: (result: T) => void
}

// 저장·삭제·수정 한 번의 수명 전체를 감싼다. 화면마다 복붙되던 pending state ·
// try/catch/finally · 오류 문자열화 · 토스트 호출을 여기로 모아, 호출부에는
// "무엇을 하고, 성공하면 뭐라고 말하고, 그다음 뭘 할지"만 남긴다.
export function useSubmit() {
  const toast = useToast()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 진행 중 판정은 state가 아니라 ref로 한다. state로 보면 같은 렌더의 클로저가 옛 값을
  // 들고 있어 빠른 연타가 두 번 통과할 수 있다. 버튼 disabled는 그대로 두고(눌리지 않는
  // 것이 보여야 한다) 여기는 마지막 방어선이다.
  const running = useRef(false)

  // onDone이 모달을 닫거나(setEditing(null)) 화면을 옮기면(navigate) 이 컴포넌트는
  // 사라진다. 실제로 AdminNotices의 save()는 자기 안에서 모달을 닫으므로, await가
  // 돌아온 시점에 이미 언마운트돼 있다. 그 뒤의 setState는 아무 일도 하지 않아야 한다.
  //
  // 토스트는 이 가드 밖이다 — 프로젝트를 지우고 목록으로 돌아간 화면에서도
  // "삭제했습니다"는 보여야 한다.
  //
  // onDone도 이 가드 밖이다. onDone은 이 컴포넌트가 아니라 아직 살아 있는 부모의 일을
  // 하는 경우가 있다 — 예를 들어 AdminUsers.act의 onDone은 부모의 load()를 불러 목록을
  // 다시 받아온다. 언마운트된 자식 기준으로 막으면 그 일이 조용히 사라진다.
  const alive = useRef(true)
  useEffect(() => {
    // 값을 effect 안에서 다시 켠다. StrictMode는 마운트 직후 cleanup을 한 번 돌리는데,
    // 선언부에서만 true를 주면 그 뒤로 영영 false에 머문다.
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  // run은 절대 reject하지 않는다 — 실패도 내부에서 처리하고 정상 반환한다. 그래서
  // AdminUsers.tsx의 onConfirm={async () => { await act(...); setConfirming(null) }}처럼
  // 호출부가 await 뒤에 정리 코드를 그냥 이어 붙일 수 있다(성공·실패 어느 쪽이든
  // 대화상자를 닫는다). try/catch 없이 체이닝해도 되는 이유다.
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, options: RunOptions<T> = {}): Promise<void> => {
      if (running.current) return
      running.current = true
      setPending(true)
      setError(null)
      let result: T
      try {
        result = await fn()
      } catch (e) {
        running.current = false
        if (alive.current) setPending(false)
        const message = errorMessage(e)
        if (options.errorAs === 'toast') toast.error(message)
        // 토스트로 보낸 오류가 화면 어딘가에 함께 남지 않도록, error는 인라인일 때만 채운다.
        else if (alive.current) setError(message)
        return
      }
      // fn()의 try 밖이다 — onDone(success 콜백)이 던지면 그건 API 실패가 아니라 내
      // 성공 처리 코드의 버그이므로, 위 catch가 그걸 삼켜 "저장 실패"로 잘못 보고하면
      // 안 된다.
      try {
        // pending을 onDone보다 먼저 내린다 — onDone이 이 컴포넌트를 언마운트시키므로
        // 순서가 반대면 사라진 뒤에 setState하는 꼴이 된다.
        if (alive.current) setPending(false)
        if (options.success) toast.success(options.success)
        options.onDone?.(result)
      } finally {
        running.current = false
      }
    },
    [toast],
  )

  // 폼을 다시 열 때처럼 호출부가 직접 오류를 지우는 자리에서 쓴다.
  const clearError = useCallback(() => setError(null), [])

  return { pending, error, run, clearError }
}
