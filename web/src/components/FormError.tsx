export function FormError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p>
}
