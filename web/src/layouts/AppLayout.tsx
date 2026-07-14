import { Outlet } from 'react-router-dom'
import { Sidebar } from '../components/layout/Sidebar'
import { Topbar } from '../components/layout/Topbar'

// 로그인 후 화면들이 공유하는 껍데기. 라우트의 부모로 두어, 페이지를 옮겨 다녀도
// 리마운트되지 않게 한다(사이드바가 깜빡이지 않는다).
export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      {/* min-w-0: 콘텐츠가 넓어져도 사이드바를 밀어내지 않는다. */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
