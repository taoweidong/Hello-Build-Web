// 业务路由配置（asyncRoutes 风格）
// 复用 pure-admin-thin 角色路由机制：meta.roles 控制菜单渲染与路由可达性
// 页面×角色权限矩阵见设计文档 4.2
import { panoramaRoute } from "./panoramaRoutes";
import { sampleRoute } from "./sampleRoutes";

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
    path: "/weekly-report",
    name: "WeeklyReport",
    component: Layout,
    redirect: "/weekly-report/index",
    meta: {
      icon: "ep/data-analysis",
      title: "策略周报",
      rank: 6
    },
    children: [
      {
        path: "/weekly-report/index",
        name: "WeeklyReportIndex",
        component: () => import("@/views/weekly-report/index.vue"),
        meta: {
          title: "策略周报",
          roles: ALL_ROLES
        }
      }
    ]
  },
  {
    path: "/weekly-new",
    name: "WeeklyNew",
    component: Layout,
    redirect: "/weekly-new/index",
    meta: {
      icon: "ep/timer",
      title: "版本策略全景(New)",
      rank: 7
    },
    children: [
      {
        path: "/weekly-new/index",
        name: "WeeklyNewIndex",
        component: () => import("@/views/weekly-new/index.vue"),
        meta: {
          title: "版本策略全景(New)",
          roles: ALL_ROLES
        }
      }
    ]
  },
  {
    path: "/borrow-flow",
    name: "BorrowFlow",
    component: Layout,
    redirect: "/borrow-flow/index",
    meta: {
      icon: "ep/tickets",
      title: "借用审批",
      rank: 8
    },
    children: [
      {
        path: "/borrow-flow/index",
        name: "BorrowFlowIndex",
        component: () => import("@/views/borrow-flow/index.vue"),
        meta: {
          title: "借用审批",
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
      rank: 9
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
      rank: 10
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
      rank: 11
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
      rank: 12
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
  },
  {
    path: "/branch-config",
    name: "BranchConfig",
    component: Layout,
    redirect: "/branch-config/index",
    meta: {
      icon: "ep/connection",
      title: "分支配置",
      rank: 13
    },
    children: [
      {
        path: "/branch-config/index",
        name: "BranchConfigIndex",
        component: () => import("@/views/branch-config/index.vue"),
        meta: {
          title: "分支配置",
          roles: ALL_ROLES
        }
      }
    ]
  },
  {
    path: "/slot-booking",
    name: "SlotBooking",
    component: Layout,
    redirect: "/slot-booking/index",
    meta: {
      icon: "ep/alarm-clock",
      title: "时段抢占",
      rank: 14
    },
    children: [
      {
        path: "/slot-booking/index",
        name: "SlotBookingIndex",
        component: () => import("@/views/slot-booking/index.vue"),
        meta: {
          title: "时段抢占",
          roles: ALL_ROLES
        }
      }
    ]
  },
  {
    path: "/slot-config",
    name: "SlotConfig",
    component: Layout,
    redirect: "/slot-config/index",
    meta: {
      icon: "ep/list",
      title: "时段配置",
      rank: 15
    },
    children: [
      {
        path: "/slot-config/index",
        name: "SlotConfigIndex",
        component: () => import("@/views/slot-config/index.vue"),
        meta: {
          title: "时段配置",
          roles: ADMIN_ROLE
        }
      }
    ]
  },
  // 调度全景：5 个独立布局共用一套接口（定义与 redirect 接线见 panoramaRoutes.ts）
  panoramaRoute,
  // 示例菜单：5 个占位演示页（不接后端，验证菜单/路由/懒加载链路）
  sampleRoute
];
