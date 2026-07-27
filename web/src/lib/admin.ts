import { api } from './api'
import type { ProjectStatus } from './projects'

export type AdminUser = {
  id: number
  email: string
  name: string
  role: 'MEMBER' | 'ADMIN'
  status: 'PENDING' | 'ACTIVE' | 'DISABLED' | 'REJECTED'
  created_at: string // 백엔드가 로컬 naive ISO 문자열로 준다
  approved_at: string | null
  failed_login_count: number
  locked_at: string | null
  unlocked_at: string | null
}

export const adminUsers = {
  // status를 생략하면 상태 무관 전체 목록을 가져온다.
  list: (status?: AdminUser['status']) =>
    api.get<AdminUser[]>(status ? `/admin/users?status=${status}` : '/admin/users'),
  approve: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/approve`),
  reject: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/reject`),
  unlock: (id: number) => api.post<{ id: number; unlocked_at: string }>(`/admin/users/${id}/unlock`),
  resetFailures: (id: number) =>
    api.post<{ id: number; failed_login_count: number }>(`/admin/users/${id}/reset-failures`),
}

// 관리자 전체 프로젝트 목록의 한 행. 소유자 이름·이메일이 조인돼 함께 온다.
export type AdminProject = {
  id: number
  owner_id: number
  title: string
  topic: string
  status: ProjectStatus
  current_stage: string
  created_at: string
  owner_name: string
  owner_email: string
}

export const adminProjects = {
  list: () => api.get<AdminProject[]>('/admin/projects'),
}
