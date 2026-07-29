import { api } from './api'

export type RuntimeSettings = {
  script_provider: string
  voice_provider: string
  captions_provider: string
  render_provider: string
  whisper_model: string
  render_bg_color: string
  render_font: string
  render_font_size: number
  stock_sources: string[]
  stock_max_bytes: number
  stock_timeout_sec: number
  failed_login_limit: number
  password_min_len: number
  signup_auto_approve: boolean
}

// 화면은 settings(현재 유효값)와 defaults(.env 기본값) 둘만 쓴다.
// 서버는 overridden(변경된 키 목록)도 함께 내려주지만 여기 타입에는 두지 않는다 —
// "변경됨" 배지는 저장 전 draft 기준이어야 하므로 화면이 draft vs defaults로 직접
// 계산한다. 서버가 준 목록은 마지막 저장 시점의 스냅샷이라 편집 중에는 맞지 않는다.
export type SettingsSnapshot = {
  settings: RuntimeSettings
  defaults: RuntimeSettings
}

export const systemSettings = {
  read: () => api.get<SettingsSnapshot>('/admin/system/settings'),
  save: (settings: RuntimeSettings) =>
    api.put<SettingsSnapshot>('/admin/system/settings', settings),
}
