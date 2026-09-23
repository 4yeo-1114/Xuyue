import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  base: "/",
  server: {
    host: "0.0.0.0", // 修改为 0.0.0.0 以支持 IPv4
    port: 6889, // 前端页面端口
    hmr: {
      overlay: false,
    },
    allowedHosts: true, // 允许所有 host 访问，解决在其他 IP 地址访问时的白屏问题
    cors: true, // 开启 CORS 允许跨域
    proxy: {
      "/api": {
        target: "http://127.0.0.1:6888",
        changeOrigin: true,
        agent: false, // 禁用 keep-alive 连接池，每次新建连接，规避 socket 复用 bug
        proxyTimeout: 30_000, // 代理等待后端响应的超时
        timeout: 30_000, // 建立到后端连接的超时
      },
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
