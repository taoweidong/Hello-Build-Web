// 借用审批页组件级回归：状态筛选必须含 cancelled（R4-F13/F-L8）
// 缺陷：撤销功能（P2-R1）上线后筛选项漏配，撤销过的申请无法筛选定位。
// 文案唯一来源 constants.borrowStatusMeta，选项集合与后端 BorrowFlow.status 值域对齐。
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { ElOption } from "element-plus";

vi.mock("@/api/borrowFlow", () => ({
  listBorrowFlows: vi.fn(async () => []),
  approveBorrowFlow: vi.fn(),
  rejectBorrowFlow: vi.fn(),
  borrowFlowUrl: (id: number) => `#/borrow-flow?focus=${id}`
}));
// 页面只用到 useRoute（?focus= 深链定位）；mock 掉避免拉起真实 router
vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }));

import BorrowFlowIndex from "../index.vue";
import { borrowStatusMeta } from "@/views/constants";

describe("borrow-flow 状态筛选选项（R4-F13/F-L8）", () => {
  it("含 待审批/已通过/已驳回/已撤销 四项，文案取 borrowStatusMeta 唯一来源", async () => {
    const wrapper = mount(BorrowFlowIndex, {
      global: { stubs: { IconifyIconOffline: true } }
    });
    await flushPromises();

    const options = wrapper.findAllComponents(ElOption);
    const byValue = new Map(
      options.map(o => [o.props("value") as string, o.props("label") as string])
    );
    for (const status of ["pending", "approved", "rejected", "cancelled"]) {
      expect(byValue.has(status), `缺少筛选项 ${status}`).toBe(true);
      expect(byValue.get(status)).toBe(borrowStatusMeta(status).text);
    }
    // 撤销项文案锁定（防止绕过 constants 复制措辞）
    expect(byValue.get("cancelled")).toBe("已撤销");
    wrapper.unmount();
  });
});
