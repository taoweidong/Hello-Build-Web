// 策略模板选项 API（端点归属 /api/admin 前缀，GET 对 admin+pm 开放）
// 2026-10-20 页面精简：系统管理页下线后，本模块仅保留策略配置页与
// 全景编辑弹窗消费的模板只读端点；版本/用户/配置/策略管理等写端点一并删除。
import http from "@/api/http";
import type { TemplateItem } from "@/api/types";

export const adminApi = {
  /** 策略模板列表（策略表单下拉选项数据源） */
  getTemplates: (): Promise<TemplateItem[]> => http.get("/admin/templates")
};
