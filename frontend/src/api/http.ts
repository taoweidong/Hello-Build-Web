// 业务 API 请求封装 —— Axios 实例
// 统一处理后端契约：响应 { code, message, data }；错误码语义见后端 errors.py。
// 失败路径统一 reject BizError（code/message/data/httpStatus），业务侧直接取 e.code / e.message。
import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";
import { getToken, removeToken } from "@/utils/auth";
import { businessUserKey } from "@/store/constants";

declare module "axios" {
  interface AxiosRequestConfig {
    /** 静默模式：失败不弹全局错误 toast（轮询/登出等后台请求用），业务侧仍收到 BizError */
    silent?: boolean;
  }
}

/** 统一业务错误：前端所有 catch 中拿到的是该对象而非原始 axios error */
export class BizError extends Error {
  code: number;
  data: unknown;
  httpStatus?: number;

  constructor(code: number, message: string, data?: unknown, httpStatus?: number) {
    super(message);
    this.name = "BizError";
    this.code = code;
    this.data = data;
    this.httpStatus = httpStatus;
  }
}

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

// 清理业务侧用户信息（与基座 token 一并清理，避免登录页读到旧身份）
function clearBusinessUser() {
  try {
    localStorage.removeItem(businessUserKey);
  } catch {
    /* 存储不可用时忽略 */
  }
}

// 响应拦截：统一解包 data 与错误处理
service.interceptors.response.use(
  (res: any) => {
    const d = res.data;
    // 契约约定成功时 code === 0
    if (d && d.code !== 0) {
      if (!res.config?.silent) {
        ElMessage.error(d.message || "请求失败");
      }
      return Promise.reject(new BizError(d.code, d.message || "请求失败", d.data));
    }
    // 成功直接返回 data 字段，方便业务层使用
    return d?.data;
  },
  (err: any) => {
    const silent = err?.config?.silent === true;
    // 兼容后端两种错误结构：{ detail: { code, message } } 或 { code, message }
    const body = err?.response?.data || {};
    const detail = body?.detail || body;
    const code = detail?.code;
    const message = detail?.message;
    if (code === 40100 || code === 40101) {
      // 未认证/登录态失效：清理并跳登录（静默请求同样跳转，登录态失效必须感知）
      removeToken();
      clearBusinessUser();
      // 保留部署子路径（pathname），避免子路径部署时硬编码 /#/login 断链
      window.location.href = `${window.location.pathname}#/login`;
      return Promise.reject(
        new BizError(code, message || "未认证", body?.data, err?.response?.status)
      );
    }
    if (!silent) {
      if (code === 40301) {
        ElMessage.error(message || "无权限执行该操作");
      } else if (code === 40901) {
        // 策略时间冲突：弹框展示冲突策略与重叠时段（前端专用弹框契约）
        ElMessageBox.alert(message || "策略时间冲突", "策略时间冲突", {
          type: "error",
          confirmButtonText: "知道了"
        });
      } else {
        ElMessage.error(message || "请求失败");
      }
    }
    return Promise.reject(
      // 网络层错误（断网/超时）无业务 code，兜底 -1；不用 0（信封契约中 0=成功）
      new BizError(code ?? -1, message || "请求失败", body?.data, err?.response?.status)
    );
  }
);

export default service;
