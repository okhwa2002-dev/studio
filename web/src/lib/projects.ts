import { api } from './api'

export type ScriptScene = { index: number; narration: string; on_screen: string }
export type ScriptOutput = {
  title: string
  hook: string
  scenes: ScriptScene[]
  estimated_duration_sec: number
}
export type VoiceOutput = { voice: string; size_bytes: number; chars: number }
export type CaptionWord = { w: string; s: number; e: number }
export type CaptionsOutput = {
  language: string
  duration_sec: number
  word_count: number
  words: CaptionWord[]
}
export type RenderSource = {
  scene: number
  source: string
  kind: string
  query: string
  url: string
  author: string
}
export type RenderOutput = {
  provider: string
  width: number
  height: number
  duration_sec: number | null
  size_bytes: number
  sources?: RenderSource[]
}
// 대본 수정 요청. 사용자가 실제로 통제하는 필드만 담는다 —
// scene의 index와 estimated_duration_sec는 서버가 배열 순서·글자수에서 유도한다.
export type ScriptEditPayload = {
  title: string
  hook: string
  scenes: { narration: string; on_screen: string }[]
}

export type StageStatus = 'PENDING' | 'QUEUED' | 'RUNNING' | 'NEEDS_REVIEW' | 'APPROVED' | 'FAILED'
export type ProjectStatus = 'DRAFT' | 'REVIEW' | 'DONE'

export type Stage = {
  id: number
  name: string
  provider: string
  status: StageStatus
  output: ScriptOutput | VoiceOutput | CaptionsOutput | RenderOutput | Record<string, never>
  error: string | null
  attempt: number
}

export type ProjectSummary = {
  id: number
  title: string
  topic: string
  status: ProjectStatus
  current_stage: string
  created_at: string
}

export type ProjectDetail = { project: ProjectSummary; stages: Stage[] }

export const projects = {
  list: () => api.get<ProjectSummary[]>('/projects'),
  create: (body: { title: string; topic: string; auto_run: boolean }) =>
    api.post<ProjectDetail>('/projects', body),
  detail: (id: number) => api.get<ProjectDetail>(`/projects/${id}`),
  run: (id: number, name: string) => api.post<ProjectDetail>(`/projects/${id}/stages/${name}/run`),
  approve: (id: number, name: string) =>
    api.post<ProjectDetail>(`/projects/${id}/stages/${name}/approve`),
  regenerate: (id: number, name: string) =>
    api.post<ProjectDetail>(`/projects/${id}/stages/${name}/regenerate`),
  // 편집 가능한 대본 전체를 보낸다(장면 삭제·순서 변경은 부분 갱신으로 표현할 수 없다).
  // index와 예상 길이는 서버가 정하므로 보내지 않는다.
  saveScript: (id: number, payload: ScriptEditPayload) =>
    api.put<ProjectDetail>(`/projects/${id}/stages/script`, payload),
  // 이름이 remove인 것은 adminNotices·adminFaqs와 같은 이유다(delete는 JS 연산자와 겹친다).
  remove: (id: number) => api.del<{ id: number; deleted_at: string }>(`/projects/${id}`),
  // 재생성 후 브라우저가 옛 음성을 캐시하지 않도록 attempt를 붙인다.
  assetUrl: (id: number, name: string, attempt: number) =>
    `/api/projects/${id}/stages/${name}/asset?v=${attempt}`,
}

// 단계 이름 → 한국어 라벨. 목록(현재 단계 컬럼)과 상세(단계 카드 제목)가 함께 쓴다.
export const STAGE_LABEL: Record<string, string> = {
  script: '대본',
  voice: '음성',
  captions: '자막',
  render: '영상',
}

export const STAGE_BADGE: Record<StageStatus, { label: string; className: string }> = {
  PENDING: { label: '대기', className: 'bg-slate-100 text-slate-600' },
  QUEUED: { label: '대기열', className: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300' },
  RUNNING: { label: '실행 중', className: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300' },
  NEEDS_REVIEW: { label: '검토 필요', className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300' },
  APPROVED: { label: '승인됨', className: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300' },
  FAILED: { label: '실패', className: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300' },
}

export function hasScript(output: Stage['output']): output is ScriptOutput {
  return 'title' in output
}

export function hasVoice(output: Stage['output']): output is VoiceOutput {
  return 'voice' in output
}

export function hasCaptions(output: Stage['output']): output is CaptionsOutput {
  return 'words' in output
}

export function hasRender(output: Stage['output']): output is RenderOutput {
  return 'width' in output
}
