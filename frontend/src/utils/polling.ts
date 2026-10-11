/**
 * 轮询退避策略：把「失败几次后等多久」从组件里抽成纯函数，便于单测锁定。
 *
 * 背景（2026-10-11 质量复评 M-6）：执行看板原为固定 30s setInterval，
 * 后端持续 500 时会每 30s 弹一次 ElMessage.error（拦截器无条件弹），
 * 空 catch 只挡得住 rejection、挡不住 toast，形成错误弹窗轰炸。
 *
 * 修复：失败按指数退避递增（30s→60s→120s→240s→300s 封顶），成功即重置；
 * 且仅首次失败提示，后续静默。
 */

/** 正常轮询间隔 */
export const POLL_BASE_MS = 30_000;
/** 退避上限（5 分钟），避免长时间不可见后再次请求过密 */
export const POLL_MAX_MS = 300_000;

/**
 * 计算下一次轮询间隔。
 *
 * @param consecutiveFailures 连续失败次数（0 表示上次成功）
 * @param baseMs 正常轮询间隔（默认 30s，实例轮询等高频场景可传更小值）
 * @param maxMs 退避上限
 * @returns 毫秒数，最小 baseMs，最大 maxMs
 */
export function pollDelay(
  consecutiveFailures: number,
  baseMs: number = POLL_BASE_MS,
  maxMs: number = POLL_MAX_MS
): number {
  if (!Number.isFinite(consecutiveFailures) || consecutiveFailures <= 0) {
    return baseMs;
  }
  const delay = baseMs * 2 ** Math.floor(consecutiveFailures);
  return Math.min(delay, maxMs);
}

/**
 * 是否应当提示用户。
 * 仅连续失败第一次提示，避免错误弹窗按秒轰炸。
 */
export function shouldNotify(consecutiveFailures: number): boolean {
  return consecutiveFailures === 0;
}
