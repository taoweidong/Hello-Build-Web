<script setup lang="ts">
// 首页：业务功能入口卡片（替换模板占位页）
import { useRouter } from "vue-router";

defineOptions({ name: "Welcome" });

const router = useRouter();

const entries = [
  {
    title: "版本全景",
    desc: "全部版本 · 分支 · 策略甘特总览",
    path: "/version-view/index"
  },
  {
    title: "版本计划",
    desc: "按日查看 构建 → 冒烟 → 分析 → 推送 排布",
    path: "/plan/index"
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
    <p class="sub">管理版本/分支的每日构建策略：构建 → 冒烟 → 人工分析 → 推送</p>
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
  /* 布局 .main-content 已提供 24px 外边距，此处不再叠加 */
}
.title {
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}
.sub {
  color: var(--el-text-color-secondary);
  margin-bottom: 20px;
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
  color: var(--el-text-color-primary);
  font-weight: 600;
  margin-bottom: 6px;
}
</style>
