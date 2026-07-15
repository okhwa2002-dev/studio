import { api } from './api'

export type AdminUser = {
  id: number
  email: string
  role: 'MEMBER' | 'ADMIN'
  status: 'PENDING' | 'ACTIVE' | 'DISABLED' | 'REJECTED'
  created_at: string // 백엔드가 로컬 naive ISO 문자열로 준다
  approved_at: string | null
}

export const adminUsers = {
  list: (status: AdminUser['status']) => api.get<AdminUser[]>(`/admin/users?status=${status}`),
  approve: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/approve`),
  reject: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/reject`),
}
