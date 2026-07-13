import type { InputHTMLAttributes } from 'react'

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string
}

export function TextField({ label, error, id, ...rest }: Props) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-slate-900"
        {...rest}
      />
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  )
}
