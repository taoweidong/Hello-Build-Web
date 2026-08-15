<script setup lang="ts">
// 验证报告详情/编辑页：只读展示 / 编辑表单 / 截图发布 / 发布历史
// 权限：tester/builder 且作者可编辑发布；新建态天然为编辑态
import { ref, reactive, computed, onMounted, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import html2canvas from "html2canvas-pro";
import {
  getReport,
  createReport,
  updateReport,
  publishReport,
  getReportPublishes,
  type ReportForm
} from "@/api/report";
import { getStrategies } from "@/api/strategy";
import type { ReportItem, ReportPublishItem, StrategyItem } from "@/api/types";
import { getCurrentUser, formatTime } from "@/utils/business";

defineOptions({ name: "ReportDetail" });

const route = useRoute();
const router = useRouter();
const currentUser = getCurrentUser();

const MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024; // 2MB，与后端校验一致

// ---- 路由态 ----
const routeId = computed(() => String(route.params.id ?? ""));
const isNew = computed(() => routeId.value === "new");

// ---- 权限 ----
const canWrite = computed(
  () => currentUser?.role === "tester" || currentUser?.role === "builder"
);
function canEdit(row: ReportItem) {
  return canWrite.value && currentUser?.id === row.created_by_id;
}
const canEditCurrent = computed(() => (report.value ? canEdit(report.value) : false));

// ---- 数据 ----
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const report = ref<ReportItem | null>(null);
const publishes = ref<ReportPublishItem[]>([]);
const activePublish = ref<number>(0);
const cardWrapRef = ref<HTMLElement | null>(null);
const editing = ref(isNew.value); // 新建态初始为编辑态；详情默认只读

// ---- 版本/策略选项（从全量策略推导，与列表页一致）----
const allStrategies = ref<StrategyItem[]>([]);
const versionOptions = computed(() => {
  const map = new Map<number, string>();
  allStrategies.value.forEach(s => {
    if (s.version_id != null && !map.has(s.version_id)) {
      map.set(s.version_id, s.version_name || "");
    }
  });
  return Array.from(map, ([id, name]) => ({ id, name }));
});
const strategyOptions = computed(() =>
  allStrategies.value.filter(s => s.version_id === form.version_id)
);
function versionNameOf(id?: number | null) {
  return allStrategies.value.find(s => s.version_id === id)?.version_name || null;
}
function strategyNameOf(id?: number | null) {
  return allStrategies.value.find(s => s.id === id)?.name || null;
}
function onVersionChange() {
  form.strategy_id = null;
}

// ---- 表单 ----
const form = reactive<ReportForm>({
  title: "",
  version_id: null,
  strategy_id: null,
  conclusion: "pass",
  environment: "",
  summary: "",
  risks: "",
  remark: ""
});

function fillForm(r: ReportItem) {
  form.title = r.title;
  form.version_id = r.version_id ?? null;
  form.strategy_id = r.strategy_id ?? null;
  form.conclusion = r.conclusion;
  form.environment = r.environment;
  form.summary = r.summary;
  form.risks = r.risks;
  form.remark = r.remark;
}

function startEdit() {
  if (report.value) {
    fillForm(report.value);
    editing.value = true;
  }
}
function cancelEdit() {
  if (report.value) fillForm(report.value);
  editing.value = false;
}

// ---- 卡片数据源（编辑态实时预览，保证截图目标恒存在）----
const cardData = computed(() => {
  const base = report.value;
  if (editing.value || isNew.value) {
    return {
      title: form.title.trim() || "（未填写标题）",
      version_name: versionNameOf(form.version_id),
      strategy_name: strategyNameOf(form.strategy_id),
      conclusion: form.conclusion,
      status: base?.status || "draft",
      environment: form.environment,
      summary: form.summary,
      risks: form.risks,
      remark: form.remark,
      created_by_name:
        base?.created_by_name ||
        currentUser?.display_name ||
        currentUser?.username ||
        "",
      updated_at: base?.updated_at || null
    };
  }
  return {
    title: base?.title || "",
    version_name: base?.version_name || null,
    strategy_name: base?.strategy_name || null,
    conclusion: base?.conclusion || "",
    status: base?.status || "",
    environment: base?.environment || "",
    summary: base?.summary || "",
    risks: base?.risks || "",
    remark: base?.remark || "",
    created_by_name: base?.created_by_name || "",
    updated_at: base?.updated_at || null
  };
});

// ---- 徽章映射（与列表页一致）----
const conclusionMap: Record<string, { text: string; type: "success" | "danger" | "warning" | "info" }> = {
  pass: { text: "通过", type: "success" },
  fail: { text: "不通过", type: "danger" },
  risk: { text: "有风险", type: "warning" }
};
const statusMap: Record<string, { text: string; type: "info" | "success" }> = {
  draft: { text: "草稿", type: "info" },
  published: { text: "已发布", type: "success" }
};
function conclusionTag(c: string) {
  return conclusionMap[c] || { text: c, type: "info" as const };
}
function statusTag(s: string) {
  return statusMap[s] || { text: s, type: "info" as const };
}

// ---- 校验 ----
function validateForm(): boolean {
  if (!form.title.trim()) {
    ElMessage.warning("请填写报告标题");
    return false;
  }
  if (!form.conclusion) {
    ElMessage.warning("请选择验证结论");
    return false;
  }
  if (!form.summary.trim()) {
    ElMessage.warning("请填写验证内容");
    return false;
  }
  if (!!form.version_id !== !!form.strategy_id) {
    ElMessage.warning("版本与策略须同时选择或均不选择");
    return false;
  }
  return true;
}

function toPayload(): ReportForm {
  return {
    title: form.title.trim(),
    version_id: form.version_id || null,
    strategy_id: form.strategy_id || null,
    conclusion: form.conclusion,
    environment: form.environment.trim(),
    summary: form.summary.trim(),
    risks: form.risks.trim(),
    remark: form.remark.trim()
  };
}

// ---- 加载 ----
async function loadReport() {
  if (isNew.value) return;
  loading.value = true;
  try {
    const data = await getReport(Number(routeId.value));
    report.value = data;
    fillForm(data);
    // 深链接带 ?edit=1 且为作者时直达编辑态
    if (route.query.edit === "1" && canEdit(data)) {
      editing.value = true;
    }
  } catch (e: any) {
    const code = e?.response?.data?.code ?? e?.code;
    if (code === 40401) {
      ElMessage.error("报告不存在或已删除");
      router.replace("/report/index");
    }
  } finally {
    loading.value = false;
  }
}

async function loadPublishes() {
  if (isNew.value) {
    publishes.value = [];
    return;
  }
  if (!report.value) return;
  publishes.value = await getReportPublishes(report.value.id);
  if (publishes.value.length && !activePublish.value) {
    activePublish.value = publishes.value[0].id; // 默认展开最新一条
  }
}

// ---- 保存 ----
async function saveDraft(): Promise<ReportItem | null> {
  if (!validateForm()) return null;
  saving.value = true;
  try {
    if (isNew.value) {
      const saved = await createReport(toPayload());
      report.value = saved;
      // 带 ?edit=1 跳转，重建后 loadReport 会恢复编辑态
      await router.replace(`/report/detail/${saved.id}?edit=1`);
      ElMessage.success("报告已创建，可继续编辑或直接发布");
      await loadPublishes();
      return saved;
    }
    if (!report.value) return null;
    const saved = await updateReport(report.value.id, toPayload());
    report.value = saved;
    ElMessage.success("报告已保存");
    return saved;
  } finally {
    saving.value = false;
  }
}

// ---- 截图与发布 ----
async function captureCard(): Promise<string> {
  const el = cardWrapRef.value;
  if (!el) throw new Error("截图区域不存在");
  const canvas = await html2canvas(el, {
    scale: 2,
    backgroundColor: "#ffffff",
    useCORS: true,
    logging: false
  });
  return canvas.toDataURL("image/png");
}

/** base64 字节数估算（dataURL 主体 4 字符 ≈ 3 字节） */
function base64Bytes(dataUrl: string): number {
  const body = dataUrl.split(",")[1] || "";
  return Math.floor(body.length * 0.75);
}

async function onPublish() {
  if (!validateForm()) return;
  try {
    await ElMessageBox.confirm(
      "发布后将模拟推送至「构建通知群」，并记录当前报告页面截图。确认发布？",
      "发布报告",
      { type: "warning", confirmButtonText: "确认发布", cancelButtonText: "取消" }
    );
  } catch {
    return; // 用户取消
  }
  publishing.value = true;
  let savedReportId: number | null = null;
  try {
    if (isNew.value) {
      // 新建态：先建报告但不跳转，截图发布成功后再切路由，避免路由重建打断发布链路
      const saved = await createReport(toPayload());
      report.value = saved;
      savedReportId = saved.id;
    } else {
      if (!report.value) return;
      await updateReport(report.value.id, toPayload());
      savedReportId = report.value.id;
    }
    // 等卡片重渲染完成再截图
    await nextTick();
    await new Promise(resolve => setTimeout(resolve, 100));
    const screenshot = await captureCard();
    if (base64Bytes(screenshot) > MAX_SCREENSHOT_BYTES) {
      ElMessage.error("截图超过 2MB，请精简报告内容后重试");
      if (isNew.value && savedReportId) {
        await router.replace(`/report/detail/${savedReportId}?edit=1`);
      }
      return;
    }
    await publishReport(savedReportId, screenshot);
    ElMessage.success("发布成功，已模拟推送至构建通知群");
    if (isNew.value && savedReportId) {
      // 发布完成后跳转详情并转为只读展示，路由重建后由 loadReport 加载已发布状态
      await router.replace(`/report/detail/${savedReportId}`);
    } else {
      await loadReport();
      await loadPublishes();
      editing.value = false; // 编辑态发布完成后转为只读展示
    }
  } catch (e) {
    // 发布失败保留编辑态，允许重试；新建的草稿已落库，跳转编辑态继续
    console.error("[report-publish] 发布失败：", e);
    ElMessage.error("发布失败，请重试");
    if (isNew.value && savedReportId) {
      await router.replace(`/report/detail/${savedReportId}?edit=1`);
    }
  } finally {
    publishing.value = false;
  }
}

// ---- 复制链接 ----
const reportLink = computed(() =>
  `${window.location.origin}/#/report/detail/${routeId.value}`
);
async function copyLink() {
  try {
    await navigator.clipboard.writeText(reportLink.value);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = reportLink.value;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  ElMessage.success("链接已复制");
}

onMounted(async () => {
  await loadReport();
  await loadPublishes();
  try {
    allStrategies.value = await getStrategies();
  } catch {
    allStrategies.value = [];
  }
});
</script>

<template>
  <div class="report-detail" v-loading="loading">
    <!-- 顶部操作栏（非新建） -->
    <div v-if="!isNew && report" class="op-bar">
      <div class="op-left">
        <span class="op-title">报告 #{{ report.id }}</span>
      </div>
      <div class="op-right">
        <el-button @click="copyLink">复制链接</el-button>
        <el-button v-if="canEditCurrent && !editing" type="primary" @click="startEdit">编辑</el-button>
        <el-button v-if="canEditCurrent" type="success" :loading="publishing" @click="onPublish">发布</el-button>
      </div>
    </div>

    <!-- 报告卡片（恒存在，截图目标） -->
    <div
      v-if="report || editing"
      ref="cardWrapRef"
      class="section report-card-wrap"
    >
      <div class="report-card">
        <div class="card-head">
          <span class="card-title">{{ cardData.title }}</span>
          <span class="card-tags">
            <el-tag :type="conclusionTag(cardData.conclusion).type" size="small">
              {{ conclusionTag(cardData.conclusion).text }}
            </el-tag>
            <el-tag
              v-if="cardData.status"
              :type="statusTag(cardData.status).type"
              size="small"
            >
              {{ statusTag(cardData.status).text }}
            </el-tag>
          </span>
        </div>
        <div class="card-meta">
          <template v-if="cardData.version_name && cardData.strategy_name">
            关联策略：{{ cardData.version_name }} / {{ cardData.strategy_name }}
          </template>
          <span v-else>未关联策略</span>
        </div>
        <div class="card-body">
          <div v-if="cardData.environment" class="card-section">
            <span class="sec-label">验证环境</span>
            <span class="sec-text">{{ cardData.environment }}</span>
          </div>
          <div class="card-section">
            <span class="sec-label">验证内容</span>
            <p class="sec-text">{{ cardData.summary }}</p>
          </div>
          <div v-if="cardData.risks" class="card-section">
            <span class="sec-label">问题与风险</span>
            <p class="sec-text">{{ cardData.risks }}</p>
          </div>
          <div v-if="cardData.remark" class="card-section">
            <span class="sec-label">备注</span>
            <p class="sec-text">{{ cardData.remark }}</p>
          </div>
        </div>
        <div class="card-foot">
          <span>作者：{{ cardData.created_by_name }}</span>
          <span v-if="cardData.updated_at">
            更新于 {{ formatTime(cardData.updated_at, "YYYY-MM-DD HH:mm") }}
          </span>
        </div>
      </div>
    </div>

    <!-- 新建 / 编辑表单 -->
    <div v-if="editing" class="section">
      <div class="section-title">{{ isNew ? "新建验证报告" : "编辑报告内容" }}</div>
      <el-form :model="form" label-width="100px" class="report-form">
        <el-form-item label="报告标题" required>
          <el-input v-model="form.title" placeholder="例：27A 冒烟验证报告" style="width: 420px" />
        </el-form-item>
        <el-form-item label="关联版本">
          <el-select
            v-model="form.version_id"
            placeholder="可选"
            clearable
            style="width: 200px"
            @change="onVersionChange"
          >
            <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
          <span class="form-tip">版本与策略须同时选择或均不选择</span>
        </el-form-item>
        <el-form-item label="关联策略">
          <el-select
            v-model="form.strategy_id"
            placeholder="可选"
            clearable
            :disabled="!form.version_id"
            style="width: 280px"
          >
            <el-option v-for="s in strategyOptions" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="验证结论" required>
          <el-radio-group v-model="form.conclusion">
            <el-radio value="pass">通过</el-radio>
            <el-radio value="fail">不通过</el-radio>
            <el-radio value="risk">有风险</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="验证环境">
          <el-input
            v-model="form.environment"
            placeholder="例：测试环境 / 生产预发"
            style="width: 420px"
          />
        </el-form-item>
        <el-form-item label="验证内容" required>
          <el-input
            v-model="form.summary"
            type="textarea"
            :rows="4"
            placeholder="填写验证内容，将展示在报告卡片中"
            style="width: 560px"
          />
        </el-form-item>
        <el-form-item label="问题与风险">
          <el-input v-model="form.risks" type="textarea" :rows="3" placeholder="可选" style="width: 560px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="可选" style="width: 560px" />
        </el-form-item>
      </el-form>
      <div class="form-actions">
        <el-button type="primary" :loading="saving" @click="saveDraft">保存草稿</el-button>
        <el-button type="success" :loading="publishing" @click="onPublish">保存并发布</el-button>
        <el-button v-if="!isNew" @click="cancelEdit">取消</el-button>
      </div>
    </div>

    <!-- 发布历史（非新建） -->
    <div v-if="!isNew" class="section">
      <div class="section-title">发布历史（{{ publishes.length }}）</div>
      <el-empty
        v-if="publishes.length === 0"
        description="暂无发布记录"
        :image-size="60"
      />
      <el-collapse v-else v-model="activePublish" accordion class="pub-collapse">
        <el-collapse-item v-for="p in publishes" :key="p.id" :name="p.id">
          <template #title>
            <span>{{ formatTime(p.created_at, "YYYY-MM-DD HH:mm") }} · {{ p.publisher_name }}</span>
            <el-tag
              size="small"
              :type="p.push_status === 'pushed' ? 'success' : 'info'"
              style="margin-left: 8px"
            >
              {{ p.push_status === "pushed" ? "已推送" : p.push_status }}
            </el-tag>
          </template>
          <div class="pub-item">
            <el-image
              :src="p.screenshot"
              :preview-src-list="[p.screenshot]"
              fit="contain"
              class="pub-img"
              preview-teleported
            />
            <p class="pub-message">{{ p.message }}</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<style scoped>
.report-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.op-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}
.op-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.op-right {
  display: flex;
  gap: 8px;
}
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.section-title {
  color: #303133;
  font-weight: 600;
  margin-bottom: 12px;
}
.form-tip {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.form-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
/* 报告卡片：截图区域 */
.report-card-wrap {
  padding: 0;
  overflow: hidden;
}
.report-card {
  background: #fff;
  padding: 20px 24px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #f0f2f5;
  padding-bottom: 12px;
}
.card-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.card-tags {
  display: inline-flex;
  gap: 6px;
  flex-shrink: 0;
}
.card-meta {
  color: #909399;
  font-size: 13px;
  padding: 10px 0;
  border-bottom: 1px dashed #f0f2f5;
}
.card-body {
  padding: 12px 0;
}
.card-section {
  margin-bottom: 10px;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
}
.sec-label {
  display: inline-block;
  color: #909399;
  font-size: 13px;
  margin-right: 10px;
}
.sec-text {
  white-space: pre-wrap;
  margin: 0;
}
.card-foot {
  display: flex;
  justify-content: space-between;
  color: #c0c4cc;
  font-size: 12px;
  border-top: 1px solid #f0f2f5;
  padding-top: 10px;
}
.pub-collapse {
  border-top: none;
}
.pub-item {
  padding: 4px 8px;
}
.pub-img {
  display: block;
  max-width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin-bottom: 8px;
}
.pub-message {
  color: #606266;
  font-size: 13px;
}
</style>