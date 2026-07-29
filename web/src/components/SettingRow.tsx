import type { ReactNode } from 'react'

// 설정 항목 한 줄: 왼쪽에 라벨·설명, 오른쪽에 조작 요소.
// 개인 설정(Settings)과 시스템 설정(AdminSystem)이 같은 모양을 공유한다.
// label이 ReactNode인 것은 시스템 설정이 라벨 옆에 "변경됨" 배지를 붙이기 때문이다.
export function SettingRow({
  label,
  description,
  children,
}: {
  label: ReactNode
  description: string
  children: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-4">
      <div>
        <div className="text-sm font-medium text-fg">{label}</div>
        <div className="mt-0.5 text-xs text-fg-muted">{description}</div>
      </div>
      {children}
    </div>
  )
}
