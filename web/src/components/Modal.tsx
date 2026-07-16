import { useEffect, type ReactNode } from 'react'

// 화면 중앙에 뜨는 모달. 배경 클릭·Esc·닫기(✕) 버튼으로 닫힌다.
// 도메인은 모른다 — 무엇을 담을지·언제 닫을지는 쓰는 쪽이 정한다(children/onClose).
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    // 배경(오버레이) 클릭은 닫기. 패널 안 클릭은 stopPropagation으로 살린다.
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <button
            onClick={onClose}
            aria-label="닫기"
            className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
