// 布局组件级测试共用挂载助手
// 目的：5 个布局 spec 只写「本布局的断言」；装配细节（API mock 默认值 /
// memory router / 全局 stub / 用户注入）收敛在此，避免五个文件各抄一遍。
//
// 注意：vi.mock 不放在本文件——各 spec 顶部自行 mock 四个数据源模块，
// 与 composables/__tests__/useWeeklyPanorama.spec.ts 的既有风格保持一致。
import { mount, flushPromises } from "@vue/test-utils";
import { vi } from "vitest";
import type { Component } from "vue";
import type { DOMWrapper } from "@vue/test-utils";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { businessUserKey } from "@/store/constants";
import {
  PANORAMA_LAYOUTS,
  resolveEntryLayout
} from "../shared/panoramaLayouts";

/** 测试用户：id=7 与夹具 borrowFlow.borrower_id 对齐，mine 判定可复现 */
export const TEST_USER = {
  id: 7,
  username: "u",
  role: "admin",
  bound_version_id: 1
};

/** 注入登录用户（getCurrentUser 读 localStorage） */
export function setTestUser() {
  localStorage.setItem(businessUserKey, JSON.stringify(TEST_USER));
}

/**
 * 只含 /panorama 相关路由的 memory router。
 * /panorama 的 redirect 复用生产同一个 resolveEntryLayout——
 * 深链优先级在真实路由行为里被验证，而不是在测试里另抄一份规则。
 */
export async function makePanoramaRouter(): Promise<Router> {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: "/panorama",
        redirect: (to: { query: Record<string, unknown> }) =>
          `/panorama/${resolveEntryLayout(to.query)}`
      },
      ...PANORAMA_LAYOUTS.map(l => ({
        path: l.path as string,
        component: { template: "<div />" }
      })),
      { path: "/:pathMatch(.*)*", component: { template: "<div />" } }
    ]
  });
}

/**
 * 打开行内「更多」下拉并返回菜单元素（ul.el-dropdown-menu）。
 * EventActionMenu 行内最多常驻 2 个操作，其余经 el-dropdown 收纳。
 * 两个坑：① 菜单隐藏态也常驻 DOM，不能按文档序 querySelector 取第一个，
 * 必须用触发按钮的 aria-controls 精确定位本行那份；
 * ② el-tooltip 的 show-after 走 setTimeout，spec 冻结了定时器，
 * 点击后必须 advanceTimersByTime 才会真正展开。
 */
export async function openMoreMenu(
  row: DOMWrapper<Element>
): Promise<HTMLElement> {
  const trigger = row.findAll("button").find(b => b.text().includes("更多"))!;
  await trigger.trigger("click");
  vi.advanceTimersByTime(50);
  await flushPromises();
  const menu = document.getElementById(
    trigger.attributes("aria-controls")!
  ) as HTMLElement | null;
  if (!menu) throw new Error("「更多」下拉未找到");
  return menu;
}

/**
 * 挂载布局组件（直接挂组件，经 router 插件提供 useRoute/useRouter）。
 * 调用方需在 beforeEach 里 setTestUser + 设置四个 API mock 的返回值。
 *
 * @param route 挂载时的当前路由（含 query，如 /panorama/timeline?date=...）
 */
export async function mountLayout(component: Component, route: string) {
  const router = await makePanoramaRouter();
  await router.push(route);
  await router.isReady();
  const wrapper = mount(component, {
    global: {
      plugins: [router],
      // 离线图标组件由 main.ts 全局注册，测试环境不存在；空 stub 避免解析告警
      stubs: {
        IconifyIconOffline: true,
        // ScheduleDialogs 内的子弹窗（WeeklyNewStrategyEditDialog 等）走项目
        // 组件自动导入（unplugin-vue-components），vitest 无该 resolver，挂在前端会
        // 解析失败；本批布局 spec 只测布局自身渲染与筛选，弹窗不作断言，置空 stub
        ScheduleDialogs: true
      }
    }
  });
  await flushPromises();
  return { wrapper, router };
}
