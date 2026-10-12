<script setup lang="ts">
// 首页：业务功能入口卡片（替换模板占位页）
import { useRouter } from "vue-router";

defineOptions({ name: "Welcome" });

const router = useRouter();

const entries = [
  {
    title: "策略周报",
    desc: "周报看板：KPI / 分支负载 / 时段趋势 / 标签云",
    path: "/weekly-report/index"
  },
  {
    title: "版本策略全景(New)",
    desc: "时间点 × 周一~周日 调度全景，对外查看 / 对内维护 / 过期置灰",
    path: "/weekly-new/index"
  },
  {
    title: "借用审批",
    desc: "非本版本人员借用时段发起电子流，来源版本负责人审批",
    path: "/borrow-flow/index"
  },
  {
    title: "验证报告",
    desc: "冒烟验证结论与发布留痕",
    path: "/report/index"
  },
  {
    title: "时段抢占",
    desc: "冒烟测试时段预约与释放",
    path: "/slot-booking/index"
  }
];
</script>

<template>
  <div class="welcome">
    <h2 class="title">构建策略配置系统</h2>
    <p class="sub">
      管理版本/分支的每日构建策略：构建 → 冒烟 → 人工分析 → 推送
    </p>
    <div class="cards">
      <div
        v-for="e in entries"
        :key="e.path"
        class="card biz-card biz-clickable"
        @click="router.push(e.path)"
      >
        <div class="card-title">{{ e.title }}</div>
        <div class="card-desc biz-tip">{{ e.desc }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.welcome {
  /* 布局 .main-content 已提供 12px 外边距，此处不再叠加 */
}

.title {
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
}

.sub {
  margin-bottom: 20px;
  color: var(--el-text-color-secondary);
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.card {
  padding: 18px;
}

.card-title {
  margin-bottom: 6px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>
