import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // En desarrollo, /api se redirige al backend FastAPI (uvicorn en :8000).
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
})
