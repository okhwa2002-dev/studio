import type { InputHTMLAttributes } from 'react'

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string
}

export function TextField({ label, error, id, ...rest }: Props) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-fg-body">
        {label}
      </label>
      <input
        id={id}
        className="w-full rounded-md border border-line-strong px-3 py-2 text-fg outline-none focus:border-fg"
        {...rest}
      />
      {error && <p className="mt-1 text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
