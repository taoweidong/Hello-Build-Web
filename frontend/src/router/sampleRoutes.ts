// 示例菜单路由：/sample 父路由 + 5 个占位演示子路由
// 用途：验证菜单注册/角色过滤/懒加载链路的演示页，数据全部来自 views/sample/demoData.ts，
// 不接后端接口；上线业务页前可作为新页面骨架的参考样板。
const Layout = () => import("@/layout/index.vue");

/** 全部角色（示例页对所有登录角色可见） */
const ALL_ROLES = ["admin", "pm", "builder", "tester", "integrator"];

export const sampleRoute = {
  path: "/sample",
  name: "Sample",
  component: Layout,
  redirect: "/sample/overview",
  meta: {
    icon: "ep/memo",
    title: "示例菜单",
    rank: 17
  },
  children: [
    {
      path: "/sample/overview",
      name: "SampleOverview",
      component: () => import("@/views/sample/overview/index.vue"),
      meta: { title: "示例 · 概览卡片", roles: ALL_ROLES }
    },
    {
      path: "/sample/table",
      name: "SampleTable",
      component: () => import("@/views/sample/table/index.vue"),
      meta: { title: "示例 · 数据表格", roles: ALL_ROLES }
    },
    {
      path: "/sample/form",
      name: "SampleForm",
      component: () => import("@/views/sample/form/index.vue"),
      meta: { title: "示例 · 表单录入", roles: ALL_ROLES }
    },
    {
      path: "/sample/timeline",
      name: "SampleTimeline",
      component: () => import("@/views/sample/timeline/index.vue"),
      meta: { title: "示例 · 时间轴", roles: ALL_ROLES }
    },
    {
      path: "/sample/empty",
      name: "SampleEmpty",
      component: () => import("@/views/sample/empty/index.vue"),
      meta: { title: "示例 · 空态引导", roles: ALL_ROLES }
    }
  ]
};
