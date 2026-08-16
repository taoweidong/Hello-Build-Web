<script setup lang="ts">
// 验证报告详情/编辑页：报告单布局（居中标题 + 信息行 + 末行发布人/核心结论/操作）
// 权限：tester/builder 且作者可编辑发布；新建态天然为编辑态
import { ref, reactive, computed, onMounted, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import html2canvas from "html2canvas-pro";
import {
  getReport,
  createReport,
  updateReport,
  publishReport,
  deprecateReport,
  getReports,
  type ReportForm
} from "@/api/report";
import { getStrategies } from "@/api/strategy";
import type { ReportItem, StrategyItem } from "@/api/types";
import { getCurrentUser, formatTime } from "@/utils/business";

defineOptions({ name: "ReportDetail" });

const route = useRoute();
const router = useRouter();
const currentUser = getCurrentUser();

// 无 layout 页面：返回列表入口
function goBack() {
  router.push("/report/index");
}

const MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024; // 2MB，与后端校验一致

// ---- 路由态 ----
const routeId = computed(() => String(route.params.id ?? ""));
const isNew = computed(() => routeId.value === "new");

// ---- 权限 ----
const canWrite = computed(
  () => currentUser?.role === "tester" || currentUser?.role === "builder"
);
function canEdit(row: ReportItem) {
  // published 锁定不可编辑；deprecated 允许编辑解锁后重新发布
  return canWrite.value && currentUser?.id === row.created_by_id && row.status !== "published";
}
const canEditCurrent = computed(() => (report.value ? canEdit(report.value) : false));
const canDeprecateCurrent = computed(
  () => !!report.value && report.value.status === "published" && canWrite.value && currentUser?.id === report.value.created_by_id
);
const canPublishCurrent = computed(() =>
  report.value ? canEdit(report.value) && !isNew.value : false
);

// ---- 数据 ----
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const report = ref<ReportItem | null>(null);
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

// 新建态预填模拟关键信息，便于快速成稿与截图验证（路由切换新建时同样调用）
function initNewForm() {
  // 重置全部字段：路由从详情切到新建时组件复用，需清空残留（含版本/策略）
  form.title = "27A 冒烟验证报告";
  form.version_id = null;
  form.strategy_id = null;
  form.conclusion = "pass";
  form.environment = "测试环境（27A 预发）";
  form.summary =
    "针对 27A 版本冒烟策略执行完整验证：核心流程用例 12 项全部通过，未出现阻断性问题。";
  form.risks = "存在 1 项中风险：附件上传偶发延迟（已提单跟踪）。";
  form.remark = "建议次日回归确认风险项后放行发布。";
}
if (isNew.value) initNewForm();

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
      created_at: base?.created_at || new Date().toISOString(),
      published_at: base?.published_at || null,
      publish_count: base?.publish_count || 0,
      deprecated_at: base?.deprecated_at || null,
      deprecated_reason: base?.deprecated_reason || ""
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
    created_at: base?.created_at || new Date().toISOString(),
    published_at: base?.published_at || null,
    publish_count: base?.publish_count || 0,
    deprecated_at: base?.deprecated_at || null,
    deprecated_reason: base?.deprecated_reason || ""
  };
});

// 居中大标题：XX版本 XX策略 测试 YYYY-MM-DD 分析报告
const headTitle = computed(() => {
  const v = cardData.value.version_name || "XX";
  const s = cardData.value.strategy_name || "XX";
  const d = formatTime(cardData.value.created_at, "YYYY-MM-DD");
  return `${v}版本 ${s}策略 测试 ${d} 分析报告`;
});

// ---- 徽章映射（与列表页一致）----
const conclusionMap: Record<string, { text: string; type: "success" | "danger" | "warning" | "info" }> = {
  pass: { text: "通过", type: "success" },
  fail: { text: "不通过", type: "danger" },
  risk: { text: "有风险", type: "warning" }
};
const statusMap: Record<string, { text: string; type: "info" | "success" | "danger" }> = {
  draft: { text: "草稿", type: "info" },
  published: { text: "已发布", type: "success" },
  deprecated: { text: "已废弃", type: "danger" }
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
      editing.value = false; // 编辑态发布完成后转为只读展示
      // 清理深链接 edit 标记，避免 URL 残留 ?edit=1
      if (route.query.edit) {
        await router.replace(`/report/detail/${savedReportId}`);
      }
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

// ---- 历史报告下拉（全部用户报告，选择后下方即切换展示）----
const historyList = ref<ReportItem[]>([]);
async function loadHistory() {
  try {
    historyList.value = await getReports();
  } catch {
    historyList.value = [];
  }
}
async function openHistory(id: number | string) {
  if (String(id) === routeId.value) return;
  try {
    const data = await getReport(Number(id));
    report.value = data;
    fillForm(data);
    editing.value = false;
    await router.replace(`/report/detail/${data.id}`);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "报告加载失败");
  }
}

// ---- 废弃报告：仅已发布作者可操作，页面标记 + 原因追溯 ----
const deprecating = ref(false);
async function onDeprecate() {
  if (!report.value) return;
  let reason = "";
  try {
    const { value } = await ElMessageBox.prompt(
      "报告发布后不可直接修改。废弃后页面将标记「已废弃」，您可重新编辑并再次发布新版本（废弃记录保留）。",
      "废弃报告",
      {
        confirmButtonText: "确认废弃",
        cancelButtonText: "取消",
        inputPlaceholder: "请输入废弃原因（必填）",
        inputValidator: (v: string) => (v && v.trim() ? true : "废弃原因不能为空")
      }
    );
    reason = value.trim();
  } catch {
    return; // 用户取消
  }
  deprecating.value = true;
  try {
    const saved = await deprecateReport(report.value.id, reason);
    report.value = saved;
    ElMessage.success("报告已废弃，页面已标记");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "废弃失败，请重试");
  } finally {
    deprecating.value = false;
  }
}

// ---- 路由切换重置：详情/新建间跳转组件实例复用，需重置页面状态 ----
watch(
  () => route.params.id,
  async () => {
    report.value = null;
    editing.value = isNew.value;
    if (isNew.value) initNewForm();
    await loadReport();
    loadHistory();
  }
);

onMounted(async () => {
  await loadReport();
  loadHistory();
  try {
    allStrategies.value = await getStrategies();
  } catch {
    allStrategies.value = [];
  }
});
</script>

<template>
  <div class="report-detail" v-loading="loading">
    <!-- 顶部操作栏：左侧新建/修改/发布/废弃，右侧历史报告下拉 + 复制链接（无 layout，页面自带导航入口） -->
    <div class="op-bar">
      <div class="op-left">
        <el-button class="op-back" @click="goBack">← 返回列表</el-button>
        <el-button v-if="canWrite" type="primary" @click="router.push('/report/detail/new')">
          新建报告
        </el-button>
        <el-button
          v-if="canEditCurrent && !editing"
          @click="startEdit"
        >
          修改报告
        </el-button>
        <el-button
          v-if="canPublishCurrent && !editing"
          type="success"
          :loading="publishing"
          @click="onPublish"
        >
          发布报告
        </el-button>
        <el-button
          v-if="canDeprecateCurrent"
          type="danger"
          plain
          :loading="deprecating"
          @click="onDeprecate"
        >
          废弃报告
        </el-button>
      </div>
      <div class="op-right">
        <span v-if="!isNew && report" class="op-title">报告 #{{ report.id }}</span>
        <el-dropdown trigger="click" @command="openHistory">
          <el-button>
            历史报告<i class="el-icon--right">▾</i>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu class="history-menu">
              <el-dropdown-item
                v-for="h in historyList"
                :key="h.id"
                :command="h.id"
                :disabled="h.id === report?.id"
              >
                <span class="history-item">
                  <span class="history-title">#{{ h.id }} {{ h.title }}</span>
                  <el-tag :type="statusTag(h.status).type" size="small">
                    {{ statusTag(h.status).text }}
                  </el-tag>
                </span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button v-if="!isNew && report" @click="copyLink">复制链接</el-button>
      </div>
    </div>

    <!-- 报告单（恒存在，截图目标） -->
    <div
      v-if="report || editing"
      ref="cardWrapRef"
      class="section report-card-wrap"
    >
      <div class="report-card">
        <!-- 废弃标记：页面显著标记，废弃原因随时间保留追溯 -->
        <div v-if="cardData.status === 'deprecated'" class="card-deprecated-bar">
          <span class="deprecated-title">⚠ 本报告已废弃</span>
          <span class="deprecated-meta">
            （{{ formatTime(cardData.deprecated_at, "YYYY-MM-DD HH:mm") }}）：{{
              cardData.deprecated_reason || "未填写原因"
            }}
          </span>
          <span class="deprecated-hint">仅作者可重新编辑后发布新版本</span>
        </div>

        <!-- 第 1 行：居中大标题 -->
        <div class="card-head">
          <span class="card-title">{{ headTitle }}</span>
        </div>

        <!-- 第 2~ 行：报告信息行（编辑态行内控件 / 只读态文本） -->
        <div class="card-rows">
          <div class="card-row">
            <span class="row-label">报告标题</span>
            <el-input
              v-if="editing"
              v-model="form.title"
              placeholder="例：27A 冒烟验证报告"
            />
            <span v-else class="row-value">{{ cardData.title || "—" }}</span>
          </div>
          <div class="card-row">
            <span class="row-label">报告编号</span>
            <span class="row-value">{{ report?.id ?? "—" }}</span>
          </div>
          <div class="card-row">
            <span class="row-label">关联版本</span>
            <el-select
              v-if="editing"
              v-model="form.version_id"
              placeholder="可选"
              clearable
              @change="onVersionChange"
            >
              <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
            </el-select>
            <span v-else class="row-value">{{ cardData.version_name || "—" }}</span>
          </div>
          <div class="card-row">
            <span class="row-label">关联策略</span>
            <el-select
              v-if="editing"
              v-model="form.strategy_id"
              placeholder="可选"
              clearable
              :disabled="!form.version_id"
            >
              <el-option v-for="s in strategyOptions" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
            <span v-else class="row-value">{{ cardData.strategy_name || "—" }}</span>
          </div>
          <div class="card-row">
            <span class="row-label">验证结论</span>
            <el-radio-group v-if="editing" v-model="form.conclusion">
              <el-radio value="pass">通过</el-radio>
              <el-radio value="fail">不通过</el-radio>
              <el-radio value="risk">有风险</el-radio>
            </el-radio-group>
            <span v-else class="row-value">
              {{ conclusionTag(cardData.conclusion).text }}（{{ cardData.conclusion }}）
            </span>
          </div>
          <div class="card-row">
            <span class="row-label">验证环境</span>
            <el-input
              v-if="editing"
              v-model="form.environment"
              placeholder="例：测试环境 / 生产预发"
            />
            <span v-else class="row-value">{{ cardData.environment || "—" }}</span>
          </div>
          <div class="card-row">
            <span class="row-label">验证内容</span>
            <el-input
              v-if="editing"
              v-model="form.summary"
              type="textarea"
              :rows="3"
              placeholder="填写验证内容，将展示在报告单中"
            />
            <span v-else class="row-value">{{ cardData.summary || "—" }}</span>
          </div>
          <div class="card-row">
            <span class="row-label">问题与风险</span>
            <el-input
              v-if="editing"
              v-model="form.risks"
              type="textarea"
              :rows="2"
              placeholder="可选"
            />
            <span v-else class="row-value">{{ cardData.risks || "—" }}</span>
          </div>
          <div class="card-row">
            <span class="row-label">备注</span>
            <el-input
              v-if="editing"
              v-model="form.remark"
              type="textarea"
              :rows="2"
              placeholder="可选"
            />
            <span v-else class="row-value">{{ cardData.remark || "—" }}</span>
          </div>
        </div>

        <!-- 最后一行：发布人 + 核心结论 + 状态 + 发布/不发布 -->
        <div class="card-foot">
          <div class="foot-left">
            <span class="foot-publisher">发布人：{{ cardData.created_by_name || "—" }}</span>
            <el-tag :type="conclusionTag(cardData.conclusion).type" size="small" class="foot-tag">
              核心结论：{{ conclusionTag(cardData.conclusion).text }}
            </el-tag>
            <el-tag
              v-if="cardData.status"
              :type="statusTag(cardData.status).type"
              size="small"
              class="foot-tag"
            >
              {{ statusTag(cardData.status).text }}
            </el-tag>
            <span
              v-if="cardData.status === 'published' && cardData.published_at"
              class="foot-meta"
            >
              发布于 {{ formatTime(cardData.published_at, "YYYY-MM-DD HH:mm") }}，共
              {{ cardData.publish_count }} 次
            </span>
            <span
              v-if="cardData.status === 'deprecated' && cardData.deprecated_at"
              class="foot-meta foot-deprecated"
            >
              已废弃于 {{ formatTime(cardData.deprecated_at, "YYYY-MM-DD HH:mm") }}，原发布于
              {{ formatTime(cardData.published_at, "YYYY-MM-DD HH:mm") }}，共
              {{ cardData.publish_count }} 次
            </span>
          </div>
          <div class="foot-actions">
            <template v-if="editing">
              <el-button :loading="saving" @click="saveDraft">保存草稿（不发布）</el-button>
              <el-button type="success" :loading="publishing" @click="onPublish">发布</el-button>
              <el-button v-if="!isNew" @click="cancelEdit">取消</el-button>
            </template>
            <template v-else-if="canEditCurrent">
              <el-button @click="startEdit">编辑</el-button>
              <el-button type="success" :loading="publishing" @click="onPublish">发布</el-button>
            </template>
            <template v-else-if="canDeprecateCurrent">
              <el-button type="danger" plain :loading="deprecating" @click="onDeprecate">
                废弃报告
              </el-button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 空态：报告不存在（非新建且加载完成） -->
    <el-empty v-if="!report && !editing" description="报告不存在或已删除" />

    </div>
</template>

<style scoped>
/* 无 layout 全屏空白页面：淡灰背景，内容居中限宽（类报告单展示） */
.report-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 100vh;
  padding: 16px 20px;
  box-sizing: border-box;
  background: #f5f7fa;
}
.op-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
}
.op-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.op-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.op-back {
  margin-right: 4px;
}
/* 历史下拉菜单 teleport 到 body，需全局样式 */
:global(.history-menu) {
  max-height: 360px;
  overflow-y: auto;
}
:global(.history-item) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 260px;
  justify-content: space-between;
}
:global(.history-title) {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 废弃标记条：卡片顶部显著告警 */
.card-deprecated-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  background: #fef0f0;
  border: 1px solid #f56c6c;
  border-radius: 6px;
  color: #f56c6c;
  font-size: 13px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.deprecated-title {
  font-weight: 600;
}
.deprecated-meta {
  color: #e64646;
}
.deprecated-hint {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.foot-deprecated {
  color: #f56c6c;
}
.op-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
/* 报告单：截图区域（居中限宽） */
.report-card-wrap {
  padding: 0;
  overflow: hidden;
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
}
.report-card {
  background: #fff;
  padding: 24px 32px;
}
/* 第 1 行：居中大标题 */
.card-head {
  text-align: center;
  border-bottom: 2px solid #409eff;
  padding-bottom: 14px;
}
.card-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  letter-spacing: 1px;
}
/* 第 2~ 行：报告信息行 */
.card-rows {
  padding: 8px 0;
}
.card-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px dashed #f0f2f5;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
}
.card-row:last-child {
  border-bottom: none;
}
.row-label {
  flex-shrink: 0;
  width: 72px;
  color: #909399;
  font-size: 13px;
  padding-top: 4px;
}
.row-value {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
}
.card-row :deep(.el-input),
.card-row :deep(.el-select),
.card-row :deep(.el-textarea) {
  max-width: 520px;
}
/* 最后一行：发布人 + 核心结论 + 发布/不发布 */
.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  border-top: 1px solid #e5e7eb;
  padding-top: 14px;
}
.foot-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}
.foot-publisher {
  color: #606266;
  font-size: 13px;
}
.foot-tag {
  flex-shrink: 0;
}
.foot-meta {
  color: #909399;
  font-size: 12px;
}
.foot-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>