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

// 화면이 "변경됨" 배지와 [기본값으로] 링크를 그리려면 셋 다 필요하다.
export type SettingsSnapshot = {
  settings: RuntimeSettings
  defaults: RuntimeSettings
  overridden: string[]
}

export const systemSettings = {
  read: () => api.get<SettingsSnapshot>('/admin/system/settings'),
  save: (settings: RuntimeSettings) =>
    api.put<SettingsSnapshot>('/admin/system/settings', settings),
}
