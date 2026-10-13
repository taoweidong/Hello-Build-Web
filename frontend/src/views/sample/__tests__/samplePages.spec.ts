// 示例菜单 5 个占位页的挂载冒烟：验证「组件可挂载 + 关键内容渲染」
// 背景教训（分支配置页）：新增页面必须有挂载级用例锁「数据加载有触发点」——
// 示例页无异步加载，冒烟重点是模板渲染与纯函数在组件里的接线是否正确。
import { describe, expect, it } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import SampleOverview from "../overview/index.vue";
import SampleTable from "../table/index.vue";
import SampleForm from "../form/index.vue";
import SampleTimeline from "../timeline/index.vue";
import SampleEmpty from "../empty/index.vue";
import {
  DEMO_FEATURES,
  DEMO_STATS,
  DEMO_TIMELINE,
  DEMO_USERS
} from "../demoData";

describe("示例页挂载冒烟", () => {
  it("概览页渲染统计卡与功能卡", () => {
    const wrapper = mount(SampleOverview);
    expect(wrapper.findAll(".stat-card")).toHaveLength(DEMO_STATS.length);
    expect(wrapper.findAll(".feature-card")).toHaveLength(DEMO_FEATURES.length);
  });

  it("表格页挂载即渲染全量首页，筛选生效、重置复原", async () => {
    const wrapper = mount(SampleTable);
    expect(wrapper.findAll(".el-table__body-wrapper tbody tr")).toHaveLength(5);
    expect(wrapper.text()).toContain(`共 ${DEMO_USERS.length} 条`);

    await wrapper.find(".el-input__inner").setValue("张");
    await flushPromises();
    expect(wrapper.text()).toContain("共 1 条");
    expect(wrapper.text()).toContain("张伟");

    const resetBtn = wrapper.findAll("button").find(b => b.text() === "重置");
    await resetBtn!.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain(`共 ${DEMO_USERS.length} 条`);
  });

  it("表单页渲染五个字段并支持重置", async () => {
    const wrapper = mount(SampleForm);
    // 名称 / 角色 / 邮箱 / 接收通知 / 备注 五个表单项
    expect(wrapper.findAll(".el-form-item").length).toBeGreaterThanOrEqual(5);
    const nameInput = wrapper.find("input[type=text]");
    await nameInput.setValue("示例名");
    expect((nameInput.element as HTMLInputElement).value).toBe("示例名");
    const resetBtn = wrapper.findAll("button").find(b => b.text() === "重置")!;
    await resetBtn.trigger("click");
    await flushPromises();
    // 重置回初始空值
    expect((nameInput.element as HTMLInputElement).value).toBe("");
  });

  it("时间轴页条目数与夹具一致", () => {
    const wrapper = mount(SampleTimeline);
    expect(wrapper.findAll(".el-timeline-item")).toHaveLength(
      DEMO_TIMELINE.length
    );
  });

  it("空态页渲染 el-empty", () => {
    const wrapper = mount(SampleEmpty);
    expect(wrapper.find(".el-empty__description").text()).toContain(
      "暂无示例数据"
    );
  });
});
