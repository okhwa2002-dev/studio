import { api } from './api'

// DB·API·프론트가 모두 'Y'/'N' 같은 표기를 쓴다. 불리언 변환은 isY/toYn에서만
// 정의되므로(호출하는 곳은 여럿이어도), 값이 뒤집혔을 때 볼 곳이 한 군데뿐이다.
export type Yn = 'Y' | 'N'

export function isY(value: Yn): boolean {
  return value === 'Y'
}

export function toYn(checked: boolean): Yn {
  return checked ? 'Y' : 'N'
}

export type Notice = {
  id: number
  title: string
  body: string
  pinned_yn: Yn
  starts_at: string // 백엔드가 로컬 naive ISO 문자열로 준다 (예: 2026-07-28T09:00:00)
  is_read: boolean
}

export type PopupNotice = {
  id: number
  title: string
  body: string
  starts_at: string
}

export const notices = {
  list: () => api.get<Notice[]>('/notices'),
  // 상세 화면 전용. 목록에서 찾아 쓰지 않는 이유는 새로고침·링크 공유로 상세에
  // 바로 들어올 수 있어야 하기 때문이다. 노출 조건을 벗어나면 404가 온다.
  detail: (id: number) => api.get<Notice>(`/notices/${id}`),
  popups: () => api.get<PopupNotice[]>('/notices/popups'),
  unreadCount: () => api.get<{ count: number }>('/notices/unread/count'),
  markRead: (id: number) => api.post<{ id: number }>(`/notices/${id}/read`),
}
