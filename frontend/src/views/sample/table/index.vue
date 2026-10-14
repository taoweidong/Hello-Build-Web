<!-- 示例菜单 · 数据表格 /sample/table -->
<!-- 定位：占位演示页。展示 .biz-filter-bar 筛选栏 + el-table + 分页的列表页骨架 -->
<!-- 数据源 demoData.ts（不接后端）；筛选与分页逻辑是纯函数，已由 spec 锁定 -->
<!-- 紧凑口径：控件自带 placeholder，不再重复写「姓名/角色/状态」文字标签；
     总数只在卡片头出现一次，分页器不再重复 total -->
<template>
  <div class="biz-page">
    <div class="biz-filter-bar">
      <div class="biz-filter-left">
        <el-input
          v-model="filter.keyword"
          size="small"
          placeholder="姓名关键字"
          clearable
          style="width: 150px"
        />
        <el-select
          v-model="filter.role"
          size="small"
          clearable
          placeholder="全部角色"
          style="width: 120px"
        >
          <el-option v-for="r in roleOptions" :key="r" :label="r" :value="r" />
        </el-select>
        <el-select
          v-model="filter.status"
          size="small"
          clearable
          placeholder="全部状态"
          style="width: 110px"
        >
          <el-option label="启用" value="active" />
          <el-option label="停用" value="disabled" />
        </el-select>
      </div>
      <div class="biz-filter-right">
        <el-button size="small" @click="resetFilter">重置</el-button>
      </div>
    </div>

    <div class="biz-card biz-card-compact">
      <div class="biz-card-head">
        <span class="biz-card-title">示例用户列表</span>
        <span class="biz-sub">共 {{ filtered.length }} 条</span>
      </div>
      <el-table :data="paged.items" size="small">
        <el-table-column prop="id" label="ID" width="64" />
        <el-table-column prop="name" label="姓名" min-width="110">
          <template #default="{ row }">
            <span class="cell-strong">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="100" />
        <el-table-column label="状态" width="88">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.status === 'active' ? 'success' : 'info'"
              effect="plain"
            >
              {{ row.status === "active" ? "启用" : "停用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建日期" width="112" />
      </el-table>
      <el-empty
        v-if="!filtered.length"
        description="没有符合条件的示例数据"
        :image-size="80"
      />
      <el-pagination
        v-if="filtered.length"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        class="pager"
        layout="prev, pager, next, sizes"
        :total="filtered.length"
        :page-sizes="[10, 20]"
        size="small"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import {
  DEMO_ROLE_OPTIONS,
  DEMO_USERS,
  filterDemoUsers,
  paginateDemoUsers,
  type DemoUserFilter
} from "../demoData";

defineOptions({ name: "SampleTable" });

const roleOptions = DEMO_ROLE_OPTIONS;
const filter = reactive<DemoUserFilter>({
  keyword: "",
  role: "",
  status: ""
});
const page = ref(1);
const pageSize = ref(10);

const filtered = computed(() => filterDemoUsers(DEMO_USERS, filter));
const paged = computed(() =>
  paginateDemoUsers(filtered.value, page.value, pageSize.value)
);

// 筛选条件变化回第一页（分页越界由 paginateDemoUsers 兜底回末页）
watch(filter, () => {
  page.value = 1;
});

function resetFilter() {
  filter.keyword = "";
  filter.role = "";
  filter.status = "";
}
</script>

<style scoped lang="scss">
/* 主信息列（姓名）加粗，次要列保持常规字重 */
.cell-strong {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.pager {
  justify-content: flex-end;
  margin-top: 10px;
}
</style>
