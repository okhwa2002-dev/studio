import { api } from './api'

export type FaqCategory = 'ACCOUNT' | 'PROJECT' | 'PRODUCTION' | 'ETC'

// 코드값 → 화면 라벨. 사용자 분류 탭·관리자 목록 셀·관리자 모달 셀렉트가 모두
// 이 하나를 읽으므로 라벨이 세 곳에서 어긋날 수 없다.
export const FAQ_CATEGORY_LABEL: Record<FaqCategory, string> = {
  ACCOUNT: '계정',
  PROJECT: '프로젝트',
  PRODUCTION: '영상제작',
  ETC: '기타',
}

// 탭·셀렉트가 도는 순서. Object.keys는 타입이 string[]으로 넓어져 FaqCategory로
// 쓸 수 없으므로, 순서는 여기서 배열로 명시한다.
export const FAQ_CATEGORIES: FaqCategory[] = ['ACCOUNT', 'PROJECT', 'PRODUCTION', 'ETC']

// 목록 응답에 answer가 함께 온다 — 아코디언이 받아둔 답변을 그대로 펼친다.
// sort_order는 서버가 정렬해서 주므로 응답에 없다.
export type Faq = {
  id: number
  question: string
  answer: string
  category: FaqCategory
}

export const faqs = {
  list: () => api.get<Faq[]>('/faqs'),
}
