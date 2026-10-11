<template>
  <div>
    <div class="panel-toolbar">
      <el-button
        type="primary"
        size="small"
        :disabled="myRole !== 'ADMIN'"
        @click="dialogVisible = true"
      >
        ＋ 添加工程
      </el-button>
    </div>
    <el-table :data="items" size="small" border>
      <el-table-column label="工程名" prop="project.name" min-width="140" />
      <el-table-column
        label="仓库地址"
        prop="project.repository_url"
        min-width="200"
        show-overflow-tooltip
      />
      <el-table-column label="启用" width="90">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? "已启用" : "已停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            text
            type="primary"
            :disabled="myRole !== 'ADMIN'"
            @click="emit('edit-config', row as BranchProjectItem)"
          >
            编辑参数
          </el-button>
          <el-button
            size="small"
            text
            type="success"
            :disabled="myRole === 'VIEWER'"
            @click="emit('start', row.id)"
          >
            启动
          </el-button>
          <el-button
            size="small"
            text
            type="warning"
            :disabled="myRole === 'VIEWER'"
            @click="emit('stop', row.id)"
          >
            停止
          </el-button>
          <el-button
            size="small"
            text
            type="danger"
            :disabled="myRole !== 'ADMIN'"
            @click="emit('remove', row.id)"
          >
            移除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="添加工程" width="420px">
      <el-select
        v-model="selectedProjectId"
        filterable
        placeholder="从工程库选择"
        style="width: 100%"
      >
        <el-option
          v-for="p in availableProjects"
          :key="p.id"
          :label="p.name"
          :value="p.id"
          :disabled="linkedIds.includes(p.id)"
        />
      </el-select>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="confirmAdd"
          >确定</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import type { BranchRole, BranchProjectItem } from "@/api/branchConfig";

// 子组件只声明一次 props：items 工程关联列表、myRole 当前分支角色、
// availableProjects 可选工程库、adding 添加请求进行中（由父组件持有 loading 状态）
const props = defineProps<{
  items: BranchProjectItem[];
  myRole: BranchRole;
  availableProjects: { id: number; name: string }[];
  adding: boolean;
}>();

// 事件映射语法（Vue 3.3+）：事件名 -> 参数元组
const emit = defineEmits<{
  add: [projectId: number];
  remove: [bpId: number];
  "edit-config": [bp: BranchProjectItem];
  start: [bpId: number];
  stop: [bpId: number];
}>();

const dialogVisible = ref(false);
const selectedProjectId = ref<number | null>(null);

/** 已关联工程 id 集合（弹窗中禁用，避免重复关联） */
const linkedIds = computed(() => props.items.map(i => i.project.id));

function confirmAdd() {
  if (!selectedProjectId.value) {
    ElMessage.warning("请选择工程");
    return;
  }
  emit("add", selectedProjectId.value);
  dialogVisible.value = false;
  selectedProjectId.value = null;
}
</script>
