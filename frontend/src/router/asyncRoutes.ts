// 业务路由配置（asyncRoutes 风格）
// 复用 pure-admin-thin 角色路由机制：meta.roles 控制菜单渲染与路由可达性
// 页面×角色权限矩阵见设计文档 4.2
const Layout = () => import("@/layout/index.vue");

/** 全部角色 */
export const ALL_ROLES = ["admin", "pm", "builder", "tester", "integrator"];

/** PM 角色 */
export const PM_ROLE = ["pm"];

/** 管理员角色 */
export const ADMIN_ROLE = ["admin"];

/** 业务路由（作为静态路由合并进路由表，仍走基座 meta.roles 角色过滤） */
export const asyncRoutes = [
  {
    path: "/plan",
    name: "Plan",
    component: Layout,
    redirect: "/plan/index",
    meta: {
      icon: "ep/calendar",
      title: "版本计划",
      rank: 1
    },
    children: [
      {
        path: "/plan/index",
        name: "PlanIndex",
        component: () => import("@/views/plan/index.vue"),
        meta: {
          title: "版本计划",
          roles: ALL_ROLES
        }
      }
    ]
  },
  {
    path: "/execution",
    name: "Execution",
    component: Layout,
    redirect: "/execution/index",
    meta: {
      icon: "ep/odometer",
      title: "今日执行",
      rank: 2
    },
    children: [
      {
        path: "/execution/index",
        name: "ExecutionIndex",
        component: () => import("@/views/execution/index.vue"),
        meta: {
          title: "今日执行",
          roles: ALL_ROLES
        }
      }
    ]
  },
  {
    path: "/panorama",
    name: "Panorama",
    component: Layout,
    redirect: "/panorama/index",
    meta: {
      icon: "ep/grid",
      title: "策略全景",
      rank: 3
    },
    children: [
      {
        path: "/panorama/index",
        name: "PanoramaIndex",
        component: () => import("@/views/panorama/index.vue"),
        meta: {
          title: "策略全景",
          roles: ALL_ROLES
        }
      }
    ]
  },
  {
    path: "/strategy",
    name: "Strategy",
    component: Layout,
    redirect: "/strategy/index",
    meta: {
      icon: "ep/set-up",
      title: "策略配置",
      rank: 4
    },
    children: [
      {
        path: "/strategy/index",
        name: "StrategyIndex",
        component: () => import("@/views/strategy/index.vue"),
        meta: {
          title: "策略配置",
          roles: PM_ROLE
        }
      }
    ]
  },
  {
    path: "/system",
    name: "System",
    component: Layout,
    redirect: "/system/index",
    meta: {
      icon: "ep/setting",
      title: "系统管理",
      rank: 5
    },
    children: [
      {
        path: "/system/index",
        name: "SystemIndex",
        component: () => import("@/views/admin/index.vue"),
        meta: {
          title: "系统管理",
          roles: ADMIN_ROLE
        }
      }
    ]
  },
  {
    path: "/logs",
    name: "Logs",
    component: Layout,
    redirect: "/logs/index",
    meta: {
      icon: "ep/document",
      title: "日志中心",
      rank: 6
    },
    children: [
      {
        path: "/logs/index",
        name: "LogsIndex",
        component: () => import("@/views/logs/index.vue"),
        meta: {
          title: "日志中心",
          roles: ALL_ROLES
        }
      }
    ]
  }
];