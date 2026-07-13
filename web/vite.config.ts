import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 개발 중 프론트(:5173)와 API(:8000)를 같은 출처로 만든다.
// 브라우저 입장에서 동일 출처이므로 CORS 설정이 필요 없고,
// httpOnly + SameSite=Lax 인증 쿠키가 그대로 동작한다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/auth': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
