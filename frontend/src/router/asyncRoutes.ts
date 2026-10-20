// 业务路由配置（asyncRoutes 风格）
// 复用 pure-admin-thin 角色路由机制：meta.roles 控制菜单渲染与路由可达性
//
// 2026-10-20 页面精简：业务页面收敛为 2 个典型页面——
// 调度全景（/panorama，复杂展示型，5 布局共用一套数据中枢）与
// 策略配置（/strategy，标准 CRUD 写路径型）。
// 原策略周报 / 版本策略全景(New) / 借用审批 / 验证报告 / 系统管理 /
// 日志中心 / 分支配置 / 时段抢占 / 时段配置 / 示例菜单已整体下线，
// 其核心能力（借用审批 / 抢占释放 / 改期）已内嵌为全景域行内动作。
import { panoramaRoute } from "./panoramaRoutes";

const Layout = () => import("@/layout/index.vue");

/** PM 角色（策略配置页仅 PM 可见） */
export const PM_ROLE = ["pm"];

/** 业务路由（作为静态路由合并进路由表，仍走基座 meta.roles 角色过滤） */
export const asyncRoutes = [
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
  // 调度全景：5 个布局共用一套接口（定义与 redirect 接线见 panoramaRoutes.ts）
  panoramaRoute
];
