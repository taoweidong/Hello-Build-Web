// 时段抢占 API 模块
// 契约：统一响应 { code, message, data }；错误码 40904 = 时段已被抢占（拦截器 ElMessage 提示）
import http from "@/api/http";

/** 时段模板 */
export interface SlotTemplateItem {
  id: number;
  name: string;
  /** "HH:MM" */
  start_time: string;
  end_time: string;
  /** "1,2,3,4,5"（1=周一…7=周日），空 = 每天 */
  weekdays: string;
  effective_from: string | null;
  effective_to: string | null;
  color: string;
  sort_order: number;
  enabled: boolean;
}

/** 抢占详情（日历芯片 / 释放响应） */
export interface BookingItem {
  id: number;
  // 过期不落库（后端惰性过期设计）：状态仅 reserved/released，过期由前端按日期置灰
  status: "reserved" | "released";
  user_name: string;
  purpose: string;
  version_id: number;
  version_name: string;
  branch_id: number;
  branch_name: string;
  is_mine: boolean;
  created_at: string;
}

/** 日历单日单时段条目 */
export interface CalendarDayCell {
  template_id: number;
  status: "available" | "reserved";
  booking: BookingItem | null;
}

/** 月历聚合响应：GET /slot-calendar */
export interface SlotCalendarResponse {
  month: string;
  horizon_days: number;
  templates: SlotTemplateItem[];
  /** key = "YYYY-MM-DD"，仅含存在适用模板的日期 */
  days: Record<string, CalendarDayCell[]>;
}

/** 模板保存响应：含同星期重叠告警 */
export interface SlotTemplateSaveResponse {
  template: SlotTemplateItem;
  warnings: string[];
}

/** 抢占记录列表行（我的抢占 / admin 记录） */
export interface BookingRow {
  id: number;
  date: string;
  template_id: number;
  template_name: string;
  start_time: string;
  end_time: string;
  status: BookingItem["status"];
  purpose: string;
  version_id: number;
  version_name: string;
  branch_id: number;
  branch_name: string;
  user_id: number;
  user_name: string;
  created_at: string;
  released_at: string | null;
  release_reason: string;
}

/** 分页包装 */
export interface PageData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** 抢占记录筛选参数 */
export interface BookingQuery {
  page?: number;
  page_size?: number;
  date_from?: string;
  date_to?: string;
  version_id?: number;
  branch_id?: number;
  user_id?: number;
  status?: BookingItem["status"];
}

// ---- 模板 ----
export function getSlotTemplates(): Promise<SlotTemplateItem[]> {
  return http.get("/slot-templates");
}

export function createSlotTemplate(
  data: Partial<SlotTemplateItem> & {
    name: string;
    start_time: string;
    end_time: string;
  }
): Promise<SlotTemplateSaveResponse> {
  return http.post("/slot-templates", data);
}

export function updateSlotTemplate(
  id: number,
  data: Partial<SlotTemplateItem>
): Promise<SlotTemplateSaveResponse> {
  return http.put(`/slot-templates/${id}`, data);
}

export function deleteSlotTemplate(id: number): Promise<void> {
  return http.delete(`/slot-templates/${id}`);
}

// ---- 日历 ----
export function getSlotCalendar(month: string): Promise<SlotCalendarResponse> {
  return http.get("/slot-calendar", { params: { month } });
}

// ---- 抢占 ----
export function createBooking(data: {
  date: string;
  template_id: number;
  purpose: string;
  version_id: number;
  branch_id: number;
}): Promise<BookingItem> {
  return http.post("/slot-bookings", data);
}

export function releaseBooking(
  id: number,
  releaseReason = ""
): Promise<BookingItem> {
  return http.post(`/slot-bookings/${id}/release`, {
    release_reason: releaseReason
  });
}

export function getMyBookings(
  page = 1,
  pageSize = 20
): Promise<PageData<BookingRow>> {
  return http.get("/slot-bookings/mine", {
    params: { page, page_size: pageSize }
  });
}

export function getSlotBookings(
  query: BookingQuery
): Promise<PageData<BookingRow>> {
  return http.get("/slot-bookings", { params: query });
}
