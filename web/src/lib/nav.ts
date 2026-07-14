export type NavItem = {
  path: string
  label: string
  icon: string
  adminOnly?: boolean
}

// 메뉴는 여기에만 적는다. 사이드바(무엇을 보여줄지)와 상단바(지금 어디인지)가
// 같은 배열을 읽으므로, 라벨이 두 곳에서 어긋날 수 없다.
export const NAV: NavItem[] = [
  { path: '/dashboard', label: '대시보드', icon: '📊' },
  { path: '/projects', label: '프로젝트', icon: '🎬' },
  { path: '/settings', label: '설정', icon: '⚙️' },
  { path: '/admin/approvals', label: '가입 승인', icon: '🛡️', adminOnly: true },
  { path: '/admin/users', label: '사용자 관리', icon: '👥', adminOnly: true },
  { path: '/admin/projects', label: '전체 프로젝트', icon: '🗂️', adminOnly: true },
  { path: '/admin/system', label: '시스템 설정', icon: '🔧', adminOnly: true },
]

export function navTitle(pathname: string): string {
  return NAV.find((item) => item.path === pathname)?.label ?? ''
}
