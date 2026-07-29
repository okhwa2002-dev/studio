import { useEffect, type ReactNode } from 'react'

// 화면 중앙에 뜨는 모달. Esc와 닫기(✕) 버튼으로만 닫힌다.
// 도메인은 모른다 — 무엇을 담을지·언제 닫을지는 쓰는 쪽이 정한다(children/onClose).
//
// 배경 클릭으로는 닫지 않는다. 모달 안에서 텍스트를 드래그하다 배경에서 손을 떼는 일이
// 잦은데, click은 mousedown과 mouseup 타깃의 최근접 공통 조상에서 발생하므로 그 경우
// target이 배경이 된다 — 이벤트가 패널을 거치지 않아 패널에서 막을 수도 없다.
// 누른 곳과 뗀 곳을 따로 보면 구분할 수는 있지만, 입력 폼을 담는 모달에서 배경 클릭은
// 작성 중인 내용을 통째로 날리는 실수에 더 가깝다. 닫는 길은 ✕와 Esc 둘로 둔다.
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
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-overlay p-4">
      <div
        className="w-full max-w-lg rounded-lg bg-surface p-6 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-fg">{title}</h2>
          <button
            onClick={onClose}
            aria-label="닫기"
            className="rounded-md px-2 py-1 text-fg-muted hover:bg-surface-muted"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
