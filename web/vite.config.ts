import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 개발 중 프론트(:5173)와 API(:8000)를 같은 출처로 만든다.
// 브라우저 입장에서 동일 출처이므로 CORS 설정이 필요 없고,
// httpOnly + SameSite=Lax 인증 쿠키가 그대로 동작한다.
//
// 프록시 키는 "경로 접두사"이고 XHR뿐 아니라 문서 요청(주소창 입력·새로고침)에도
// 걸린다. 따라서 여기 적은 접두사 아래로는 프론트 라우트를 둘 수 없다.
// 관리자 API는 /admin/users 뿐이므로 접두사를 그 경로까지 좁혔다. 이렇게 하지 않으면
// 다음 Plan의 화면 /admin/approvals가 프록시에 먹혀 SPA 대신 FastAPI의 404 JSON이 뜬다
// (앱 안에서 링크로 이동할 때는 멀쩡하고 새로고침할 때만 깨져서 발견이 늦다).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/auth': 'http://localhost:8000',
      '/admin/users': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
