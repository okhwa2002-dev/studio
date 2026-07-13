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

// 백엔드의 /auth/refresh는 리프레시 토큰을 회전시키며 재사용을 탈취로 간주한다
// (이미 폐기된 토큰이 다시 제시되면 해당 사용자의 모든 세션을 폐기한다).
// StrictMode의 effect 이중 실행 등으로 401이 동시에 여러 건 발생하면, 각 요청이
// 같은 리프레시 쿠키를 들고 개별적으로 /auth/refresh를 호출하게 되어 뒤에 도착한
// 쪽이 앞선 쪽이 이미 회전시킨 토큰을 재사용하는 꼴이 되고, 스스로 이 경보를
// 울려 모든 세션을 날려버릴 수 있다. 그래서 동시 요청은 진행 중인 갱신 하나를
// 공유하고, 실제 네트워크 호출은 한 번만 나가도록 한다.
let refreshInFlight: Promise<Response> | null = null

function refreshOnce(): Promise<Response> {
  refreshInFlight ??= send('/auth/refresh', { method: 'POST' }).finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

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
    let refreshed: Response | null = null
    try {
      refreshed = await refreshOnce()
    } catch {
      // 갱신 시도가 네트워크 오류로 실패해도 원래의 401을 그대로 흘려보낸다
      // → 호출자가 로그아웃 상태로 처리. (갱신 실패는 종류를 가리지 않는다.)
      // refreshInFlight는 공유 프로미스이므로, 동시에 대기 중이던 다른 호출자들도
      // 각자 이 catch로 떨어져 자신의 원래 401을 그대로 던지게 된다.
    }

    if (refreshed?.ok) {
      // 재시도는 딱 한 번. 재귀하지 않으므로 무한 루프가 생길 수 없다.
      // 여기서의 실패는 갱신이 성공한 뒤의 진짜 실패이므로 삼키지 않고 그대로 던진다.
      response = await send(path, init)
    }
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
