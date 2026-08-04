// 페이지당 몇 건을 보여줄지 고르는 셀렉터. Pagination과 같은 방침이다 —
// 도메인을 모르고 숫자만 알며, 바깥 여백·정렬은 두지 않는다(배치는 쓰는 쪽이 정한다).
export const PAGE_SIZE_OPTIONS = [20, 50, 100] as const

// 목록 화면 일곱 곳이 모두 이 값에서 시작한다. 화면마다 10 / 50으로 갈려 있던
// 기본값을 하나로 맞춘 것이라, 바꾸려면 여기 한 곳만 고치면 된다.
export const DEFAULT_PAGE_SIZE = 20

export function PageSizeSelect({
  value,
  onChange,
}: {
  value: number
  onChange: (size: number) => void
}) {
  return (
    <select
      value={value}
      // select의 value는 언제나 문자열이다. 쓰는 쪽은 숫자만 다루게 여기서 되돌린다.
      onChange={(e) => onChange(Number(e.target.value))}
      aria-label="페이지당 건수"
      className="rounded-md border border-line-strong px-2 py-1.5 text-sm text-fg-body hover:bg-surface-muted focus:border-fg-muted focus:outline-none"
    >
      {PAGE_SIZE_OPTIONS.map((size) => (
        <option key={size} value={size}>
          {size}건씩
        </option>
      ))}
    </select>
  )
}
