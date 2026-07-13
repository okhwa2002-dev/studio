import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'

export type User = {
  id: number
  email: string
  role: 'member' | 'admin'
}

type AuthState = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 인증 토큰은 httpOnly 쿠키라 JS가 읽을 수 없다.
    // 따라서 "지금 로그인돼 있는가"는 서버에 물어보는 수밖에 없다.
    api
      .get<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null)) // 401(비로그인)·네트워크 오류 모두 로그아웃 상태로 취급
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    // 로그인 응답이 이미 {id, email, role}이므로 /auth/me를 또 부르지 않는다.
    const loggedIn = await api.post<User>('/auth/login', { email, password })
    setUser(loggedIn)
  }

  const register = async (email: string, password: string) => {
    // 가입 직후 사용자는 status=pending이라 로그인 자체가 불가능하다.
    // 그래서 여기서 user를 세팅하지 않는다. 호출자가 /pending으로 안내한다.
    await api.post<{ id: number; status: string }>('/auth/register', { email, password })
  }

  const logout = async () => {
    await api.post('/auth/logout')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext)
  if (state === null) {
    throw new Error('useAuth는 AuthProvider 안에서만 사용할 수 있습니다.')
  }
  return state
}
