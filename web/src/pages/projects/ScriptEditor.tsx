import { useState } from 'react'
import { FormError } from '../../components/FormError'
import { TextField } from '../../components/TextField'
import type { ScriptEditPayload, ScriptOutput } from '../../lib/projects'

// 서버의 _MAX_SCENES와 같은 값. 넘으면 422가 나므로 화면에서 먼저 막는다.
const MAX_SCENES = 20

type SceneDraft = { narration: string; on_screen: string }

const INPUT_CLASS =
  'w-full rounded-md border border-line-strong px-3 py-2 text-sm text-fg outline-none focus:border-fg'

// 대본 하나를 받아 수정된 대본을 돌려준다. 서버를 직접 부르지 않고 onSave로 부모에 넘긴다 —
// ProjectDetail이 이미 API 호출과 detail 상태를 쥐고 있어서, 편집기가 따로 부르면
// 응답으로 온 detail을 부모에 되돌릴 길이 또 필요해진다.
export function ScriptEditor({
  initial,
  saving,
  error,
  onSave,
  onCancel,
}: {
  initial: ScriptOutput
  saving: boolean
  error: string | null
  onSave: (payload: ScriptEditPayload) => void
  onCancel: () => void
}) {
  // 로컬 draft다. SSE로 부모의 detail이 갱신돼도 작성 중인 내용이 덮이지 않는다.
  const [title, setTitle] = useState(initial.title)
  const [hook, setHook] = useState(initial.hook)
  const [scenes, setScenes] = useState<SceneDraft[]>(
    initial.scenes.map((s) => ({ narration: s.narration, on_screen: s.on_screen })),
  )

  const patchScene = (index: number, patch: Partial<SceneDraft>) =>
    setScenes((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)))

  const removeScene = (index: number) =>
    setScenes((prev) => prev.filter((_, i) => i !== index))

  const addScene = () =>
    setScenes((prev) => [...prev, { narration: '', on_screen: '' }])

  // 이웃과 자리를 맞바꾼다. 서버는 배열 순서를 그대로 낭독 순서로 쓴다.
  const moveScene = (index: number, delta: -1 | 1) =>
    setScenes((prev) => {
      const next = [...prev]
      const target = index + delta
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })

  // 서버가 최종 강제하지만 즉각적인 피드백을 위해 저장 버튼을 먼저 잠근다.
  const titleBlank = title.trim().length === 0
  const blankNarration = scenes.some((s) => s.narration.trim().length === 0)
  const canSave = !saving && !titleBlank && !blankNarration && scenes.length > 0

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({
      title: title.trim(),
      hook: hook.trim(),
      scenes: scenes.map((s) => ({
        narration: s.narration.trim(),
        on_screen: s.on_screen.trim(),
      })),
    })
  }

  return (
    <form onSubmit={submit} className="mt-4 space-y-4 rounded-md border border-line p-4">
      <TextField
        id="script-title"
        label="제목"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        error={titleBlank ? '제목을 입력해 주세요.' : undefined}
      />
      <TextField
        id="script-hook"
        label="훅"
        value={hook}
        onChange={(e) => setHook(e.target.value)}
      />

      <div className="space-y-3">
        {scenes.map((scene, i) => (
          <div key={i} className="rounded-md border border-line-subtle p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium text-fg">#{i + 1}</span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => moveScene(i, -1)}
                  disabled={i === 0}
                  aria-label="위로"
                  className="rounded px-2 py-0.5 text-xs text-fg-body hover:bg-surface-muted disabled:opacity-30"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => moveScene(i, 1)}
                  disabled={i === scenes.length - 1}
                  aria-label="아래로"
                  className="rounded px-2 py-0.5 text-xs text-fg-body hover:bg-surface-muted disabled:opacity-30"
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => removeScene(i)}
                  // 0개는 서버가 422로 막는다 — 화면에서 먼저 알려준다.
                  disabled={scenes.length === 1}
                  className="rounded px-2 py-0.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-30 dark:text-red-400 dark:hover:bg-red-500/10"
                >
                  삭제
                </button>
              </div>
            </div>

            <label htmlFor={`narration-${i}`} className="mb-1 block text-xs text-fg-muted">
              나레이션 (음성이 읽는 내용)
            </label>
            <textarea
              id={`narration-${i}`}
              rows={2}
              value={scene.narration}
              onChange={(e) => patchScene(i, { narration: e.target.value })}
              className={INPUT_CLASS}
            />
            {scene.narration.trim().length === 0 && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                나레이션을 입력해 주세요.
              </p>
            )}

            <label htmlFor={`on-screen-${i}`} className="mb-1 mt-2 block text-xs text-fg-muted">
              화면 자막 (영상 소재 검색에도 쓰입니다 · 비워도 됩니다)
            </label>
            <input
              id={`on-screen-${i}`}
              value={scene.on_screen}
              onChange={(e) => patchScene(i, { on_screen: e.target.value })}
              className={INPUT_CLASS}
            />
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={addScene}
        disabled={scenes.length >= MAX_SCENES}
        className="w-full rounded-md border border-dashed border-line-strong px-3 py-2 text-sm text-fg-body hover:bg-surface-muted disabled:opacity-40"
      >
        + 장면 추가
      </button>

      <p className="text-xs text-fg-faint">저장하면 예상 길이가 다시 계산됩니다.</p>

      {error && <FormError message={error} />}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
        >
          취소
        </button>
        <button
          type="submit"
          disabled={!canSave}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          {saving ? '저장 중…' : '저장'}
        </button>
      </div>
    </form>
  )
}
