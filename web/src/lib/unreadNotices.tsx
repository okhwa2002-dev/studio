import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { notices } from './notices'

type UnreadNoticesState = {
  count: number
  refresh: () => void
}

const UnreadNoticesContext = createContext<UnreadNoticesState | null>(null)

// 상단바 배지가 읽는 유일한 상태다. 값을 가진 곳이 한 군데뿐이라, 공지를 읽은
// 화면이 refresh()만 부르면 배지가 즉시 줄어든다.
export function UnreadNoticesProvider({ children }: { children: ReactNode }) {
  const [count, setCount] = useState(0)
  const { pathname } = useLocation()

  const refresh = useCallback(() => {
    // 배지는 부가 정보다. 조회가 실패하면 0으로 두고 배지를 그리지 않는다.
    notices
      .unreadCount()
      .then((data) => setCount(data.count))
      .catch(() => setCount(0))
  }, [])

  // 최초 마운트와 화면 이동 때 갱신한다. 같은 화면에 머문 채 공지를 읽는 경우는
  // 그 화면이 refresh()를 직접 부른다.
  useEffect(() => {
    refresh()
  }, [refresh, pathname])

  return (
    <UnreadNoticesContext.Provider value={{ count, refresh }}>
      {children}
    </UnreadNoticesContext.Provider>
  )
}

export function useUnreadNotices(): UnreadNoticesState {
  const state = useContext(UnreadNoticesContext)
  if (state === null) {
    throw new Error('useUnreadNotices는 UnreadNoticesProvider 안에서만 사용할 수 있습니다.')
  }
  return state
}
