/**
 * 过期响应守卫（R5-F4，第五轮质量修复）。
 *
 * 「seq 守卫」范式的共用小工具：panorama 数据中枢（useScheduleData）与
 * useWeeklyPanorama（weeklySeq）各自内联了同款三行逻辑，但 branch-config /
 * slot-booking / RecordsPanel / borrow-flow / logs 等页面的加载函数一直裸奔——
 * 快速切换筛选/翻页/分支时，旧请求晚归会覆盖新状态的视图（错配数据）。
 *
 * 用法：
 * ```ts
 * const guard = createSeqGuard();
 * async function load() {
 *   const token = guard.next();          // 发起时取新序号
 *   const data = await fetchSomething(); // 网络往返
 *   if (!guard.isCurrent(token)) return; // 迟到响应直接丢弃
 *   items.value = data;                  // 仅最新请求可写响应式状态
 * }
 * ```
 *
 * 纯内存序号，无副作用；每个独立加载域各建一个实例（勿跨域共享）。
 */
export interface SeqGuard {
  /** 发起一次新请求：序号自增并返回本次令牌 */
  next: () => number;
  /** 令牌是否仍为最新（false = 已被更晚的请求取代，应丢弃响应） */
  isCurrent: (token: number) => boolean;
}

export function createSeqGuard(): SeqGuard {
  let seq = 0;
  return {
    next: () => ++seq,
    isCurrent: (token: number) => token === seq
  };
}
