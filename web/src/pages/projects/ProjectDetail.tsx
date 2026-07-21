import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { ApiError } from '../../lib/api'
import { hasCaptions, hasRender, hasScript, hasVoice, projects, STAGE_BADGE, type ProjectDetail as Detail, type Stage } from '../../lib/projects'

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
    <div className="mt-4 space-y-3 rounded-md border border-slate-200 p-4">
      <div className="text-base font-semibold text-slate-900">{s.title}</div>
      <div className="text-sm text-slate-600">🎣 {s.hook}</div>
      <ol className="space-y-2">
        {s.scenes.map((scene) => (
          <li key={scene.index} className="text-sm">
            <span className="font-medium text-slate-800">#{scene.index}</span>{' '}
            <span className="text-slate-700">{scene.narration}</span>
            <div className="text-xs text-slate-400">화면: {scene.on_screen}</div>
          </li>
        ))}
      </ol>
      <div className="text-xs text-slate-400">예상 길이 {s.estimated_duration_sec}초</div>
    </div>
  )
}

const STAGE_LABEL: Record<string, string> = {
  script: '대본 (script)',
  voice: '음성 (voice)',
  captions: '자막 (captions)',
  render: '영상 (render)',
}

function VoiceView({ projectId, stage }: { projectId: number; stage: Stage }) {
  if (!hasVoice(stage.output)) return null
  return (
    <div className="mt-4 space-y-2 rounded-md border border-slate-200 p-4">
      <audio
        controls
        className="w-full"
        src={projects.assetUrl(projectId, stage.name, stage.attempt)}
      />
      <div className="text-xs text-slate-400">
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
    <div className="mt-4 space-y-3 rounded-md border border-slate-200 p-4">
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
              i === active ? 'bg-yellow-200 text-slate-900' : 'text-slate-700'
            }`}
          >
            {word.w}
          </span>
        ))}
      </div>
      <div className="text-xs text-slate-400">
        {word_count}단어 · {duration_sec.toFixed(1)}초
      </div>
    </div>
  )
}

function RenderView({ projectId, stage }: { projectId: number; stage: Stage }) {
  if (!hasRender(stage.output)) return null
  const url = projects.assetUrl(projectId, stage.name, stage.attempt)
  return (
    <div className="mt-4 space-y-2 rounded-md border border-slate-200 p-4">
      <video controls className="w-full rounded-md bg-black" src={url} />
      <a
        href={url}
        download="render.mp4"
        className="inline-block rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
      >
        mp4 다운로드
      </a>
      <div className="text-xs text-slate-400">
        {stage.output.width}×{stage.output.height}
        {stage.output.duration_sec !== null && ` · ${stage.output.duration_sec.toFixed(1)}초`}
      </div>
    </div>
  )
}

function StageCard({
  projectId,
  stage,
  voiceAttempt,
  acting,
  act,
}: {
  projectId: number
  stage: Stage
  voiceAttempt: number | null
  acting: boolean
  act: (fn: () => Promise<Detail>) => Promise<void>
}) {
  return (
    <div className="mt-4 rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium text-slate-800">{STAGE_LABEL[stage.name] ?? stage.name}</span>
          <StageBadge status={stage.status} />
        </div>
        <div className="flex gap-2">
          {(stage.status === 'PENDING' || stage.status === 'FAILED') && (
            <button
              onClick={() => act(() => projects.run(projectId, stage.name))}
              disabled={acting}
              className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {acting ? '생성 중… (최대 1분)' : '실행'}
            </button>
          )}
          {stage.status === 'NEEDS_REVIEW' && (
            <>
              <button
                onClick={() => act(() => projects.approve(projectId, stage.name))}
                disabled={acting}
                className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                승인
              </button>
              <button
                onClick={() => act(() => projects.regenerate(projectId, stage.name))}
                disabled={acting}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                재생성
              </button>
            </>
          )}
        </div>
      </div>

      {stage.status === 'FAILED' && stage.error && (
        <div className="mt-3 text-sm text-red-700">오류: {stage.error}</div>
      )}
      {(stage.status === 'NEEDS_REVIEW' || stage.status === 'APPROVED') && (
        <>
          <ScriptView stage={stage} />
          <VoiceView projectId={projectId} stage={stage} />
          <CaptionsView projectId={projectId} stage={stage} voiceAttempt={voiceAttempt} />
          <RenderView projectId={projectId} stage={stage} />
        </>
      )}
    </div>
  )
}

export function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    projects
      .detail(projectId)
      .then(setDetail)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

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

  if (loading) return <div className="p-10 text-center text-sm text-slate-500">불러오는 중…</div>
  if (!detail) return <FormError message={error ?? UNKNOWN} />

  const voiceAttempt = detail.stages.find((s) => s.name === 'voice')?.attempt ?? null

  return (
    <div className="max-w-2xl">
      <h1 className="text-lg font-semibold text-slate-900">{detail.project.title}</h1>
      <p className="mt-1 text-sm text-slate-500">주제: {detail.project.topic}</p>

      {error && <div className="mt-4"><FormError message={error} /></div>}

      <div className="mt-6">
        {detail.stages.map((s) => (
          <StageCard
            key={s.id}
            projectId={projectId}
            stage={s}
            voiceAttempt={voiceAttempt}
            acting={acting}
            act={act}
          />
        ))}
      </div>

      <div className="mt-6">
        <Link
          to="/projects"
          className="inline-block rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          ← 목록으로
        </Link>
      </div>
    </div>
  )
}
