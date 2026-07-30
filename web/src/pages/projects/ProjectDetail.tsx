import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { FormError } from '../../components/FormError'
import { ApiError } from '../../lib/api'
import { useToast } from '../../lib/toast'
import { subscribeProject, type StageProgress } from '../../lib/events'
import { hasCaptions, hasRender, hasScript, hasVoice, projects, STAGE_BADGE, STAGE_LABEL, type ProjectDetail as Detail, type ScriptEditPayload, type Stage } from '../../lib/projects'
import { ScriptEditor } from './ScriptEditor'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

function StageBadge({ status }: { status: Stage['status'] }) {
  const badge = STAGE_BADGE[status]
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
      {badge.label}
    </span>
  )
}

function ScriptView({ stage }: { stage: Stage }) {
  if (!hasScript(stage.output)) return null
  const s = stage.output
  return (
    <div className="mt-4 space-y-3 rounded-md border border-line p-4">
      <div className="text-base font-semibold text-fg">{s.title}</div>
      <div className="text-sm text-fg-muted">🎣 {s.hook}</div>
      <ol className="space-y-2">
        {s.scenes.map((scene) => (
          <li key={scene.index} className="text-sm">
            <span className="font-medium text-fg">#{scene.index}</span>{' '}
            <span className="text-fg-body">{scene.narration}</span>
            <div className="text-xs text-fg-faint">화면: {scene.on_screen}</div>
          </li>
        ))}
      </ol>
      <div className="text-xs text-fg-faint">예상 길이 {s.estimated_duration_sec}초</div>
    </div>
  )
}

// 라벨은 lib/projects의 STAGE_LABEL 하나로 관리하고, 상세에서만 원본 단계명을 괄호로 덧붙인다.
function stageTitle(name: string) {
  const label = STAGE_LABEL[name]
  return label ? `${label} (${name})` : name
}

function VoiceView({ projectId, stage }: { projectId: number; stage: Stage }) {
  if (!hasVoice(stage.output)) return null
  return (
    <div className="mt-4 space-y-2 rounded-md border border-line p-4">
      <audio
        controls
        className="w-full"
        src={projects.assetUrl(projectId, stage.name, stage.attempt)}
      />
      <div className="text-xs text-fg-faint">
        목소리 {stage.output.voice} · {stage.output.chars}자
      </div>
    </div>
  )
}

function CaptionsView({
  projectId,
  stage,
  voiceAttempt,
}: {
  projectId: number
  stage: Stage
  voiceAttempt: number | null
}) {
  // 훅은 조건부 반환보다 먼저 호출해야 한다.
  const cursor = useRef(0)
  const [active, setActive] = useState(-1)

  if (!hasCaptions(stage.output)) return null
  const { words, word_count, duration_sec } = stage.output

  // 단어가 수백 개라 매 틱 전체를 훑지 않고 현재 위치에서 전진한다.
  const onTimeUpdate = (e: React.SyntheticEvent<HTMLAudioElement>) => {
    if (words.length === 0) return // 단어가 하나도 없는 자막도 카드가 렌더되므로 방어
    const t = e.currentTarget.currentTime
    let i = cursor.current
    if (i >= words.length || t < words[i].s) i = 0 // 뒤로 감았다 → 처음부터 다시 전진
    while (i < words.length - 1 && t >= words[i + 1].s) i += 1
    cursor.current = i
    setActive(t >= words[i].s && t < words[i].e ? i : -1)
  }

  return (
    <div className="mt-4 space-y-3 rounded-md border border-line p-4">
      {voiceAttempt !== null && (
        <audio
          controls
          className="w-full"
          src={projects.assetUrl(projectId, 'voice', voiceAttempt)}
          onTimeUpdate={onTimeUpdate}
        />
      )}
      <div className="flex flex-wrap gap-1 text-sm leading-7">
        {words.map((word, i) => (
          <span
            key={i}
            className={`rounded px-1 ${
              i === active
                ? 'bg-yellow-200 text-slate-900 dark:bg-yellow-500/30 dark:text-yellow-50'
                : 'text-fg-body'
            }`}
          >
            {word.w}
          </span>
        ))}
      </div>
      <div className="text-xs text-fg-faint">
        {word_count}단어 · {duration_sec.toFixed(1)}초
      </div>
    </div>
  )
}

function RenderView({ projectId, stage }: { projectId: number; stage: Stage }) {
  if (!hasRender(stage.output)) return null
  const url = projects.assetUrl(projectId, stage.name, stage.attempt)
  return (
    <div className="mt-4 space-y-2 rounded-md border border-line p-4">
      <video controls className="w-full rounded-md bg-black" src={url} />
      <a
        href={url}
        download="render.mp4"
        className="inline-block rounded-md border border-line-strong px-3 py-1 text-xs font-medium text-fg-body hover:bg-surface-muted"
      >
        mp4 다운로드
      </a>
      <div className="text-xs text-fg-faint">
        {stage.output.width}×{stage.output.height}
        {stage.output.duration_sec != null && ` · ${stage.output.duration_sec.toFixed(1)}초`}
      </div>
      {stage.output.sources && stage.output.sources.length > 0 && (
        <div className="space-y-1 border-t border-line-subtle pt-2">
          <div className="text-xs font-medium text-fg-muted">소재 출처</div>
          <ul className="space-y-0.5">
            {stage.output.sources.map((source) => (
              <li key={source.scene} className="text-xs text-fg-faint">
                #{source.scene}{' '}
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-fg-muted"
                >
                  {source.source === 'pexels' ? 'Pexels' : 'Pixabay'}
                </a>
                {source.author && ` · ${source.author}`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// 백엔드 계산값이 튀거나(105%) 음수로 잠깐 흔들려도 바가 넘치거나 뒤집히지 않게 막는다.
function clamp(n: number, min: number, max: number): number {
  return Math.min(Math.max(n, min), max)
}

function ProgressBar({ progress }: { progress: StageProgress }) {
  const { percent, message } = progress
  return (
    <div className="mt-3 space-y-1">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
        {percent === null ? (
          // 진짜 진행률이 없는 단계(대본·음성) — 가짜 숫자 대신 움직이는 띠를 보여준다.
          <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-400" />
        ) : (
          <div
            className="h-full rounded-full bg-blue-500 transition-[width] duration-300"
            style={{ width: `${clamp(percent, 0, 100)}%` }}
          />
        )}
      </div>
      <div className="text-xs text-fg-muted">
        {message}
        {percent !== null && ` ${Math.round(clamp(percent, 0, 100))}%`}
      </div>
    </div>
  )
}

function StageCard({
  projectId,
  stage,
  voiceAttempt,
  progress,
  acting,
  act,
  readOnly,
  onDetail,
}: {
  projectId: number
  stage: Stage
  voiceAttempt: number | null
  progress: StageProgress | undefined
  acting: boolean
  act: (fn: () => Promise<Detail>) => Promise<void>
  readOnly: boolean
  onDetail: (detail: Detail) => void
}) {
  // 대본 편집 상태는 이 카드가 들고 있다. act()를 쓰지 않는 이유: act는 실패를 페이지
  // 상단의 error로 올리는데, 저장 실패 시에는 편집기를 닫지 않고 그 안에 보여줘야 한다
  // (작성 중인 내용을 날리면 안 된다).
  const [editing, setEditing] = useState(false)
  const [savingScript, setSavingScript] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const saveScript = async (payload: ScriptEditPayload) => {
    setSavingScript(true)
    setSaveError(null)
    try {
      onDetail(await projects.saveScript(projectId, payload))
      setEditing(false)
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setSavingScript(false)
    }
  }

  const editable = !readOnly && stage.name === 'script' && stage.status === 'NEEDS_REVIEW'

  return (
    <div className="mt-4 rounded-lg border border-line p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium text-fg">{stageTitle(stage.name)}</span>
          <StageBadge status={stage.status} />
        </div>
        {/* 읽기 전용(관리자 열람)에서는 실행·승인·재생성 버튼을 아예 그리지 않는다.
            편집 중에도 숨긴다 — 그대로 두면 [승인]이 수정 전 대본을 승인해 작성 중인
            내용을 조용히 버린다. */}
        <div className="flex gap-2">
          {editable && !editing && (
            <button
              onClick={() => {
                setSaveError(null)
                setEditing(true)
              }}
              disabled={acting}
              className="rounded-md border border-line-strong px-3 py-1 text-xs font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
            >
              수정
            </button>
          )}
          {!editing && !readOnly && (stage.status === 'PENDING' || stage.status === 'FAILED') && (
            <button
              onClick={() => act(() => projects.run(projectId, stage.name))}
              disabled={acting}
              className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-on-primary disabled:opacity-50"
            >
              {acting ? '요청 중…' : '실행'}
            </button>
          )}
          {!editing && !readOnly && stage.status === 'NEEDS_REVIEW' && (
            <>
              <button
                onClick={() => act(() => projects.approve(projectId, stage.name))}
                disabled={acting}
                className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-on-primary disabled:opacity-50"
              >
                승인
              </button>
              <button
                onClick={() => act(() => projects.regenerate(projectId, stage.name))}
                disabled={acting}
                className="rounded-md border border-line-strong px-3 py-1 text-xs font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
              >
                재생성
              </button>
            </>
          )}
        </div>
      </div>

      {(stage.status === 'QUEUED' || stage.status === 'RUNNING') && (
        <ProgressBar progress={progress ?? { percent: null, message: '대기 중…' }} />
      )}

      {stage.status === 'FAILED' && stage.error && (
        <div className="mt-3 text-sm text-red-700 dark:text-red-400">오류: {stage.error}</div>
      )}
      {editing && hasScript(stage.output) ? (
        <ScriptEditor
          initial={stage.output}
          saving={savingScript}
          error={saveError}
          onSave={saveScript}
          onCancel={() => setEditing(false)}
        />
      ) : (
        (stage.status === 'NEEDS_REVIEW' || stage.status === 'APPROVED') && (
          <>
            <ScriptView stage={stage} />
            <VoiceView projectId={projectId} stage={stage} />
            <CaptionsView projectId={projectId} stage={stage} voiceAttempt={voiceAttempt} />
            <RenderView projectId={projectId} stage={stage} />
          </>
        )
      )}
    </div>
  )
}

// readOnly는 관리자 열람(/admin/projects/:id)에서 켠다 — 액션 버튼을 숨기고 목록 링크를 관리자 쪽으로 돌린다.
// 서버도 쓰기(실행·승인·재생성)를 소유자로 제한하므로, 버튼을 숨기는 건 UX일 뿐 보안 경계는 백엔드가 강제한다.
export function ProjectDetail({ readOnly = false }: { readOnly?: boolean }) {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [progress, setProgress] = useState<Record<string, StageProgress>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const navigate = useNavigate()
  const toast = useToast()

  useEffect(() => {
    setLoading(true)
    setError(null)
    // 첫 화면은 SSE의 snapshot이 채운다. 실패는 구독 래퍼가 재시도로 흡수한다.
    const unsubscribe = subscribeProject(projectId, (event) => {
      setLoading(false)
      if (event.type === 'fatal') {
        // 삭제됐거나 남의 프로젝트(404), 갱신 후에도 만료된 인증(401) — 재시도해도
        // 절대 낫지 않으므로 구독은 이미 스스로 멈췄다. 여기서는 화면에만 반영한다.
        setDetail(null)
        setError(event.message)
        return
      }
      if (event.type === 'snapshot') {
        setDetail({ project: event.project, stages: event.stages })
        setProgress(event.progress)
        return
      }
      if (event.type === 'stage') {
        setDetail((prev) =>
          prev === null
            ? prev
            : {
                project: event.project,
                stages: prev.stages.some((s) => s.id === event.stage.id)
                  ? prev.stages.map((s) => (s.id === event.stage.id ? event.stage : s))
                  : [...prev.stages, event.stage],
              },
        )
        // 단계가 끝났으면 진행률을 지운다 — 다음 실행의 잔상이 남지 않게.
        if (event.stage.status !== 'QUEUED' && event.stage.status !== 'RUNNING') {
          setProgress((prev) => {
            const { [event.stage.name]: _done, ...rest } = prev
            return rest
          })
        }
        return
      }
      setProgress((prev) => ({
        ...prev,
        [event.stage]: { percent: event.percent, message: event.message },
      }))
    })
    return unsubscribe
  }, [projectId])

  // 요청을 보내는 동안만 잠근다. 실행 완료를 기다리지 않는다 — 결과는 SSE로 온다.
  const act = async (fn: () => Promise<Detail>) => {
    setActing(true)
    setError(null)
    try {
      setDetail(await fn())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setActing(false)
    }
  }

  const remove = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await projects.remove(projectId)
      toast.success('프로젝트를 삭제했습니다.')
      // replace인 이유: 뒤로 가기로 방금 지운 상세에 돌아가면 404 화면이 뜬다.
      navigate('/projects', { replace: true })
    } catch (e) {
      // 대화상자를 닫지 않는다 — 실행 중이라 거절된 경우(409) 사용자가 읽고 취소해야 한다.
      setDeleteError(e instanceof ApiError ? e.message : UNKNOWN)
      setDeleting(false)
    }
  }

  if (loading) return <div className="p-10 text-center text-sm text-fg-muted">불러오는 중…</div>
  if (!detail) return <FormError message={error ?? UNKNOWN} />

  const voiceAttempt = detail.stages.find((s) => s.name === 'voice')?.attempt ?? null

  return (
    <div className="max-w-2xl">
      <h1 className="text-lg font-semibold text-fg">{detail.project.title}</h1>
      <p className="mt-1 text-sm text-fg-muted">주제: {detail.project.topic}</p>

      {error && <div className="mt-4"><FormError message={error} /></div>}

      <div className="mt-6">
        {detail.stages.map((s) => (
          <StageCard
            key={s.id}
            projectId={projectId}
            stage={s}
            voiceAttempt={voiceAttempt}
            progress={progress[s.name]}
            acting={acting}
            act={act}
            readOnly={readOnly}
            onDetail={setDetail}
          />
        ))}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <Link
          to={readOnly ? '/admin/projects' : '/projects'}
          className="inline-block rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-fg-body hover:bg-surface-muted"
        >
          ← 목록으로
        </Link>
        {/* 관리자 열람에서는 숨긴다 — 다른 액션 버튼과 같은 규칙이고, 서버도 삭제를
            소유자로 제한하므로 관리자에게는 항상 실패할 버튼이 된다. */}
        {!readOnly && (
          <button
            onClick={() => {
              setDeleteError(null)
              setConfirmingDelete(true)
            }}
            className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 dark:border-red-500/40 dark:text-red-300 dark:hover:bg-red-500/10"
          >
            삭제
          </button>
        )}
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title="프로젝트 삭제"
          message={`「${detail.project.title}」을 삭제합니다. 대본·음성·자막·영상이 함께 사라지며 되돌릴 수 없습니다.`}
          confirmLabel="삭제"
          tone="danger"
          busy={deleting}
          error={deleteError}
          onConfirm={remove}
          onClose={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  )
}
