export type NavItem = {
  path: string
  label: string
  icon: string
  adminOnly?: boolean
}

// 사이드바가 가입 승인 대기 건수 배지를 붙이는 항목. 경로 문자열이 두 곳에서
// 어긋나지 않게 여기서 뽑아 쓴다. (가입 승인 전용 화면은 두지 않는다 —
// 승인·거절은 사용자 관리의 "대기" 탭이 담당하고, 알림은 이 배지가 맡는다.)
export const ADMIN_USERS_PATH = '/admin/users'

// 메뉴는 여기에만 적는다. 사이드바(무엇을 보여줄지)와 본문 제목(지금 어디인지)이
// 같은 배열을 읽으므로, 라벨이 두 곳에서 어긋날 수 없다.
// (상단바는 로고를 갖는다 — 페이지 제목은 AppLayout이 본문 위에 그린다)
export const NAV: NavItem[] = [
  { path: '/dashboard', label: '대시보드', icon: '📊' },
  { path: '/projects', label: '프로젝트', icon: '🎬' },
  { path: '/notices', label: '공지사항', icon: '📢' },
  { path: '/faqs', label: 'FAQ', icon: '❓' },
  { path: '/settings', label: '설정', icon: '⚙️' },
  { path: ADMIN_USERS_PATH, label: '사용자 관리', icon: '👥', adminOnly: true },
  { path: '/admin/projects', label: '전체 프로젝트', icon: '🗂️', adminOnly: true },
  { path: '/admin/notices', label: '공지 관리', icon: '🗞️', adminOnly: true },
  { path: '/admin/faqs', label: 'FAQ 관리', icon: '📖', adminOnly: true },
  { path: '/admin/system', label: '시스템 설정', icon: '🔧', adminOnly: true },
]

export function navTitle(pathname: string): string {
  return NAV.find((item) => item.path === pathname)?.label ?? ''
}
