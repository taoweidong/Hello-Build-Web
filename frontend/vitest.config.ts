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
    restoreMocks: true,
    // 环境性 flaky 治理（R5-T1）：panorama 重型组件挂载测试（真实 Element Plus
    // + router + 多段 flushPromises）在多 worker 高负载并行时偶发突破 vitest
    // 默认 5s 超时（单文件复跑全绿、失败集合每次不同）。放宽到 15s 固化；
    // 纪律：全量红灯先单文件复跑甄别环境性超时。
    testTimeout: 15000,
    hookTimeout: 15000
  }
});
