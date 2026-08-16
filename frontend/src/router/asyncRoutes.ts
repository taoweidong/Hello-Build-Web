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
    path: "/weekly",
    name: "Weekly",
    component: Layout,
    redirect: "/weekly/index",
    meta: {
      icon: "ep/date",
      title: "周视图",
      rank: 2
    },
    children: [
      {
        path: "/weekly/index",
        name: "WeeklyIndex",
        component: () => import("@/views/weekly/index.vue"),
        meta: {
          title: "周视图",
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
      rank: 3
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
      rank: 4
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
    path: "/version-view",
    name: "VersionView",
    component: Layout,
    redirect: "/version-view/index",
    meta: {
      icon: "ep/trend-charts",
      title: "版本全景",
      rank: 5
    },
    children: [
      {
        path: "/version-view/index",
        name: "VersionViewIndex",
        component: () => import("@/views/versionView/index.vue"),
        meta: {
          title: "版本全景",
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
      rank: 6
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
    path: "/report",
    name: "Report",
    component: Layout,
    redirect: "/report/index",
    meta: {
      icon: "ep/notebook",
      title: "验证报告",
      rank: 7
    },
    children: [
      {
        path: "/report/index",
        name: "ReportIndex",
        component: () => import("@/views/report/index.vue"),
        meta: {
          title: "验证报告",
          roles: ALL_ROLES
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
      rank: 8
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
      rank: 9
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