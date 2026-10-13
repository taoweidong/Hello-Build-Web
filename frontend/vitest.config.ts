// vitest 单元测试配置：独立于 vite.config.ts，仅需别名与 jsdom 环境
import path from "path";
import vue from "@vitejs/plugin-vue";
import Icons from "unplugin-icons/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [vue(), Icons({ compiler: "vue3", scale: 1 })],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src")
    }
  },
  test: {
    environment: "jsdom",
    include: ["src/**/__tests__/**/*.spec.ts"],
    // 全局注册 Element Plus（与 main.ts 对齐），布局组件按真实组件渲染
    setupFiles: ["./vitest.setup.ts"],
    // 拦截器/组件测试可能触发 requestAnimationFrame 等，使用 jsdom 默认配置即可
    restoreMocks: true
  }
});
