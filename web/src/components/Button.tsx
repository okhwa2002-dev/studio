import type { ButtonHTMLAttributes } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  pending?: boolean
}

export function Button({ pending, children, disabled, ...rest }: Props) {
  return (
    <button
      // 제출 중에는 비활성화해 중복 제출을 막는다.
      disabled={disabled || pending}
      className="w-full rounded-md bg-primary px-3 py-2 font-medium text-on-primary disabled:opacity-50"
      {...rest}
    >
      {pending ? '처리 중…' : children}
    </button>
  )
}
