// 构建策略配置系统 —— 后端 API 契约类型定义
// 2026-10-20 页面精简：仅保留调度全景 + 策略配置两页所依赖的契约类型，
// 验证报告 / 执行轮次 / 各类日志 / 版本管理等已下线域的类型一并删除。
// 统一响应结构 { code, message, data }；错误码 0 / 40100 / 40301 / 40901 / 40902 / 42201

// ============ 字面量联合（与后端模型 choices 对齐，避免裸 string 比较散落各页） ============

/** 用户角色（User.ROLE_CHOICES） */
export type Role = "admin" | "pm" | "builder" | "tester" | "integrator";
/** 推送模式（Strategy.PUSH_MODE_CHOICES） */
export type PushMode = "normal" | "sync";

/** 用户信息（含绑定版本元数据） */
export interface UserInfo {
  id: number;
  username: string;
  display_name: string;
  /** 角色：admin / pm / builder / tester / integrator */
  role: Role;
  /** PM 绑定版本（仅 PM 角色存在；未绑定为 null——R7-F14 前类型未含 null） */
  bound_version_id?: number | null;
  bound_version_name?: string | null;
}

/** 登录结果 */
export interface LoginResult {
  token: string;
  user: UserInfo;
}

/** 时间线单个阶段区间 */
export interface TimelinePhase {
  start: string;
  end: string;
}

/** 一条策略按模板自动排布的完整时间线（绝对时间，可跨天） */
export interface Timeline {
  /** 推送（同步模式占用固定时段；正常模式为 null 或结论后动态） */
  push: TimelinePhase | null;
  build: TimelinePhase;
  smoke: TimelinePhase;
  analysis: TimelinePhase;
}

/** 策略条目 */
export interface StrategyItem {
  id: number;
  branch_id: number;
  branch_name: string;
  version_id: number;
  version_name?: string;
  template_id: number;
  template_name: string;
  name: string;
  build_start_time: string;
  push_mode: PushMode;
  push_start_time?: string | null; // 推送固定时间 HH:MM（可空，空则结论后动态推导）
  enabled: boolean;
  /** 时间线计算结果（仅 preview / plan 返回；/strategies 列表不含此字段，
   * R7-F14 前注释失实误导直取得 undefined） */
  timeline?: Timeline;
  /** 冲突详情（preview 返回时存在） */
  conflict?: ConflictInfo | null;
}

/** 冲突详情 */
export interface ConflictInfo {
  strategy_id?: number;
  strategy_name?: string;
  overlap_start?: string;
  overlap_end?: string;
  message?: string;
}

/** 策略模板 */
export interface TemplateItem {
  id: number;
  name: string;
  smoke_minutes: number;
  analysis_minutes: number;
  description?: string;
}

/** 周视图单日 */
export interface WeeklyDay {
  date: string; // "YYYY-MM-DD"
  weekday: string; // 中文星期名（周一~周日）
}

/** 周视图策略条目（后端扁平结构） */
export interface WeeklyStrategy {
  strategy_id: number;
  strategy_name: string;
  branch_id: number;
  branch_name: string;
  build_start_time: string; // "HH:mm"
  push_start_time?: string | null;
  push_mode: PushMode;
  template_name: string;
}

/** 周视图分支分组（仅 id/name，策略在顶层的 strategies 列表） */
export interface WeeklyBranch {
  branch_id: number;
  branch_name: string;
}

/** 周视图数据 */
export interface WeeklyData {
  week_start: string; // "YYYY-MM-DD"（周一）
  days: WeeklyDay[]; // 7 天
  version: { version_id: number; version_name: string } | null;
  versions: { version_id: number; version_name: string }[];
  branches: WeeklyBranch[];
  strategies: WeeklyStrategy[];
}
