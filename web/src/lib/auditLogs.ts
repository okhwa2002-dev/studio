import { api } from './api'

export type AuditLog = {
  id: number
  action: string
  actor_id: number | null
  actor_email: string | null
  actor_name: string | null
  actor_ip: string | null
  target_type: string | null
  target_id: number | null
  target_label: string | null
  http_method: string | null
  http_path: string | null
  success_yn: 'Y' | 'N'
  summary: string | null
  created_at: string
}

export type AuditLogPage = {
  items: AuditLog[]
  total: number
  page: number
  size: number
}

export type AuditLogQuery = {
  from?: string
  to?: string
  action?: string
  success?: 'Y' | 'N'
  q?: string
  page?: number
  size?: number
}

// 백엔드 AuditAction(app/constants.py)의 25종과 1:1이다. 행위를 추가하면 여기에도
// 라벨을 넣어야 필터 선택지에 나타난다 — 그래서 라벨 없는 코드값이 화면에 뜰 수 없다.
export const AUDIT_ACTION_LABEL: Record<string, string> = {
  REGISTER: '회원 가입',
  LOGIN_SUCCESS: '로그인',
  LOGIN_FAILURE: '로그인 실패',
  ACCOUNT_LOCKED: '계정 잠김',
  LOGOUT: '로그아웃',
  PASSWORD_CHANGE: '비밀번호 변경',
  TOKEN_REUSE_DETECTED: '토큰 재사용 감지',
  USER_APPROVE: '가입 승인',
  USER_REJECT: '가입 거절',
  USER_UNLOCK: '잠금 해제',
  USER_RESET_PASSWORD: '비밀번호 초기화',
  USER_RESET_FAILURES: '실패 횟수 초기화',
  NOTICE_CREATE: '공지 등록',
  NOTICE_UPDATE: '공지 수정',
  NOTICE_DELETE: '공지 삭제',
  FAQ_CREATE: 'FAQ 등록',
  FAQ_UPDATE: 'FAQ 수정',
  FAQ_DELETE: 'FAQ 삭제',
  SYSTEM_SETTINGS_UPDATE: '시스템 설정 변경',
  PROJECT_CREATE: '프로젝트 생성',
  PROJECT_DELETE: '프로젝트 삭제',
  SCRIPT_UPDATE: '대본 수정',
  STAGE_RUN: '단계 실행',
  STAGE_APPROVE: '단계 승인',
  STAGE_REGENERATE: '단계 재생성',
}

export const auditLogs = {
  list: (params: AuditLogQuery) => {
    const qs = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') qs.set(key, String(value))
    }
    return api.get<AuditLogPage>(`/admin/audit-logs?${qs.toString()}`)
  },
}
