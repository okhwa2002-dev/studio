import { useSyncExternalStore } from 'react'

export type ThemePref = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

// index.html 인라인 스크립트와 반드시 같은 키를 쓴다(첫 페인트 전 적용과 일관성).
const STORAGE_KEY = 'theme-preference'

const media = window.matchMedia('(prefers-color-scheme: dark)')
const listeners = new Set<() => void>()

function readPref(): ThemePref {
  const v = localStorage.getItem(STORAGE_KEY)
  return v === 'light' || v === 'dark' ? v : 'system'
}

// 선호값을 실제 테마(light/dark)로 해석한다. 'system'은 OS 설정을 따른다.
function resolve(pref: ThemePref): ResolvedTheme {
  return pref === 'dark' || (pref === 'system' && media.matches) ? 'dark' : 'light'
}

// 해석된 테마로 <html>.dark를 켜고 끈다.
function apply(pref: ThemePref): void {
  document.documentElement.classList.toggle('dark', resolve(pref) === 'dark')
}

function notify(): void {
  listeners.forEach((l) => l())
}

// OS 테마가 바뀌면 선호가 'system'일 때만 따라 반영한다.
media.addEventListener('change', () => {
  if (readPref() === 'system') {
    apply('system')
    notify()
  }
})

export function initTheme(): void {
  // 인라인 스크립트가 이미 클래스를 달았지만, 저장값 기준으로 한 번 더 맞춘다(방어).
  apply(readPref())
}

export function setThemePref(pref: ThemePref): void {
  if (pref === 'system') localStorage.removeItem(STORAGE_KEY)
  else localStorage.setItem(STORAGE_KEY, pref)
  apply(pref)
  notify()
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

// 현재 선호값(system/light/dark)을 구독한다. setThemePref·OS 변경 시 리렌더된다.
export function useThemePref(): ThemePref {
  return useSyncExternalStore(subscribe, readPref, () => 'system')
}

// 실제 적용 중인 테마(light/dark). 'system'일 때 OS가 바뀌면 값이 달라져 리렌더된다.
export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, () => resolve(readPref()), () => 'light')
}

// 현재 보이는 테마의 반대로 뒤집는다(system이면 해석된 값 기준으로 전환).
export function toggleTheme(): void {
  setThemePref(resolve(readPref()) === 'dark' ? 'light' : 'dark')
}
