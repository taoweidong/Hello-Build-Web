// 构建策略配置系统 —— 后端 API 契约类型定义
// 契约基准：docs/superpowers/specs/2026-08-08-build-strategy-web-design.md
// 统一响应结构 { code, message, data }；错误码 0 / 40101 / 40301 / 40901 / 40902 / 42201

/** 统一响应结构 */
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

/** 用户信息（含绑定版本元数据） */
export interface UserInfo {
  id: number;
  username: string;
  display_name: string;
  /** 角色：admin / pm / builder / tester / integrator */
  role: string;
  /** 是否启用（停用后不可登录） */
  is_active?: boolean;
  /** PM 绑定版本（仅 PM 角色存在） */
  bound_version_id?: number;
  bound_version_name?: string;
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
  push_mode: string;
  push_start_time?: string | null; // 推送固定时间 HH:MM（可空，空则结论后动态推导）
  enabled: boolean;
  /** 时间线计算结果（preview / strategies 返回） */
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

/** 每日执行轮次实例 */
export interface RoundItem {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  exec_date: string;
  push_start: string | null;
  push_end: string | null;
  build_start: string;
  build_end: string;
  smoke_start: string;
  smoke_end: string;
  analysis_start: string;
  analysis_end: string;
  /** 结论：pending / pass / fail */
  conclusion: string;
  conclusion_note?: string;
  /** 推送状态：pending / running / success / failed / skipped */
  push_status: string;
  /** 同步模式是否正式发布 */
  release_approved?: boolean;
}

/** 版本 */
export interface VersionItem {
  id: number;
  name: string;
  pm_user_id?: number | null;
  pm_name?: string;
  status: string;
  branches?: BranchItem[];
}

/** 分支 */
export interface BranchItem {
  id: number;
  version_id: number;
  name: string;
}

/** 策略模板 */
export interface TemplateItem {
  id: number;
  name: string;
  smoke_minutes: number;
  analysis_minutes: number;
  description?: string;
}

/** 全局关键配置 */
export interface GlobalConfig {
  build_minutes: number;
  push_minutes: number;
  sync_buffer_minutes: number;
}

/** 执行日志条目 */
export interface ExecutionLogItem {
  id: number;
  round_id: number;
  stage: string;
  event: string;
  detail?: string;
  at: string;
}

/** 策略变更日志条目 */
export interface ChangeLogItem {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  operator: string;
  field: string;
  old_value: string;
  new_value: string;
  at: string;
}

/** 管理操作日志条目 */
export interface AdminOpLogItem {
  id: number;
  operator: string;
  action: string;
  target_type: string;
  target_id?: number;
  detail?: string;
  at: string;
}

/** 登录安全日志条目 */
export interface SecurityLogItem {
  id: number;
  user_id?: number;
  username?: string;
  event: string;
  ip?: string;
  at: string;
}

/** 周视图单日 */
export interface WeeklyDay {
  date: string; // "YYYY-MM-DD"
  weekday: string; // 后端返回英文星期名（"%A"，如 "Monday"）
}

/** 周视图策略条目（后端扁平结构） */
export interface WeeklyStrategy {
  strategy_id: number;
  strategy_name: string;
  branch_id: number;
  branch_name: string;
  build_start_time: string; // "HH:mm"
  push_start_time?: string | null;
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

// ============ 验证报告 ============

/** 验证报告条目 */
export interface ReportItem {
  id: number;
  title: string;
  /** 版本/策略为文本快照（无外键关联，随报告保存） */
  version_name: string;
  strategy_name: string;
  /** 结论：pass / fail / risk */
  conclusion: string;
  /** 结论中文标签（后端计算） */
  conclusion_label: string;
  environment: string;
  summary: string;
  risks: string;
  remark: string;
  /** 状态：draft（草稿）/ published（已发布） */
  status: string;
  /** 状态中文标签（后端计算） */
  status_label: string;
  /** 作者账号（文本快照） */
  created_by_username: string;
  published_at?: string | null;
  publish_count: number;
  /** 是否为更新报告：发布次数大于 1（后端计算） */
  is_updated: boolean;
  /** 更新次数：发布次数减 1（后端计算） */
  update_count: number;
  created_at: string;
  updated_at: string;
}

/** 报告修改记录：创建/修改/发布全留痕，按时间倒序返回 */
export interface ReportRevisionItem {
  id: number;
  report_id: number;
  report_title: string;
  /** 动作：create（创建）/ update（修改）/ publish（发布） */
  action: string;
  /** 动作中文标签 */
  action_label: string;
  /** 修改字段（中文标签），如 标题 / 验证内容 */
  field_name: string;
  /** 修改前内容 */
  before_value: string;
  /** 修改后内容 */
  after_value: string;
  /** 操作人账号 */
  operator_username: string;
  created_at: string;
}

