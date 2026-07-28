import { api } from './api'
import type { Yn } from './notices'
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

// 관리자 공지 목록의 한 행. 작성자 이름이 조인돼 함께 온다(작성자 계정이
// 지워졌거나 created_by가 비면 null).
export type AdminNotice = {
  id: number
  title: string
  body: string
  status: 'DRAFT' | 'PUBLISHED'
  pinned_yn: Yn
  popup_yn: Yn
  starts_at: string | null
  ends_at: string | null
  created_at: string
  created_by_name: string | null
}

// 생성·수정이 같은 본문을 쓴다 — 관리자 모달이 항상 편집 가능한 전체를 보낸다.
export type NoticePayload = {
  title: string
  body: string
  status: AdminNotice['status']
  pinned_yn: Yn
  popup_yn: Yn
  starts_at: string | null
  ends_at: string | null
}

export const adminNotices = {
  list: () => api.get<AdminNotice[]>('/admin/notices'),
  create: (payload: NoticePayload) => api.post<{ id: number }>('/admin/notices', payload),
  update: (id: number, payload: NoticePayload) =>
    api.patch<{ id: number }>(`/admin/notices/${id}`, payload),
  remove: (id: number) => api.del<{ id: number; deleted_at: string }>(`/admin/notices/${id}`),
}

export type NoticePhase = 'DRAFT' | 'SCHEDULED' | 'ACTIVE' | 'ENDED'

// 백엔드가 주는 로컬 naive ISO 문자열과 같은 모양의 "지금"을 만든다.
// Date로 파싱해 비교하면 타임존 보정이 끼어들므로, 같은 형식끼리 문자열로 비교한다
// (0으로 채워진 고정 폭 형식이라 사전순 비교가 곧 시간순 비교다).
export function localNowIso(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  )
}

// 표시 상태는 저장하지 않고 status와 기간에서 파생한다.
// (브라우저 시간대가 서버의 Asia/Seoul과 다르면 경계에서 어긋날 수 있으나,
//  사용자에게 실제로 보이는 목록은 서버가 걸러주므로 관리자 화면 표시에만 영향이 있다.)
export function noticePhase(notice: AdminNotice, now: string): NoticePhase {
  if (notice.status === 'DRAFT' || notice.starts_at === null) return 'DRAFT'
  if (notice.starts_at > now) return 'SCHEDULED'
  if (notice.ends_at !== null && notice.ends_at <= now) return 'ENDED'
  return 'ACTIVE'
}
