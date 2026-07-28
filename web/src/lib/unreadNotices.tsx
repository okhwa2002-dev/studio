import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
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

  // 화면 이동이 빠르면 이전 요청이 나중에 도착해 최신 값을 덮을 수 있다.
  // 요청마다 번호를 달고, 도착 시점에 자기가 최신이 아니면 결과를 버린다.
  // (언마운트 뒤 도착한 응답도 같은 검사에 걸려 setCount를 부르지 않는다.)
  const latestRequest = useRef(0)

  const refresh = useCallback(() => {
    const requestId = ++latestRequest.current
    // 배지는 부가 정보다. 조회가 실패하면 0으로 두고 배지를 그리지 않는다.
    notices
      .unreadCount()
      .then((data) => {
        if (requestId === latestRequest.current) setCount(data.count)
      })
      .catch(() => {
        if (requestId === latestRequest.current) setCount(0)
      })
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
