import { api } from './api'

// 계정 자체를 다루는 호출 모음(세션 상태와 분리 — auth.tsx는 로그인 여부만 관리한다).
export const account = {
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<{ status: string }>('/auth/change-password', body),
}
