import { toggleTheme, useResolvedTheme } from '../lib/theme'

// 우측 하단에 떠 있는 라이트/다크 토글. 클릭하면 보이는 테마를 반대로 뒤집는다.
// 세밀한 선택(시스템 포함)은 설정 화면의 3-way 컨트롤이 담당한다 — 둘은 같은 저장소를 공유한다.
export function ThemeToggle() {
  const isDark = useResolvedTheme() === 'dark'
  const label = isDark ? '라이트 모드로 전환' : '다크 모드로 전환'
  return (
    <button
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      className="fixed bottom-6 right-6 z-30 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-surface text-lg shadow-lg hover:bg-surface-muted"
    >
      <span aria-hidden>{isDark ? '🌙' : '☀️'}</span>
    </button>
  )
}
