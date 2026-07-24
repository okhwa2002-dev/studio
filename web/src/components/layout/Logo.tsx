import { Link } from 'react-router-dom'

// 상단바의 브랜드 자리. 파비콘과 같은 마크를 써서 탭·화면이 같은 얼굴을 갖는다.
// 누르면 홈(대시보드)으로 — 로고 클릭은 홈이라는 웹 관습을 따른다.
export function Logo() {
  return (
    <Link to="/dashboard" aria-label="Studio 홈" className="flex items-center gap-2">
      <img src="/favicon.svg" alt="" width={22} height={21} />
      <span className="text-base font-semibold tracking-tight text-slate-900">Studio</span>
    </Link>
  )
}
