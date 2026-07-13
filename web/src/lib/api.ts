export class ApiError extends Error {
  // 프로젝트 tsconfig의 erasableSyntaxOnly로 인해 생성자 매개변수 속성(public status: ...)
  // 축약 문법을 쓸 수 없다. 필드를 명시적으로 선언하고 생성자에서 대입한다.
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const UNKNOWN_MESSAGE = '알 수 없는 오류가 발생했습니다.'
const NETWORK_MESSAGE = '서버에 연결할 수 없습니다.'

// 401을 받아도 토큰 갱신을 시도하면 안 되는 경로.
// - /auth/refresh: 갱신이 갱신을 부르는 재귀를 막는다.
// - /auth/login: 비밀번호가 틀린 것이지 토큰이 만료된 게 아니다.
// - /auth/logout: 이미 로그아웃 중이다.
const NO_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout']

async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(path, {
      credentials: 'include', // 인증 쿠키를 함께 보낸다
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    // fetch 자체가 거부된 경우(서버 다운·네트워크 끊김). HTTP 상태가 없다.
    throw new ApiError(0, 'NETWORK_ERROR', NETWORK_MESSAGE)
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { code?: string; message?: string }
    return new ApiError(response.status, body.code ?? 'UNKNOWN_ERROR', body.message ?? UNKNOWN_MESSAGE)
  } catch {
    // 본문이 JSON이 아닌 경우(프록시 오류 등)
    return new ApiError(response.status, 'UNKNOWN_ERROR', UNKNOWN_MESSAGE)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response = await send(path, init)

  if (response.status === 401 && !NO_REFRESH_PATHS.includes(path)) {
    const refreshed = await send('/auth/refresh', { method: 'POST' })
    if (refreshed.ok) {
      // 재시도는 딱 한 번. 재귀하지 않으므로 무한 루프가 생길 수 없다.
      response = await send(path, init)
    }
    // 갱신이 실패하면 원래의 401을 그대로 아래로 흘려보낸다 → 호출자가 로그아웃 상태로 처리.
  }

  if (!response.ok) {
    throw await toApiError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
}
