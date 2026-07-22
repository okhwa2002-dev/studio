import { ApiError } from './api'
import { projects, type ProjectDetail, type Stage } from './projects'

export type StageProgress = { percent: number | null; message: string }

export type ProjectEvent =
  | ({ type: 'snapshot'; progress: Record<string, StageProgress> } & ProjectDetail)
  | { type: 'stage'; project: ProjectDetail['project']; stage: Stage }
  | ({ type: 'progress'; stage: string } & StageProgress)
  // 재접속을 포기해야 하는 영구 실패(존재하지 않거나 남의 프로젝트, 갱신 후에도 만료된 인증).
  // message는 백엔드가 내려준 한국어 문구를 그대로 전달한다.
  | { type: 'fatal'; status: number; message: string }

const FIRST_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 30_000
// 연결이 이 시간(ms) 이상 살아있어야 "안정됐다"고 보고 백오프를 리셋한다.
// 서버 ping 주기(15s, app/api/projects.py)보다 충분히 짧아 정상 연결은 여유 있게 통과하지만,
// onopen 직후 바로 끊기는 프록시 드롭/유휴 타임아웃은 걸러내 지수 백오프가 실제로 동작하게 한다.
const STABLE_CONNECTION_MS = 5000

// 프로젝트 상세 화면의 실시간 구독. 정리 함수를 돌려준다.
//
// EventSource는 401을 받아도 스스로 무한히 재접속한다. 그래서 오류가 나면 직접 닫고,
// 다시 붙기 전에 평범한 API를 한 번 태운다 — api.ts의 401→refresh→재시도가 거기서
// 쿠키를 갱신해 준다. 그마저 실패하면(로그아웃 등) 백오프를 늘리며 물러선다.
export function subscribeProject(id: number, onEvent: (e: ProjectEvent) => void): () => void {
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let stableTimer: ReturnType<typeof setTimeout> | null = null
  let backoff = FIRST_BACKOFF_MS
  let closed = false

  const clearStableTimer = () => {
    if (stableTimer) clearTimeout(stableTimer)
    stableTimer = null
  }

  const retryLater = () => {
    if (closed) return
    timer = setTimeout(reconnect, backoff)
    backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
  }

  const connect = () => {
    if (closed) return
    source = new EventSource(`/api/projects/${id}/events`)
    source.onopen = () => {
      // onopen은 HTTP 200 응답만으로도 발생한다 — 바로 끊기는 연결이면 아래 onerror가
      // 이 타이머를 취소하므로, STABLE_CONNECTION_MS를 버틴 연결만 백오프를 리셋한다.
      clearStableTimer()
      stableTimer = setTimeout(() => {
        stableTimer = null
        backoff = FIRST_BACKOFF_MS
      }, STABLE_CONNECTION_MS)
    }
    source.onmessage = (e) => {
      let parsed: ProjectEvent
      try {
        parsed = JSON.parse(e.data) as ProjectEvent
      } catch (err) {
        // 깨진 프레임은 건너뛰되, 백엔드 회귀를 디버깅할 수 있게 로그는 남긴다.
        console.error('[events] malformed SSE payload', e.data, err)
        return
      }
      onEvent(parsed)
    }
    source.onerror = () => {
      clearStableTimer()
      source?.close()
      source = null
      retryLater()
    }
  }

  const reconnect = async () => {
    if (closed) return
    try {
      await projects.detail(id)
    } catch (err) {
      // await 도중 cleanup이 호출됐을 수 있다 — 그랬다면 closed가 이미 true이므로
      // 여기서 멈춰야 한다. 그렇지 않으면 구독이 끝난 뒤에도 onEvent가 불릴 수 있다.
      if (closed) return
      // 404(프로젝트 삭제·남의 프로젝트)와, 갱신을 거치고도 살아남은 401은
      // 재시도해도 절대 낫지 않는다 — request()가 401을 만나면 이미 한 번
      // refresh를 시도한 뒤이므로, 여기 도달한 401은 그 refresh마저 실패했다는 뜻.
      // 이런 영구 실패는 cleanup과 동일하게 closed를 세워 재접속을 멈추고,
      // 호출자에게 한 번만 알린다. 그 외(네트워크 끊김, 5xx 등)는 일시적이므로
      // 기존 백오프로 계속 재시도한다.
      if (err instanceof ApiError && (err.status === 404 || err.status === 401)) {
        closed = true
        onEvent({ type: 'fatal', status: err.status, message: err.message })
        return
      }
      retryLater()
      return
    }
    connect()
  }

  connect()

  return () => {
    closed = true
    if (timer) clearTimeout(timer)
    clearStableTimer()
    source?.close()
  }
}
