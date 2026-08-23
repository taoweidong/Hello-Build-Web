<template>
  <el-table :data="rows" size="small" border>
    <el-table-column label="工程名" prop="project_name" min-width="140" />
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag v-if="row.instance" :type="statusType(row.instance.status)" size="small">
          {{ statusLabel(row.instance.status) }}
        </el-tag>
        <el-tag v-else type="info" size="small">未启动</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="PID" width="90">
      <template #default="{ row }">{{ row.instance?.pid ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="启动时间" width="170">
      <template #default="{ row }">{{ row.instance?.started_at ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="停止时间" width="170">
      <template #default="{ row }">{{ row.instance?.stopped_at ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="最近心跳" width="170">
      <template #default="{ row }">{{ row.instance?.last_heartbeat_at ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="日志尾部" min-width="200" show-overflow-tooltip>
      <template #default="{ row }">{{ row.instance?.log_tail ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <el-button
          size="small"
          text
          type="success"
          :disabled="myRole === 'VIEWER' || row.instance?.status === 'RUNNING' || row.instance?.status === 'STARTING' || startingId === row.branch_project_id"
          :loading="startingId === row.branch_project_id"
          @click="$emit('start', row.branch_project_id)"
        >
          启动
        </el-button>
        <el-button
          size="small"
          text
          type="warning"
          :disabled="myRole === 'VIEWER' || !row.instance || row.instance.status === 'STOPPED' || stoppingId === row.branch_project_id"
          :loading="stoppingId === row.branch_project_id"
          @click="$emit('stop', row.branch_project_id)"
        >
          停止
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { BranchRole, InstanceRow, InstanceStatus } from "@/api/branchConfig";

defineProps<{
  rows: InstanceRow[];
  myRole: BranchRole;
  startingId: number | null;
  stoppingId: number | null;
}>();

defineEmits<{
  (e: "start", bpId: number): void;
  (e: "stop", bpId: number): void;
}>();

/** 实例状态文案 */
const STATUS_LABEL: Record<InstanceStatus, string> = {
  STARTING: "启动中",
  RUNNING: "运行中",
  STOPPED: "已停止",
  ERROR: "异常"
};

/** 实例状态 tag 类型 */
const STATUS_TYPE: Record<InstanceStatus, "primary" | "success" | "info" | "danger"> = {
  STARTING: "primary",
  RUNNING: "success",
  STOPPED: "info",
  ERROR: "danger"
};

function statusLabel(s: InstanceStatus): string {
  return STATUS_LABEL[s] ?? s;
}

function statusType(s: InstanceStatus): "primary" | "success" | "info" | "danger" {
  return STATUS_TYPE[s] ?? "info";
}
</script>