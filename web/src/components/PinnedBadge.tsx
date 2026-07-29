// 상단 고정 공지를 표시하는 배지. 목록의 No 자리에 번호 대신 들어간다 —
// 고정 공지는 순번 바깥에 있기 때문이다(사용자·관리자 목록 공용).
export function PinnedBadge() {
  return (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
      공지
    </span>
  )
}
