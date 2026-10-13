// 调度全景路由：/panorama 父路由 + 5 个独立布局子路由
// 后端只维护一套接口，5 个页面共用同一 API 与权限校验（设计文档 §4.0）
//
// 落点优先级：?layout= 深链 > localStorage 偏好 > 默认布局（月历矩阵）。
// 解析逻辑收敛在 views/panorama/shared/panoramaLayouts.ts 的 resolveEntryLayout，
// 本文件只做接线，避免优先级规则散落两处。
import { resolveEntryLayout } from "@/views/panorama/shared/panoramaLayouts";

const Layout = () => import("@/layout/index.vue");

/** 全部角色（5 个布局对所有登录角色开放，权限细化到事件级 permissions 包） */
const ALL_ROLES = ["admin", "pm", "builder", "tester", "integrator"];

export const panoramaRoute = {
  path: "/panorama",
  name: "Panorama",
  component: Layout,
  redirect: (to: { query: Record<string, unknown> }) =>
    `/panorama/${resolveEntryLayout(to.query)}`,
  meta: {
    icon: "ep/grid",
    title: "调度全景",
    rank: 16
  },
  children: [
    {
      path: "/panorama/dashboard",
      name: "PanoramaDashboard",
      component: () =>
        import("@/views/panorama/layouts/s1-dashboard/index.vue"),
      meta: { title: "调度全景 · 态势大屏", roles: ALL_ROLES }
    },
    {
      path: "/panorama/gantt",
      name: "PanoramaGantt",
      component: () => import("@/views/panorama/layouts/s2-gantt/index.vue"),
      meta: { title: "调度全景 · 时空甘特", roles: ALL_ROLES }
    },
    {
      path: "/panorama/month",
      name: "PanoramaMonth",
      component: () => import("@/views/panorama/layouts/s3-month/index.vue"),
      meta: { title: "调度全景 · 月历矩阵", roles: ALL_ROLES }
    },
    {
      path: "/panorama/board",
      name: "PanoramaBoard",
      component: () => import("@/views/panorama/layouts/s4-board/index.vue"),
      meta: { title: "调度全景 · 分组看板", roles: ALL_ROLES }
    },
    {
      path: "/panorama/timeline",
      name: "PanoramaTimeline",
      component: () => import("@/views/panorama/layouts/s5-timeline/index.vue"),
      meta: { title: "调度全景 · 时间轴流水", roles: ALL_ROLES }
    }
  ]
};
