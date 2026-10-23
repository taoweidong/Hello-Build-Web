// 策略表单实时预览：防抖 + 过期响应守卫（strategy 页与 StrategyEditDialog 两入口共用；
// 2026-10-20 页面精简后 admin 策略 Tab 已随系统管理页下线）
import { onScopeDispose, shallowRef } from "vue";
import {
  previewStrategy,
  type PreviewResult,
  type StrategyForm
} from "@/api/strategy";

/** 编辑态透传 id，预览时后端据此排除被编辑策略自身，避免自冲突误报 */
export type StrategyPreviewForm = StrategyForm & { id?: number };

export function useStrategyPreview(
  getForm: () => StrategyPreviewForm | null,
  debounceMs = 400
) {
  const preview = shallowRef<PreviewResult | null>(null);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let seq = 0;

  /** 表单变化后调度防抖预览；分支/模板/时间未选齐时跳过 */
  function schedule() {
    const form = getForm();
    if (!form?.branch_id || !form?.template_id || !form?.build_start_time)
      return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(run, debounceMs);
  }

  async function run() {
    const form = getForm();
    if (!form?.branch_id || !form?.template_id) return;
    const cur = ++seq;
    try {
      const res = await previewStrategy({
        ...form,
        push_start_time: form.push_start_time || null
      });
      if (cur !== seq) return; // 过期响应丢弃
      preview.value = res;
    } catch {
      if (cur !== seq) return;
      preview.value = null;
    }
  }

  /** 清空预览并作废在途响应（关闭弹窗/切换编辑对象时调用） */
  function reset() {
    if (timer) clearTimeout(timer);
    timer = null;
    seq++;
    preview.value = null;
  }

  onScopeDispose(() => {
    if (timer) clearTimeout(timer);
  });

  return { preview, schedule, run, reset };
}
