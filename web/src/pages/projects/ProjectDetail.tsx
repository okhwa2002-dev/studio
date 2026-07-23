import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { ApiError } from '../../lib/api'
import { subscribeProject, type StageProgress } from '../../lib/events'
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
        {stage.output.duration_sec != null && ` · ${stage.output.duration_sec.toFixed(1)}초`}
      </div>
      {stage.output.sources && stage.output.sources.length > 0 && (
        <div className="space-y-1 border-t border-slate-100 pt-2">
          <div className="text-xs font-medium text-slate-500">소재 출처</div>
          <ul className="space-y-0.5">
            {stage.output.sources.map((source) => (
              <li key={source.scene} className="text-xs text-slate-400">
                #{source.scene}{' '}
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-slate-600"
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
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
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
      <div className="text-xs text-slate-500">
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
}: {
  projectId: number
  stage: Stage
  voiceAttempt: number | null
  progress: StageProgress | undefined
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
              {acting ? '요청 중…' : '실행'}
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

      {(stage.status === 'QUEUED' || stage.status === 'RUNNING') && (
        <ProgressBar progress={progress ?? { percent: null, message: '대기 중…' }} />
      )}

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
  const [progress, setProgress] = useState<Record<string, StageProgress>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)

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
            progress={progress[s.name]}
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
