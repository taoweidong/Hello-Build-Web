// 业务 API 请求封装 —— Axios 实例
// 统一处理后端契约：响应 { code, message, data }；错误码 0/40101/40301/40901/40902/42201
// 401 跳登录 · 403 提示 · 40901 冲突弹框 · 40902 结论重复提示
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";
import { getToken, removeToken } from "@/utils/auth";

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 15000
});

// 请求拦截：附加 Bearer Token
service.interceptors.request.use(config => {
  const token = getToken()?.accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：统一解包 data 与错误处理
service.interceptors.response.use(
  (res: any) => {
    const d = res.data;
    // 契约约定成功时 code === 0
    if (d && d.code !== 0) {
      ElMessage.error(d.message || "请求失败");
      return Promise.reject(d);
    }
    // 成功直接返回 data 字段，方便业务层使用
    return d?.data;
  },
  (err: any) => {
    // 兼容后端两种错误结构：{ detail: { code, message } } 或 { code, message }
    const body = err?.response?.data || {};
    const detail = body?.detail || body;
    const code = detail?.code;
    if (code === 40101) {
      // 令牌失效/未登录：清理并跳登录
      removeToken();
      // 记录当前路径，登录后可返回（基座登录后跳首页，此处仅简单跳登录）
      window.location.href = "/#/login";
    } else if (code === 40301) {
      ElMessage.error("无权限执行该操作");
    } else if (code === 40901) {
      // 策略时间冲突：弹框展示冲突策略与重叠时段
      ElMessageBox.alert(detail?.message || "策略时间冲突", "策略时间冲突", {
        type: "error",
        confirmButtonText: "知道了"
      });
    } else if (code === 40902) {
      ElMessage.error(detail?.message || "结论已录入，请查看现有结论");
    } else {
      ElMessage.error(detail?.message || "请求失败");
    }
    return Promise.reject(err);
  }
);

export default service;