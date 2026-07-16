import { api } from './api'

export type ScriptScene = { index: number; narration: string; on_screen: string }
export type ScriptOutput = {
  title: string
  hook: string
  scenes: ScriptScene[]
  estimated_duration_sec: number
}
export type StageStatus = 'PENDING' | 'RUNNING' | 'NEEDS_REVIEW' | 'APPROVED' | 'FAILED'
export type ProjectStatus = 'DRAFT' | 'REVIEW' | 'DONE'

export type Stage = {
  id: number
  name: string
  provider: string
  status: StageStatus
  output: ScriptOutput | Record<string, never>
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
  create: (body: { title: string; topic: string }) => api.post<ProjectDetail>('/projects', body),
  detail: (id: number) => api.get<ProjectDetail>(`/projects/${id}`),
  run: (id: number, name: string) => api.post<ProjectDetail>(`/projects/${id}/stages/${name}/run`),
  approve: (id: number, name: string) =>
    api.post<ProjectDetail>(`/projects/${id}/stages/${name}/approve`),
  regenerate: (id: number, name: string) =>
    api.post<ProjectDetail>(`/projects/${id}/stages/${name}/regenerate`),
}

export const STAGE_BADGE: Record<StageStatus, { label: string; className: string }> = {
  PENDING: { label: '대기', className: 'bg-slate-100 text-slate-600' },
  RUNNING: { label: '실행 중', className: 'bg-blue-100 text-blue-800' },
  NEEDS_REVIEW: { label: '검토 필요', className: 'bg-yellow-100 text-yellow-800' },
  APPROVED: { label: '승인됨', className: 'bg-green-100 text-green-800' },
  FAILED: { label: '실패', className: 'bg-red-100 text-red-800' },
}

export function hasScript(output: Stage['output']): output is ScriptOutput {
  return 'title' in output
}
