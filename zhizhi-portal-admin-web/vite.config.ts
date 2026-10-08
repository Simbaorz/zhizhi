import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {plugins:[vue()],server:{port:5175,proxy:{"/api":{target:env.ZHIZHI_PORTAL_API_PROXY_TARGET || "http://127.0.0.1:8003",changeOrigin:true}}}};
});
