import { useEffect, useState } from 'react'
import { FormError } from '../../components/FormError'
import { SettingRow } from '../../components/SettingRow'
import { ApiError } from '../../lib/api'
import {
  systemSettings,
  type RuntimeSettings,
  type SettingsSnapshot,
} from '../../lib/systemSettings'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'
const MB = 1024 * 1024

const SCRIPT_PROVIDERS = ['fake', 'openai', 'claude']
const VOICE_PROVIDERS = ['fake', 'edge_tts']
const CAPTIONS_PROVIDERS = ['fake', 'whisper']
const RENDER_PROVIDERS = ['fake', 'slideshow', 'stock']
const WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v3']
const STOCK_ORDERS: { value: string[]; label: string }[] = [
  { value: ['pexels', 'pixabay'], label: 'Pexels 먼저' },
  { value: ['pixabay', 'pexels'], label: 'Pixabay 먼저' },
  { value: ['pexels'], label: 'Pexels만' },
  { value: ['pixabay'], label: 'Pixabay만' },
]

const selectClass =
  'shrink-0 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm text-fg'
const inputClass =
  'w-32 shrink-0 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm text-fg'

function Select({
  value,
  options,
  onChange,
}: {
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <select className={selectClass} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  )
}

function NumberInput({
  value,
  onChange,
}: {
  value: number
  onChange: (v: number) => void
}) {
  // 지우고 다시 타이핑하는 중간에는 빈 문자열이 되는데, 그 상태를 곧바로 0으로 스냅해
  // draft에 반영하면 사용자가 지운 걸 알아채지 못한 채 0이 저장될 수 있다. 그래서
  // 표시 문자열은 컴포넌트가 따로 들고 있고, 유효한 숫자일 때만 상위 draft로 올린다.
  const [text, setText] = useState(String(value))

  // 바깥 값이 바뀌면(되돌리기·기본값으로·저장 응답 반영 등) 표시도 맞춘다.
  useEffect(() => {
    setText(String(value))
  }, [value])

  return (
    <input
      type="number"
      className={inputClass}
      value={text}
      onChange={(e) => {
        const raw = e.target.value
        setText(raw)
        if (raw.trim() === '') return // 빈 상태를 그대로 유지하고 draft는 건드리지 않는다.
        const n = Number(raw)
        if (!Number.isNaN(n)) onChange(n)
      }}
    />
  )
}

// 기본값과 다른 항목에만 붙는다. 눌러서 곧바로 되돌릴 수 있다.
function Overridden({ onReset }: { onReset: () => void }) {
  return (
    <span className="ml-2 inline-flex items-center gap-1 align-middle">
      <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
        변경됨
      </span>
      <button
        type="button"
        onClick={onReset}
        className="text-[11px] text-fg-muted underline hover:text-fg"
      >
        기본값으로
      </button>
    </span>
  )
}

export function AdminSystem() {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null)
  const [draft, setDraft] = useState<RuntimeSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    systemSettings
      .read()
      .then((s) => {
        if (!alive) return
        setSnapshot(s)
        setDraft(s.settings)
      })
      .catch((e) => {
        if (!alive) return
        setError(e instanceof ApiError ? e.message : UNKNOWN)
      })
    return () => {
      alive = false
    }
  }, [])

  if (error && !draft) return <FormError message={error} />
  if (!snapshot || !draft) return <p className="text-sm text-fg-muted">불러오는 중…</p>

  const set = <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => {
    setSaved(false)
    setDraft({ ...draft, [key]: value })
  }
  const reset = (key: keyof RuntimeSettings) => set(key, snapshot.defaults[key])
  const changed = (key: keyof RuntimeSettings) =>
    JSON.stringify(draft[key]) !== JSON.stringify(snapshot.defaults[key])
  const dirty = JSON.stringify(draft) !== JSON.stringify(snapshot.settings)

  const badge = (key: keyof RuntimeSettings) =>
    changed(key) ? <Overridden onReset={() => reset(key)} /> : null

  const save = async () => {
    setError(null)
    setSaving(true)
    try {
      const next = await systemSettings.save(draft)
      setSnapshot(next)
      setDraft(next.settings)
      setSaved(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-4 pb-20">
      {saved && (
        <p className="rounded-md bg-green-50 px-4 py-2 text-sm text-green-700 dark:bg-green-500/10 dark:text-green-300">
          시스템 설정을 저장했습니다.
        </p>
      )}
      {error && <FormError message={error} />}

      <section className="divide-y divide-line-subtle rounded-lg border border-line bg-surface px-6">
        <h2 className="pt-5 pb-1 text-sm font-semibold text-fg">파이프라인 기본값</h2>

        <SettingRow
          label={<>스크립트 provider{badge('script_provider')}</>}
          description="대본 생성 도구입니다. 새로 만드는 프로젝트부터 적용됩니다."
        >
          <Select
            value={draft.script_provider}
            options={SCRIPT_PROVIDERS}
            onChange={(v) => set('script_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>음성 provider{badge('voice_provider')}</>}
          description="음성 합성 도구입니다. 새로 만들어지는 단계부터 적용됩니다."
        >
          <Select
            value={draft.voice_provider}
            options={VOICE_PROVIDERS}
            onChange={(v) => set('voice_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>자막 provider{badge('captions_provider')}</>}
          description="자막 생성 도구입니다. 새로 만들어지는 단계부터 적용됩니다."
        >
          <Select
            value={draft.captions_provider}
            options={CAPTIONS_PROVIDERS}
            onChange={(v) => set('captions_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>렌더 provider{badge('render_provider')}</>}
          description="영상 합성 도구입니다. 새로 만들어지는 단계부터 적용됩니다."
        >
          <Select
            value={draft.render_provider}
            options={RENDER_PROVIDERS}
            onChange={(v) => set('render_provider', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>Whisper 모델{badge('whisper_model')}</>}
          description="클수록 자막이 정확하지만 느립니다. 다음 실행부터 적용됩니다."
        >
          <Select
            value={draft.whisper_model}
            options={WHISPER_MODELS}
            onChange={(v) => set('whisper_model', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>렌더 배경색{badge('render_bg_color')}</>}
          description="영상 배경으로 쓰는 단색입니다. 다음 실행부터 적용됩니다."
        >
          <span className="flex shrink-0 items-center gap-2">
            <input
              type="color"
              className="h-8 w-10 rounded border border-line-strong"
              value={draft.render_bg_color}
              onChange={(e) => set('render_bg_color', e.target.value)}
            />
            <input
              className="w-28 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm text-fg"
              value={draft.render_bg_color}
              onChange={(e) => set('render_bg_color', e.target.value)}
            />
          </span>
        </SettingRow>

        <SettingRow
          label={<>렌더 폰트{badge('render_font')}</>}
          description="자막에 쓰는 글꼴 이름입니다. 서버에 설치된 글꼴이어야 합니다. 다음 실행부터 적용됩니다."
        >
          <input
            className={inputClass}
            value={draft.render_font}
            onChange={(e) => set('render_font', e.target.value)}
          />
        </SettingRow>

        <SettingRow
          label={<>렌더 폰트 크기{badge('render_font_size')}</>}
          description="자막 글자 크기입니다 (8~200). 다음 실행부터 적용됩니다."
        >
          <NumberInput
            value={draft.render_font_size}
            onChange={(v) => set('render_font_size', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>스톡 소스 우선순위{badge('stock_sources')}</>}
          description="배경 소재를 찾을 순서입니다. 앞의 소스에서 못 찾으면 다음으로 넘어갑니다. 다음 실행부터 적용됩니다."
        >
          <select
            className={selectClass}
            value={draft.stock_sources.join(',')}
            onChange={(e) => set('stock_sources', e.target.value.split(','))}
          >
            {STOCK_ORDERS.map((o) => (
              <option key={o.value.join(',')} value={o.value.join(',')}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>

        <SettingRow
          label={<>씬당 다운로드 상한{badge('stock_max_bytes')}</>}
          description="배경 소재 하나의 최대 크기(MB)입니다 (1~500). 다음 실행부터 적용됩니다."
        >
          <NumberInput
            value={Math.round(draft.stock_max_bytes / MB)}
            onChange={(v) => set('stock_max_bytes', v * MB)}
          />
        </SettingRow>

        <SettingRow
          label={<>스톡 타임아웃{badge('stock_timeout_sec')}</>}
          description="소재를 내려받을 때 기다리는 최대 시간(초)입니다 (5~300). 다음 실행부터 적용됩니다."
        >
          <NumberInput
            value={draft.stock_timeout_sec}
            onChange={(v) => set('stock_timeout_sec', v)}
          />
        </SettingRow>
      </section>

      <section className="divide-y divide-line-subtle rounded-lg border border-line bg-surface px-6">
        <h2 className="pt-5 pb-1 text-sm font-semibold text-fg">계정 · 보안</h2>

        <SettingRow
          label={<>로그인 실패 잠금 횟수{badge('failed_login_limit')}</>}
          description="이 횟수만큼 연속 실패하면 계정이 잠깁니다 (1~100)."
        >
          <NumberInput
            value={draft.failed_login_limit}
            onChange={(v) => set('failed_login_limit', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>비밀번호 최소 길이{badge('password_min_len')}</>}
          description="회원가입과 비밀번호 변경에 함께 적용됩니다 (8~128). 기존 비밀번호는 그대로 쓸 수 있습니다."
        >
          <NumberInput
            value={draft.password_min_len}
            onChange={(v) => set('password_min_len', v)}
          />
        </SettingRow>

        <SettingRow
          label={<>가입 자동 승인{badge('signup_auto_approve')}</>}
          description="켜면 가입 즉시 로그인할 수 있습니다. 이미 대기 중인 사용자에게는 적용되지 않습니다."
        >
          <input
            type="checkbox"
            className="h-5 w-5 shrink-0 accent-primary"
            checked={draft.signup_auto_approve}
            onChange={(e) => set('signup_auto_approve', e.target.checked)}
          />
        </SettingRow>
      </section>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={() => {
            setDraft(snapshot.settings)
            setSaved(false)
            setError(null)
          }}
          disabled={!dirty || saving}
          className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-fg-body hover:bg-surface-muted disabled:opacity-50"
        >
          되돌리기
        </button>
        <button
          type="button"
          onClick={save}
          disabled={!dirty || saving}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-50"
        >
          {saving ? '저장 중…' : '저장'}
        </button>
      </div>
    </div>
  )
}
