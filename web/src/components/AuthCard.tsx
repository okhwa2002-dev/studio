import type { ReactNode } from 'react'

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4">
      {/* max-w-sm(384px)에서는 안내 문구가 두 줄로 접혔다. 가장 긴 문구인
          "비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요."가 text-sm 기준 약 360px인데,
          카드 패딩(p-6 좌우 48px)과 안내 박스 패딩(px-4 좌우 32px)을 빼면 304px밖에 남지 않았다.
          max-w-md(448px)로는 여유가 8px뿐이라 문구가 조금만 길어져도 다시 접힌다. */}
      <div className="w-full max-w-lg rounded-xl border border-line bg-surface p-6 shadow-sm">
        <h1 className="mb-6 text-xl font-semibold text-fg">{title}</h1>
        {children}
      </div>
    </div>
  )
}
