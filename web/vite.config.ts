import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 개발 중 프론트(:5173)와 API(:8000)를 같은 출처로 만든다.
// 브라우저 입장에서 동일 출처이므로 CORS 설정이 필요 없고,
// httpOnly + SameSite=Lax 인증 쿠키가 그대로 동작한다.
//
// 프록시 키는 "경로 접두사"이고 XHR뿐 아니라 문서 요청(주소창 입력·새로고침)에도
// 걸린다. 그래서 모든 API를 /api 아래로 몰아, 프론트 SPA 라우트(/admin/users 등)와
// 절대 겹치지 않게 했다. /api만 백엔드로 넘기므로, SPA 경로에서 새로고침해도
// 문서 요청이 index.html로 서빙되어 앱이 정상적으로 뜬다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
