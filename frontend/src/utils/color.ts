/**
 * 颜色工具：十六进制色转 rgba。
 *
 * 周报页深色主题需要把「分支配色（固定色板 hex）」派生出半透明 tint
 * （推送芯片底色、光晕、进度条亮段等），CSS 无法直接从 hex 计算透明度，
 * 故在此统一转换，避免各组件各写一份。
 */

/** 支持 #rgb / #rrggbb（不带 # 亦可）；非法输入回退为原值交由 CSS 兜底 */
export function normalizeHex(hex: string): string {
  const h = hex.trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(h)) {
    return `#${h
      .split("")
      .map(c => c + c)
      .join("")}`;
  }
  if (/^[0-9a-f]{6}$/i.test(h)) return `#${h}`;
  return hex;
}

/**
 * hex → rgba() 字符串。
 * @param hex  颜色（#rgb / #rrggbb）
 * @param alpha 透明度 0~1（越界时收敛到边界）
 */
export function hexToRgba(hex: string, alpha: number): string {
  const a = Math.min(1, Math.max(0, Number.isFinite(alpha) ? alpha : 1));
  const h = normalizeHex(hex).slice(1);
  if (h.length !== 6) return hex;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}
