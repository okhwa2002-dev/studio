import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from '../components/layout/Sidebar'
import { Topbar } from '../components/layout/Topbar'

// 로그인 후 화면들이 공유하는 껍데기. 라우트의 부모로 두어, 페이지를 옮겨 다녀도
// 리마운트되지 않게 한다.
export function AppLayout() {
  // 사이드바는 콘텐츠 위에 떠서 열리는 서랍이다. 열려 있는 동안 콘텐츠를 가리므로
  // 기본은 닫힘이고, 메뉴를 고르면 닫힌다(상태를 저장해 둘 이유가 없다).
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])

  return (
    // 콘텐츠는 사이드바와 무관하게 항상 전체 폭을 쓴다. 열고 닫아도 레이아웃이 흔들리지 않는다.
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Topbar menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((prev) => !prev)} />
      <main className="flex-1 p-6">
        <Outlet />
      </main>

      {menuOpen && (
        <>
          {/* 바깥을 누르면 닫힌다. 사이드바(z-30) 아래에 깔리고, 상단바는 덮지 않는다. */}
          <div
            className="fixed inset-x-0 bottom-0 top-14 z-20 bg-slate-900/30"
            onClick={() => setMenuOpen(false)}
            aria-hidden
          />
          <Sidebar onNavigate={() => setMenuOpen(false)} onClose={() => setMenuOpen(false)} />
        </>
      )}
    </div>
  )
}
