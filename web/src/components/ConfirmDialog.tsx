import { FormError } from './FormError'
import { Modal } from './Modal'

// 실행 전에 한 번 더 확인받는 대화상자. Modal을 재사용하므로 다크모드·디자인이 일관된다.
// 도메인은 모른다 — 무엇을 확인할지·확인 시 무엇을 할지는 쓰는 쪽이 정한다.
export function ConfirmDialog({
  title,
  message,
  confirmLabel = '확인',
  cancelLabel = '취소',
  tone = 'default',
  busy = false,
  error,
  onConfirm,
  onClose,
}: {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'default' | 'danger' // danger는 거절·삭제처럼 되돌리기 어려운 동작에 쓴다
  busy?: boolean // 처리 중이면 버튼을 잠근다
  // 확인 동작이 실패했을 때의 메시지. 여기 두는 이유: 실패해도 대화상자를 닫으면 안 되는
  // 경우(예: "실행 중이라 삭제할 수 없다")가 있고, 그때 메시지를 보여줄 자리가 필요하다.
  // 호출부마다 따로 만들지 않도록 확인 동작의 공통 부품인 여기서 처리한다.
  error?: string | null
  onConfirm: () => void
  onClose: () => void
}) {
  const confirmClass =
    tone === 'danger'
      ? 'bg-red-600 text-white hover:bg-red-700'
      : 'bg-primary text-on-primary'
  return (
    <Modal title={title} onClose={onClose}>
      <p className="text-sm text-fg-body">{message}</p>
      {error && (
        <div className="mt-4">
          <FormError message={error} />
        </div>
      )}
      <div className="mt-6 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={`rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 ${confirmClass}`}
        >
          {busy ? '처리 중…' : confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
