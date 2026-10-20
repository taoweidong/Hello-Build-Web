<script setup lang="ts">
// 首页：业务功能入口卡片（2026-10-20 页面精简后仅保留 2 个典型页面入口）
import { computed } from "vue";
import { useRouter } from "vue-router";
import { getCurrentUser } from "@/utils/business";

defineOptions({ name: "Welcome" });

const router = useRouter();

const user = getCurrentUser();

/** 策略配置仅 PM 可见（与路由 meta.roles 口径一致） */
const entries = computed(() => {
  const list = [
    {
      title: "调度全景",
      desc: "策略 / 抢占 / 借用三源合一的调度总览，五种布局任意切换",
      path: "/panorama"
    }
  ];
  if (user?.role === "pm") {
    list.push({
      title: "策略配置",
      desc: "维护本版本分支的每日构建策略：构建 → 冒烟 → 分析 → 推送",
      path: "/strategy/index"
    });
  }
  return list;
});
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
