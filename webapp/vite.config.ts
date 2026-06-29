import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    allowedHosts: ['goliath'],
    port: 10999,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": { target: "http://127.0.0.1:10998", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:10998" },
      "/mcp": { target: "http://127.0.0.1:10998", ws: true },
    },
  },
});
