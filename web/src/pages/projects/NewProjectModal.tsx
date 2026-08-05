import { useState } from 'react'
import { FormError } from '../../components/FormError'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/TextField'
import { useSubmit } from '../../lib/useSubmit'
import { projects } from '../../lib/projects'

// 프로젝트 등록 모달. 생성에 성공하면 목록에 머문 채 onCreated로 알린다(라우팅 없음).
export function NewProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [title, setTitle] = useState('')
  const [topic, setTopic] = useState('')
  const [autoRun, setAutoRun] = useState(false)
  const { pending: submitting, error, run } = useSubmit()

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    // 목록에 머문 채 새로고침만 하므로(주석 참조) 새 행이 어디 생겼는지 눈에 띄지 않는다.
    // 만들어졌다는 사실은 문장으로 말해 준다.
    run(() => projects.create({ title: title.trim(), topic: topic.trim(), auto_run: autoRun }), {
      success: '프로젝트를 만들었습니다.',
      onDone: onCreated,
    })
  }

  return (
    <Modal title="새 프로젝트" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <TextField
          id="title"
          label="제목"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <TextField
          id="topic"
          label="주제"
          required
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <label className="flex items-start gap-2 text-sm text-fg-body">
          <input
            type="checkbox"
            checked={autoRun}
            onChange={(e) => setAutoRun(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            자동으로 끝까지 진행
            <span className="block text-xs text-fg-faint">
              대본·음성·자막·영상을 검토 없이 이어서 만듭니다. 중간에 실패하면 멈춥니다.
            </span>
          </span>
        </label>
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
            disabled={submitting || !title.trim() || !topic.trim()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
          >
            {submitting ? '처리 중…' : '만들기'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
