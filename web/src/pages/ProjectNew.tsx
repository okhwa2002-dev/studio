import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FormError } from '../components/FormError'
import { TextField } from '../components/TextField'
import { ApiError } from '../lib/api'
import { projects } from '../lib/projects'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

export function ProjectNew() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [topic, setTopic] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const detail = await projects.create({ title: title.trim(), topic: topic.trim() })
      navigate(`/projects/${detail.project.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="mb-4 text-lg font-semibold text-slate-900">새 프로젝트</h1>
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
        {error && <FormError message={error} />}
        <button
          type="submit"
          disabled={submitting || !title.trim() || !topic.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          만들기
        </button>
      </form>
    </div>
  )
}
