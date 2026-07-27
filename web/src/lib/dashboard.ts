import { api } from './api'

export type ProjectCounts = { total: number; draft: number; review: number; done: number }

export type AttentionProject = {
  id: number
  title: string
  current_stage: string
  needs_review: boolean
  failed: boolean
}

export type AdminSummary = {
  users: { active: number; pending: number; locked: number }
  projects: ProjectCounts
  stages: { running: number; failed: number; needs_review: number }
}

export type DashboardSummary = {
  projects: ProjectCounts
  attention: AttentionProject[]
  admin: AdminSummary | null // 멤버면 null, 관리자면 운영 지표
}

export const dashboard = {
  summary: () => api.get<DashboardSummary>('/dashboard/summary'),
}
