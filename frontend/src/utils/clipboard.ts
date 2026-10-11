/**
 * 剪贴板复制：优先 async Clipboard API，降级 textarea + execCommand。
 *
 * 此前 report/index 与 report/detail 各自复制一份（2026-10-11 复评 L-8），
 * 且降级路径未检查 execCommand 返回值 —— 复制被浏览器策略拦截时仍提示
 * 「已复制」，用户粘贴拿到空内容（假成功）。
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // 降级：非 HTTPS 或浏览器限制时用临时 textarea 复制
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      // execCommand 返回 false 表示被浏览器拦截（常见于无用户手势调用）
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }
}
