import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 构建产物输出到上级 static/，由 FastAPI 托管。
// dev 时把 /api 代理到本地 FastAPI（mediamaid web --port 8500）。
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8500",
    },
  },
});
