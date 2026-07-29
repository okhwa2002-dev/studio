import { useEffect, useState } from 'react'
import { notices, type PopupNotice } from '../lib/notices'
import { Modal } from './Modal'

const STORAGE_KEY = 'notice_popup_dismissed'

// 오늘 날짜를 'YYYY-MM-DD'로. 브라우저 로컬 날짜 기준이며, 이 값은 서버로 가지
// 않는다("오늘 하루 보지 않기"는 기기별로 따로 노는 것이 정상 동작이다).
function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

// { 공지ID: 'YYYY-MM-DD' } 한 덩어리로 담는다. 읽을 때 오늘이 아닌 항목을
// 걸러내므로, 지난 날짜가 무한히 쌓이지 않는다.
function readDismissed(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, string>
    const now = today()
    return Object.fromEntries(Object.entries(parsed).filter(([, date]) => date === now))
  } catch {
    // 값이 깨졌으면 없는 것으로 본다.
    return {}
  }
}

function dismissForToday(id: number) {
  const next = { ...readDismissed(), [String(id)]: today() }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // 저장 공간이 없거나 차단된 경우. 이번 세션만 안 뜨는 것으로 만족한다.
  }
}

/**
 * 로그인 후 첫 화면에서 한 번 뜨는 공지 팝업.
 *
 * AppLayout에 매달려 있어 페이지를 옮겨 다녀도 다시 뜨지 않는다(AppLayout은
 * 라우트의 부모라 리마운트되지 않는다). 여러 건이면 서버가 준 순서대로
 * 한 건씩 보여준다. 닫기는 읽음 처리를 하지 않으므로 배지와 NEW는 그대로 남는다.
 */
export function NoticePopup() {
  const [queue, setQueue] = useState<PopupNotice[]>([])
  const [dontShowToday, setDontShowToday] = useState(false)

  useEffect(() => {
    // 팝업은 부가 기능이다. 조회가 실패하면 조용히 넘어간다.
    notices
      .popups()
      .then((rows) => {
        const dismissed = readDismissed()
        setQueue(rows.filter((row) => dismissed[String(row.id)] === undefined))
      })
      .catch(() => setQueue([]))
  }, [])

  const current = queue[0]
  if (!current) return null

  const close = () => {
    if (dontShowToday) dismissForToday(current.id)
    setDontShowToday(false)
    setQueue((prev) => prev.slice(1))
  }

  return (
    <Modal title={current.title} onClose={close}>
      <div className="text-xs text-fg-muted">{current.starts_at.slice(0, 10)}</div>
      <p className="mt-3 border-t border-line-subtle pt-3 text-sm whitespace-pre-wrap text-fg-body">
        {current.body}
      </p>
      <div className="mt-4 flex items-center justify-between border-t border-line-subtle pt-4">
        <label className="flex items-center gap-2 text-sm text-fg-body">
          <input
            type="checkbox"
            checked={dontShowToday}
            onChange={(e) => setDontShowToday(e.target.checked)}
          />
          오늘 하루 보지 않기
        </label>
        <button
          onClick={close}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-on-primary"
        >
          닫기
        </button>
      </div>
    </Modal>
  )
}
