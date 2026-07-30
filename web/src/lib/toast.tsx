import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'

// 저장 완료·실패처럼 잠깐 뜨고 사라지는 안내(토스트)를 앱 어디서나 띄운다.
// 공지(notices) 도메인과는 무관하다 — 이건 순수 UI 피드백이다.
type ToastKind = 'success' | 'error'
type Toast = { id: number; kind: ToastKind; message: string }
type ToastApi = { success: (message: string) => void; error: (message: string) => void }

const ToastContext = createContext<ToastApi | null>(null)
const DURATION_MS = 3500

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const seq = useRef(0)

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = (seq.current += 1)
      setToasts((prev) => [...prev, { id, kind, message }])
      window.setTimeout(() => remove(id), DURATION_MS)
    },
    [remove],
  )

  // api는 안정적이어야 한다(자식이 useEffect 의존성에 넣어도 매번 안 바뀌게).
  const api = useMemo<ToastApi>(
    () => ({ success: (m) => push('success', m), error: (m) => push('error', m) }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={remove} />
    </ToastContext.Provider>
  )
}

// 상단 중앙에 쌓인다(우측 하단 테마 토글과 겹치지 않게). 모달(z-40) 위로 보이도록 z-50.
function ToastViewport({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed left-1/2 top-4 z-50 flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((t) => (
        <button
          key={t.id}
          onClick={() => onDismiss(t.id)}
          className={`pointer-events-auto rounded-md px-4 py-2 text-sm font-medium text-white shadow-lg ${
            t.kind === 'success' ? 'bg-green-600' : 'bg-red-600'
          }`}
        >
          {t.message}
        </button>
      ))}
    </div>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (ctx === null) {
    throw new Error('useToast는 ToastProvider 안에서만 사용할 수 있습니다.')
  }
  return ctx
}
