<template>
  <div class="borrow-flow biz-page">
    <!-- 工具栏：状态筛选 + 仅待我审批 -->
    <div class="section biz-card">
      <div class="toolbar">
        <el-select
          v-model="statusFilter"
          placeholder="全部状态"
          clearable
          style="width: 140px"
          @change="load"
        >
          <el-option label="待审批" value="pending" />
          <el-option label="已通过" value="approved" />
          <el-option label="已驳回" value="rejected" />
        </el-select>
        <el-checkbox v-model="onlyMine">仅看我可审批的</el-checkbox>
        <span class="toolbar-tip">
          审批规则：被借用策略所属版本的负责人（或管理员）审批；通过后将在目标分支按新时间实际创建借用策略。
        </span>
      </div>

      <!-- 电子流列表 -->
      <el-table v-loading="loading" :data="filteredFlows" style="width: 100%">
        <el-table-column prop="id" label="#" width="56" />
        <el-table-column label="策略（来源）" min-width="220">
          <template #default="{ row }">
            <div class="cell-main">{{ row.strategy_name }}</div>
            <div class="cell-sub">
              {{ row.source_version_name }}/{{ row.source_branch_name }} ·
              {{ row.template_name }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="原时间" width="90">
          <template #default="{ row }">{{ row.original_build_time }}</template>
        </el-table-column>
        <el-table-column prop="borrower_name" label="借用人" width="110" />
        <el-table-column label="借用至" min-width="180">
          <template #default="{ row }">
            <div class="cell-main">
              {{ row.target_version_name }}/{{ row.target_branch_name }}
            </div>
            <div class="cell-sub">新构建时间 {{ row.new_build_time }}</div>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="160">
          <template #default="{ row }">
            <span class="reason" :title="row.reason">{{
              row.reason || "-"
            }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">
              {{ BORROW_STATUS_TEXT[row.status as BorrowFlowItem["status"]] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="申请时间" width="150">
          <template #default="{ row }">
            {{ (row.created_at || "").replace("T", " ") }}
          </template>
        </el-table-column>
        <el-table-column label="审批" min-width="140">
          <template #default="{ row }">
            <template v-if="row.status !== 'pending'">
              <div class="cell-main">{{ row.approver_name || "-" }}</div>
              <div class="cell-sub">{{ row.handle_comment || "-" }}</div>
            </template>
            <span v-else class="cell-sub">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button
              type="info"
              link
              size="small"
              @click="openDetail(row as BorrowFlowItem)"
            >
              详情
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              @click="onCopy(row as BorrowFlowItem)"
            >
              复制
            </el-button>
            <template
              v-if="
                row.status === 'pending' && canApprove(row as BorrowFlowItem)
              "
            >
              <el-button
                type="success"
                link
                size="small"
                @click="onApprove(row as BorrowFlowItem)"
              >
                通过
              </el-button>
              <el-button
                type="danger"
                link
                size="small"
                @click="onReject(row as BorrowFlowItem)"
              >
                驳回
              </el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 电子流只读详情（列表「详情」按钮或 ?focus= 直达链接打开） -->
    <el-dialog v-model="detailVisible" title="借用电子流详情" width="560px">
      <el-descriptions v-if="detailFlow" :column="2" border size="small">
        <el-descriptions-item label="编号"
          >#{{ detailFlow.id }}</el-descriptions-item
        >
        <el-descriptions-item label="状态">
          <el-tag :type="statusTag(detailFlow.status)" size="small">
            {{ BORROW_STATUS_TEXT[detailFlow.status] }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="策略（来源）" :span="2">
          {{ detailFlow.strategy_name }}（{{
            detailFlow.source_version_name
          }}/{{ detailFlow.source_branch_name }} ·
          {{ detailFlow.template_name }}）
        </el-descriptions-item>
        <el-descriptions-item label="原构建时间">
          {{ detailFlow.original_build_time }}
        </el-descriptions-item>
        <el-descriptions-item label="借用人">
          {{ detailFlow.borrower_name }}
        </el-descriptions-item>
        <el-descriptions-item label="借用至">
          {{ detailFlow.target_version_name }}/{{
            detailFlow.target_branch_name
          }}
        </el-descriptions-item>
        <el-descriptions-item label="新构建时间">
          {{ detailFlow.new_build_time }}
        </el-descriptions-item>
        <el-descriptions-item label="借用原因" :span="2">
          {{ detailFlow.reason || "（未填写）" }}
        </el-descriptions-item>
        <el-descriptions-item label="申请时间" :span="2">
          {{ (detailFlow.created_at || "").replace("T", " ") }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="detailFlow.status !== 'pending'"
          :span="2"
          label="审批"
        >
          {{ detailFlow.approver_name || "-" }}
          {{ detailFlow.status === "approved" ? "通过" : "驳回"
          }}{{
            detailFlow.handle_comment ? `（${detailFlow.handle_comment}）` : ""
          }}
          {{ (detailFlow.handled_at || "").replace("T", " ") }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button
          type="primary"
          plain
          @click="detailFlow && onCopy(detailFlow)"
        >
          复制（含链接）
        </el-button>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// 借用审批页：借用电子流列表 + 复制（含直达链接）+ 通过/驳回（独立页面，与版本策略全景页不绑定）
import { computed, h, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  approveBorrowFlow,
  borrowFlowUrl,
  BORROW_STATUS_TEXT,
  formatBorrowFlowText,
  listBorrowFlows,
  rejectBorrowFlow,
  type BorrowFlowItem
} from "@/api/borrowFlow";
import { getCurrentUser } from "@/utils/business";
import { copyText } from "@/utils/clipboard";

defineOptions({ name: "BorrowFlowIndex" });

const currentUser = getCurrentUser();
const route = useRoute();

const loading = ref(false);
const flows = ref<BorrowFlowItem[]>([]);
const statusFilter = ref<BorrowFlowItem["status"] | undefined>(undefined);
const onlyMine = ref(false);
// 直达链接打开的只读详情
const detailVisible = ref(false);
const detailFlow = ref<BorrowFlowItem | null>(null);

/** 审批权限：admin 全部；pm 仅来源版本为自己的电子流 */
function canApprove(flow: BorrowFlowItem): boolean {
  if (currentUser?.role === "admin") return true;
  return (
    currentUser?.role === "pm" &&
    currentUser?.bound_version_id === flow.source_version_id
  );
}

const filteredFlows = computed(() =>
  onlyMine.value ? flows.value.filter(f => canApprove(f)) : flows.value
);

async function load() {
  loading.value = true;
  try {
    flows.value = await listBorrowFlows(statusFilter.value);
  } finally {
    loading.value = false;
  }
}

function statusTag(status: BorrowFlowItem["status"]) {
  return status === "pending"
    ? "warning"
    : status === "approved"
      ? "success"
      : "danger";
}

/** 复制电子流内容为纯文本（含可直达该条的审批链接），便于粘贴发给审核人员快速定位 */
async function onCopy(flow: BorrowFlowItem) {
  const text = formatBorrowFlowText(flow, borrowFlowUrl(flow.id));
  // 统一走带降级与假成功防护的 copyText（与 report 两页同款）
  const copied = await copyText(text);
  if (copied) {
    ElMessage.success("电子流内容（含审批链接）已复制到剪贴板");
    return;
  }
  // 复制被浏览器策略拦截时降级为手动复制弹框；用 VNode 文本节点渲染，
  // 杜绝 dangerouslyUseHTMLString 直插他人输入（reason/审批意见）的存储型 XSS
  ElMessageBox.alert(
    h("pre", { style: "white-space:pre-wrap;margin:0" }, text),
    "电子流内容（请手动复制）"
  );
}

async function onApprove(flow: BorrowFlowItem) {
  await ElMessageBox.confirm(
    `通过后将立即在 ${flow.target_version_name}/${flow.target_branch_name} 按新时间 ${flow.new_build_time} 创建借用策略（若与目标版本既有安排冲突将无法通过）`,
    "通过借用申请",
    { type: "warning", confirmButtonText: "确认通过", cancelButtonText: "取消" }
  );
  await approveBorrowFlow(flow.id);
  ElMessage.success("已通过并创建借用策略");
  await load();
}

async function onReject(flow: BorrowFlowItem) {
  const { value } = await ElMessageBox.prompt(
    "请填写驳回意见（必填）",
    "驳回借用申请",
    {
      type: "warning",
      confirmButtonText: "确认驳回",
      cancelButtonText: "取消",
      inputValidator: (v: string) => (v && v.trim() ? true : "驳回意见不能为空")
    }
  );
  await rejectBorrowFlow(flow.id, value.trim());
  ElMessage.success("已驳回");
  await load();
}

/** 打开某条电子流的只读详情（供直达链接定位查看） */
function openDetail(flow: BorrowFlowItem) {
  detailFlow.value = flow;
  detailVisible.value = true;
}

onMounted(async () => {
  await load();
  // 支持 ?focus=<id> 直达：自动定位并打开对应电子流详情
  const focus = Number(route.query.focus);
  if (focus) {
    const target = flows.value.find(f => f.id === focus);
    if (target) openDetail(target);
    else ElMessage.warning(`未找到电子流 #${focus}`);
  }
});
</script>

<style scoped lang="scss">
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;

  .toolbar-tip {
    font-size: 12px;
    color: var(--el-text-color-placeholder);
  }
}

.cell-main {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.cell-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.reason {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
</style>
