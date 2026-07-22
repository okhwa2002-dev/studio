import { useState } from 'react'
import { FormError } from '../../components/FormError'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/TextField'
import { ApiError } from '../../lib/api'
import { projects } from '../../lib/projects'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

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
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await projects.create({ title: title.trim(), topic: topic.trim(), auto_run: autoRun })
      onCreated()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
      setSubmitting(false)
    }
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
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={autoRun}
            onChange={(e) => setAutoRun(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            자동으로 끝까지 진행
            <span className="block text-xs text-slate-400">
              대본·음성·자막·영상을 검토 없이 이어서 만듭니다. 중간에 실패하면 멈춥니다.
            </span>
          </span>
        </label>
        {error && <FormError message={error} />}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={submitting || !title.trim() || !topic.trim()}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {submitting ? '처리 중…' : '만들기'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
