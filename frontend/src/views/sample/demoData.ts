// 示例菜单共用演示数据与纯函数（5 个占位页唯一的数据源）
// 约定：示例页不接后端接口，数据全部来自本文件；展示逻辑（筛选/分页）抽成
// 纯函数便于单测锁定，页面模板只做渲染。配色一律走 Element Plus 语义变量。

/** 表格演示行 */
export interface DemoUserRow {
  id: number;
  name: string;
  role: string;
  status: "active" | "disabled";
  /** 创建日期 "YYYY-MM-DD" */
  createdAt: string;
}

/** 时间轴演示条目 */
export interface DemoTimelineItem {
  time: string;
  title: string;
  /** el-timeline-item 的 type 语义值（不写死颜色） */
  type: "primary" | "success" | "warning" | "danger" | "info";
  note: string;
}

/** 概览统计卡（hint 为一行补充信息：趋势/占比，不写说明性长句） */
export interface DemoStatCard {
  label: string;
  value: string;
  hint: string;
}

/** 概览功能占位卡 */
export interface DemoFeatureCard {
  title: string;
  desc: string;
}

export const DEMO_STATS: DemoStatCard[] = [
  { label: "示例总量", value: "128", hint: "较昨日 +6" },
  { label: "进行中", value: "42", hint: "占比 33%" },
  { label: "已完成", value: "80", hint: "本周 +12" },
  { label: "异常", value: "6", hint: "待跟进" }
];

export const DEMO_FEATURES: DemoFeatureCard[] = [
  { title: "卡片网格", desc: "biz-card 网格 + 悬停态" },
  { title: "数据表格", desc: "筛选 + 表格 + 分页" },
  { title: "表单录入", desc: "校验规则与重置" },
  { title: "时间轴", desc: "纵向事件流水" },
  { title: "空态引导", desc: "el-empty + 主操作" },
  { title: "深浅色适配", desc: "语义变量自动适配" }
];

/** 表格演示数据（12 条，覆盖两状态与多个角色） */
export const DEMO_USERS: DemoUserRow[] = [
  {
    id: 1,
    name: "张伟",
    role: "admin",
    status: "active",
    createdAt: "2026-09-01"
  },
  {
    id: 2,
    name: "李娜",
    role: "pm",
    status: "active",
    createdAt: "2026-09-03"
  },
  {
    id: 3,
    name: "王强",
    role: "builder",
    status: "disabled",
    createdAt: "2026-09-05"
  },
  {
    id: 4,
    name: "刘洋",
    role: "tester",
    status: "active",
    createdAt: "2026-09-08"
  },
  {
    id: 5,
    name: "陈静",
    role: "integrator",
    status: "active",
    createdAt: "2026-09-10"
  },
  {
    id: 6,
    name: "杨光",
    role: "pm",
    status: "disabled",
    createdAt: "2026-09-12"
  },
  {
    id: 7,
    name: "赵敏",
    role: "builder",
    status: "active",
    createdAt: "2026-09-15"
  },
  {
    id: 8,
    name: "孙磊",
    role: "tester",
    status: "disabled",
    createdAt: "2026-09-18"
  },
  {
    id: 9,
    name: "周婷",
    role: "admin",
    status: "active",
    createdAt: "2026-09-21"
  },
  {
    id: 10,
    name: "吴刚",
    role: "pm",
    status: "active",
    createdAt: "2026-09-24"
  },
  {
    id: 11,
    name: "郑洁",
    role: "integrator",
    status: "disabled",
    createdAt: "2026-09-27"
  },
  {
    id: 12,
    name: "冯军",
    role: "builder",
    status: "active",
    createdAt: "2026-09-30"
  }
];

export const DEMO_TIMELINE: DemoTimelineItem[] = [
  {
    time: "09:00",
    title: "构建完成",
    type: "success",
    note: "release/1.8 · 耗时 8m"
  },
  {
    time: "10:30",
    title: "冒烟进行中",
    type: "primary",
    note: "用例 120/200"
  },
  {
    time: "11:45",
    title: "人工分析待办",
    type: "warning",
    note: "待张伟确认"
  },
  {
    time: "13:20",
    title: "推送失败告警",
    type: "danger",
    note: "目标分支被锁定"
  },
  {
    time: "15:00",
    title: "记录已归档",
    type: "info",
    note: "保留 30 天"
  }
];

/** 角色下拉选项（与表格数据同源，避免页面散落魔法值） */
export const DEMO_ROLE_OPTIONS = [...new Set(DEMO_USERS.map(u => u.role))];

export interface DemoUserFilter {
  /** 姓名关键字（空串 = 不过滤） */
  keyword: string;
  /** 角色（空串 = 全部） */
  role: string;
  /** 状态（空串 = 全部） */
  status: string;
}

/** 按关键字/角色/状态过滤（纯函数，spec 锁定） */
export function filterDemoUsers(
  rows: DemoUserRow[],
  filter: DemoUserFilter
): DemoUserRow[] {
  const kw = filter.keyword.trim();
  return rows.filter(
    r =>
      (!kw || r.name.includes(kw)) &&
      (!filter.role || r.role === filter.role) &&
      (!filter.status || r.status === filter.status)
  );
}

/** 页码从 1 起；越界页回退末页（纯函数，spec 锁定） */
export function paginateDemoUsers(
  rows: DemoUserRow[],
  page: number,
  pageSize: number
): { items: DemoUserRow[]; total: number } {
  const total = rows.length;
  const safeSize = Math.max(1, pageSize);
  const lastPage = Math.max(1, Math.ceil(total / safeSize));
  const safePage = Math.min(Math.max(1, page), lastPage);
  const start = (safePage - 1) * safeSize;
  return { items: rows.slice(start, start + safeSize), total };
}

/** 演示表单默认值 */
export interface DemoFormModel {
  name: string;
  role: string;
  email: string;
  notify: boolean;
  remark: string;
}

export const DEMO_FORM_INITIAL: DemoFormModel = {
  name: "",
  role: "",
  email: "",
  notify: true,
  remark: ""
};
