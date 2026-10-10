<template>
  <div class="slot-config">
    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="模板管理" name="templates">
          <div class="panel-toolbar">
            <el-button type="primary" size="small" @click="openCreate"
              >＋ 新建时段</el-button
            >
          </div>
          <el-table v-loading="loading" :data="templates" size="small" border>
            <el-table-column label="标识色" width="70" align="center">
              <template #default="{ row }">
                <span class="color-dot" :style="{ background: row.color }" />
              </template>
            </el-table-column>
            <el-table-column
              label="时段名称"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column label="时段" width="130" align="center">
              <template #default="{ row }"
                >{{ row.start_time }} – {{ row.end_time }}</template
              >
            </el-table-column>
            <el-table-column label="适用星期" min-width="150">
              <template #default="{ row }">
                <template v-if="row.weekdays">
                  <el-tag
                    v-for="w in row.weekdays.split(',')"
                    :key="w"
                    size="small"
                    effect="plain"
                    class="wd-tag"
                  >
                    {{ weekdayLabel(w) }}
                  </el-tag>
                </template>
                <span v-else class="cell-muted">每天</span>
              </template>
            </el-table-column>
            <el-table-column label="生效范围" width="200" align="center">
              <template #default="{ row }">
                <span
                  v-if="row.effective_from || row.effective_to"
                  class="cell-normal"
                >
                  {{ row.effective_from ?? "…" }} ~
                  {{ row.effective_to ?? "…" }}
                </span>
                <span v-else class="cell-muted">长期有效</span>
              </template>
            </el-table-column>
            <el-table-column
              label="排序"
              prop="sort_order"
              width="70"
              align="center"
            />
            <el-table-column label="启用" width="80" align="center">
              <template #default="{ row }">
                <el-switch
                  :model-value="row.enabled"
                  size="small"
                  :loading="togglingId === row.id"
                  @change="toggleEnabled(row as SlotTemplateItem)"
                />
              </template>
            </el-table-column>
            <el-table-column
              label="操作"
              width="140"
              fixed="right"
              align="center"
            >
              <template #default="{ row }">
                <el-button
                  size="small"
                  text
                  type="primary"
                  @click="openEdit(row as SlotTemplateItem)"
                  >编辑</el-button
                >
                <el-button
                  size="small"
                  text
                  type="danger"
                  @click="handleDelete(row as SlotTemplateItem)"
                  >删除</el-button
                >
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="抢占记录" name="records">
          <RecordsPanel ref="recordsRef" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新建/编辑模板 -->
    <TemplateDialog
      v-model="dialogVisible"
      :editing="editing"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteSlotTemplate,
  getSlotTemplates,
  updateSlotTemplate,
  type SlotTemplateItem
} from "@/api/slotBooking";
import TemplateDialog from "./components/TemplateDialog.vue";
import RecordsPanel from "./components/RecordsPanel.vue";

defineOptions({ name: "SlotConfigIndex" });

const activeTab = ref("templates");
const loading = ref(false);
const templates = ref<SlotTemplateItem[]>([]);
const dialogVisible = ref(false);
const editing = ref<SlotTemplateItem | null>(null);
const togglingId = ref<number | null>(null);
const recordsRef = ref<InstanceType<typeof RecordsPanel>>();

const WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

function weekdayLabel(w: string) {
  return WEEKDAY_NAMES[Number(w) - 1] ?? w;
}

async function load() {
  loading.value = true;
  try {
    templates.value = await getSlotTemplates();
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editing.value = null;
  dialogVisible.value = true;
}

function openEdit(row: SlotTemplateItem) {
  editing.value = row;
  dialogVisible.value = true;
}

function onSaved(payload: { warnings: string[] }) {
  dialogVisible.value = false;
  ElMessage.success("时段模板已保存");
  if (payload.warnings.length) {
    ElMessageBox.alert(payload.warnings.join("；"), "存在重叠时段", {
      type: "warning",
      confirmButtonText: "知道了"
    });
  }
  load();
}

async function toggleEnabled(row: SlotTemplateItem) {
  togglingId.value = row.id;
  try {
    await updateSlotTemplate(row.id, { enabled: !row.enabled });
    row.enabled = !row.enabled;
    ElMessage.success(row.enabled ? "已启用" : "已停用");
  } catch {
    // 拦截器已提示
  } finally {
    togglingId.value = null;
  }
}

async function handleDelete(row: SlotTemplateItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除时段「${row.name}」吗？若该时段已有抢占记录，请改用停用。`,
      "删除确认",
      {
        type: "warning",
        confirmButtonText: "确定删除",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return;
  }
  try {
    await deleteSlotTemplate(row.id);
    ElMessage.success("时段模板已删除");
    load();
  } catch {
    // 40902 拦截等：拦截器已提示
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.slot-config {
  padding: 4px;
}

.panel-toolbar {
  margin-bottom: 10px;
}

.color-dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  vertical-align: middle;
}

.wd-tag {
  margin-right: 4px;
}

.cell-muted {
  color: var(--el-text-color-placeholder);
}

.cell-normal {
  color: var(--el-text-color-regular);
}
</style>
