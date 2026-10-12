/**
 * 报告截图 dataURL 纯函数工具（2026-10-13 第三轮质量优化自 report/detail.vue 抽取）。
 *
 * 发布报告前需估算截图体积（后端限 2MB），复制报告需把 dataURL 转 Blob 写入剪贴板；
 * 抽取为纯函数便于单测锁定边界（无逗号 dataURL、空 body、mime 缺失兜底）。
 */

/** base64 字节数估算（dataURL 主体 4 字符 ≈ 3 字节）；无逗号/空主体返回 0 */
export function base64Bytes(dataUrl: string): number {
  const body = dataUrl.split(",")[1] || "";
  return Math.floor(body.length * 0.75);
}

/**
 * dataURL → Blob（剪贴板写图片用）。
 * 边界：无逗号（无主体）或空主体时返回空 Blob 而不抛异常；mime 解析失败兜底 image/png。
 */
export function dataUrlToBlob(dataUrl: string): Blob {
  const commaIdx = dataUrl.indexOf(",");
  const head = commaIdx >= 0 ? dataUrl.slice(0, commaIdx) : dataUrl;
  const body = commaIdx >= 0 ? dataUrl.slice(commaIdx + 1) : "";
  const mime = head.match(/data:(.*?);/)?.[1] || "image/png";
  const bin = body ? atob(body) : "";
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}
