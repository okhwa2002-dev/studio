import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'

export type User = {
  id: number
  email: string
  name: string
  role: 'MEMBER' | 'ADMIN'
}

type AuthState = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  // 서버가 정한 신규 계정 상태('ACTIVE' | 'PENDING')를 그대로 돌려준다 —
  // 가입 자동 승인 설정에 따라 달라지므로 호출자가 안내를 갈라야 한다.
  register: (email: string, password: string, name: string) => Promise<string>
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

  const register = async (email: string, password: string, name: string) => {
    // 가입 자동 승인이 켜져 있으면 신규 계정은 곧바로 ACTIVE다 — "가입 직후엔 무조건
    // PENDING"이 아니므로 응답의 status를 버리지 않고 호출자에게 넘긴다.
    // 여기서 user를 세팅하지 않는 것은 여전하다: /auth/register는 인증 쿠키를 내려주지
    // 않으므로 ACTIVE라도 로그인은 따로 해야 한다.
    const created = await api.post<{ id: number; status: string }>('/auth/register', {
      email,
      password,
      name,
    })
    return created.status
  }

  const logout = async () => {
    // 요청이 실패해도(예: 개발 중 서버 재기동) 로컬 세션 상태는 정리한다.
    try {
      await api.post('/auth/logout')
    } finally {
      setUser(null)
    }
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
