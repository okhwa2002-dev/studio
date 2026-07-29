import { useEffect, useState } from 'react'
import { api } from './api'

// 서버가 최종 권한이다. 이 값은 화면이 즉각적인 피드백을 주기 위한 힌트일 뿐이다.
// 불러오기 전/실패 시에는 서버의 하한과 같은 8을 쓴다.
const FALLBACK_MIN_LEN = 8

export function usePasswordMinLen(): number {
  const [minLen, setMinLen] = useState(FALLBACK_MIN_LEN)

  useEffect(() => {
    let alive = true
    api
      .get<{ password_min_len: number }>('/auth/policy')
      .then((p) => {
        if (alive) setMinLen(p.password_min_len)
      })
      .catch(() => {
        // 정책 조회 실패로 가입·변경 화면을 막지 않는다. 서버가 어차피 다시 검증한다.
      })
    return () => {
      alive = false
    }
  }, [])

  return minLen
}
