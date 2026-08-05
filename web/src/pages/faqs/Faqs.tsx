import { useEffect, useState } from 'react'
import { FormError } from '../../components/FormError'
import { errorMessage } from '../../lib/api'
import {
  FAQ_CATEGORIES,
  FAQ_CATEGORY_LABEL,
  faqs,
  type Faq,
  type FaqCategory,
} from '../../lib/faqs'

type CategoryFilter = FaqCategory | 'ALL'

// Table을 쓰지 않는다 — Table은 "행 = 열들의 나열"이 전제인데 아코디언은 행 아래로
// 열 구분 없는 본문이 펼쳐진다. colSpan 트릭을 넣으면 이후 Table을 손볼 때마다
// 이 화면까지 확인해야 한다.
function FaqItem({ faq, open, onToggle }: { faq: Faq; open: boolean; onToggle: () => void }) {
  return (
    <li className="border-b border-line-subtle last:border-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-muted"
      >
        <span className="shrink-0 font-medium text-fg-muted">Q</span>
        <span className="flex-1 text-sm text-fg-body">{faq.question}</span>
        <span className="shrink-0 text-xs text-fg-muted">{open ? '▲' : '▼'}</span>
      </button>
      {/* 답변은 일반 텍스트다. 줄바꿈을 살려서 그대로 보여준다. */}
      {open && (
        <p className="px-4 pb-4 pl-11 text-sm whitespace-pre-wrap text-fg-body">{faq.answer}</p>
      )}
    </li>
  )
}

export function Faqs() {
  const [rows, setRows] = useState<Faq[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [category, setCategory] = useState<CategoryFilter>('ALL')
  const [query, setQuery] = useState('')
  // 한 번에 하나만 열린다. 같은 항목을 다시 누르면 닫힌다.
  const [openId, setOpenId] = useState<number | null>(null)

  useEffect(() => {
    faqs
      .list()
      .then(setRows)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [])

  const keyword = query.trim().toLowerCase()
  const filteredRows = rows.filter((f) => {
    if (category !== 'ALL' && f.category !== category) return false
    if (!keyword) return true
    return f.question.toLowerCase().includes(keyword) || f.answer.toLowerCase().includes(keyword)
  })

  // 필터를 바꿀 때 열린 항목을 닫는다. 걸러져 사라진 항목이 열린 채로 남아 있으면
  // 필터를 되돌렸을 때 예상치 못한 항목이 펼쳐져 있다.
  const changeCategory = (next: CategoryFilter) => {
    setCategory(next)
    setOpenId(null)
  }

  const changeQuery = (next: string) => {
    setQuery(next)
    setOpenId(null)
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <button
            onClick={() => changeCategory('ALL')}
            className={`rounded-md px-3 py-1.5 text-sm ${
              category === 'ALL'
                ? 'bg-primary font-medium text-on-primary'
                : 'text-fg-muted hover:bg-surface-muted'
            }`}
          >
            전체
          </button>
          {FAQ_CATEGORIES.map((value) => (
            <button
              key={value}
              onClick={() => changeCategory(value)}
              className={`rounded-md px-3 py-1.5 text-sm ${
                category === value
                  ? 'bg-primary font-medium text-on-primary'
                  : 'text-fg-muted hover:bg-surface-muted'
              }`}
            >
              {FAQ_CATEGORY_LABEL[value]}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => changeQuery(e.target.value)}
          placeholder="질문 또는 답변 검색"
          className="w-64 rounded-md border border-line-strong px-3 py-1.5 text-sm focus:border-fg-muted focus:outline-none"
        />
      </div>

      {error && (
        <div className="mb-4">
          <FormError message={error} />
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-sm text-fg-muted">불러오는 중…</div>
      ) : error ? null : filteredRows.length === 0 ? (
        <div className="rounded-xl border border-line bg-surface p-10 text-center text-sm text-fg-muted">
          {keyword ? '검색 결과가 없습니다.' : '등록된 FAQ가 없습니다.'}
        </div>
      ) : (
        // 페이지네이션을 두지 않는다 — 훑어 내려가며 찾는 화면이라 페이지를 넘기면
        // "다음 장에 있나" 확인하러 왕복하게 된다. 분류 탭과 검색이 그 역할을 한다.
        <ul className="rounded-xl border border-line bg-surface">
          {filteredRows.map((faq) => (
            <FaqItem
              key={faq.id}
              faq={faq}
              open={openId === faq.id}
              onToggle={() => setOpenId(openId === faq.id ? null : faq.id)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
