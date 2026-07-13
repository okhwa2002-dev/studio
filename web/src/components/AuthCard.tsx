import type { ReactNode } from 'react'

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="mb-6 text-xl font-semibold text-slate-900">{title}</h1>
        {children}
      </div>
    </div>
  )
}
