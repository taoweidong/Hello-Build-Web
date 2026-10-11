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
  getReports,
  type ReportForm
} from "@/api/report";
import type { ReportItem } from "@/api/types";
import { getCurrentUser, formatTime } from "@/utils/business";
import { useReportForm } from "@/composables/useReportForm";
import { useStrategyOptions } from "@/composables/useStrategyOptions";
import { copyText } from "@/utils/clipboard";
import { appHashUrl } from "@/utils/appUrl";
import { reportConclusionMeta, reportStatusMeta } from "@/views/constants";

// 图标：~icons/ri（Remix Icon）+ ~icons/ep（Element Plus Icon）
import ArrowLeft from "~icons/ri/arrow-left-line";
import AddLine from "~icons/ri/add-line";
import EditLine from "~icons/ri/edit-line";
import SendPlane from "~icons/ri/send-plane-fill";
import FileCopy from "~icons/ri/file-copy-line";
import LinkIcon from "~icons/ri/link";
import HistoryLine from "~icons/ri/history-line";
import FileText from "~icons/ri/file-text-line";
import Hashtag from "~icons/ri/hashtag";
import GitBranch from "~icons/ri/git-branch-line";
import FlagLine from "~icons/ri/flag-line";
import ServerLine from "~icons/ri/server-line";
import ClipboardLine from "~icons/ri/clipboard-line";
import AlarmWarning from "~icons/ri/alarm-warning-line";
import StickyNote from "~icons/ri/sticky-note-line";
import UserLine from "~icons/ri/user-line";
import CheckDouble from "~icons/ri/check-double-line";
import CloseCircle from "~icons/ri/close-circle-line";
import ErrorWarning from "~icons/ri/error-warning-line";
import TimeLine from "~icons/ri/time-line";
import SaveLine from "~icons/ri/save-line";
import CloseLine from "~icons/ri/close-line";
import RefreshLine from "~icons/ri/refresh-line";

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
  // 发布后仍可编辑（最终结论锁定），仅作者可编辑
  return canWrite.value && currentUser?.username === row.created_by_username;
}
const canEditCurrent = computed(() =>
  report.value ? canEdit(report.value) : false
);
const canPublishCurrent = computed(() =>
  report.value ? canEdit(report.value) && !isNew.value : false
);

// 已发布后最终结论锁定，其余字段仍可编辑（规则见后端 ReportService）
const conclusionLocked = computed(
  () => !!report.value && report.value.status === "published"
);

// ---- 数据 ----
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const report = ref<ReportItem | null>(null);
const cardWrapRef = ref<HTMLElement | null>(null);
const editing = ref(isNew.value); // 新建态初始为编辑态；详情默认只读

// ---- 版本/策略选项（从全量策略推导，与列表页一致；报告存文本快照，按名称级联）----
const { versionOptions, strategyOptions, loadStrategyOptions } =
  useStrategyOptions(computed(() => form.version_name));
function onVersionChange() {
  form.strategy_name = null;
}

// ---- 表单（状态机收敛在 useReportForm，纯逻辑可单测）----
const { form, initNewForm, fillForm, validateForm, toPayload } =
  useReportForm();
if (isNew.value) initNewForm();

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
  // 只读字段统一从基准报告兜底（两分支曾逐字段重复 15 项，收敛为展开合并）
  const readonlyData = {
    title: base?.title || "",
    version_name: base?.version_name || null,
    strategy_name: base?.strategy_name || null,
    conclusion: base?.conclusion || "",
    status: base?.status || "",
    environment: base?.environment || "",
    summary: base?.summary || "",
    risks: base?.risks || "",
    remark: base?.remark || "",
    created_by_username: base?.created_by_username || "",
    created_at: base?.created_at || new Date().toISOString(),
    published_at: base?.published_at || null,
    publish_count: base?.publish_count || 0,
    is_updated: base?.is_updated || false,
    update_count: base?.update_count || 0
  };
  if (!editing.value && !isNew.value) return readonlyData;
  // 编辑/新建态：表单可编辑字段实时覆盖
  return {
    ...readonlyData,
    title: form.title.trim() || "（未填写标题）",
    version_name: form.version_name || null,
    strategy_name: form.strategy_name || null,
    conclusion: form.conclusion,
    status: base?.status || "draft",
    environment: form.environment,
    summary: form.summary,
    risks: form.risks,
    remark: form.remark,
    created_by_username:
      base?.created_by_username || currentUser?.username || "",
    created_at: base?.created_at || new Date().toISOString()
  };
});

// 居中大标题：XX版本 XX策略 测试 YYYY-MM-DD 分析报告
const headTitle = computed(() => {
  const v = cardData.value.version_name || "XX";
  const s = cardData.value.strategy_name || "XX";
  const d = formatTime(cardData.value.created_at, "YYYY-MM-DD");
  return `${v}版本 ${s}策略 测试 ${d} 分析报告`;
});

// ---- 徽章映射（共享常量，与列表页一致）----
function conclusionTag(c: string) {
  return reportConclusionMeta(c);
}
function statusTag(s: string) {
  return reportStatusMeta(s);
}

// 结论图标映射
const conclusionIconMap: Record<string, any> = {
  pass: CheckDouble,
  fail: CloseCircle,
  risk: ErrorWarning
};
function conclusionIcon(c: string) {
  return conclusionIconMap[c] || CheckDouble;
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
    const code = e?.code;
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
      {
        type: "warning",
        confirmButtonText: "确认发布",
        cancelButtonText: "取消"
      }
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

// ---- 复制报告：报告单截图写入剪贴板（图片），供用户粘贴到文档/聊天等 ----
const copying = ref(false);
function dataUrlToBlob(dataUrl: string): Blob {
  const [head, body] = dataUrl.split(",");
  const mime = head.match(/data:(.*?);/)?.[1] || "image/png";
  const bin = atob(body);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}
async function copyReport() {
  if (!cardWrapRef.value || copying.value) return;
  copying.value = true;
  try {
    const dataUrl = await captureCard();
    if (!navigator.clipboard || typeof ClipboardItem === "undefined") {
      ElMessage.error("当前浏览器不支持复制图片，请改用系统截图");
      return;
    }
    await navigator.clipboard.write([
      new ClipboardItem({ "image/png": dataUrlToBlob(dataUrl) })
    ]);
    ElMessage.success("报告截图已复制，可直接粘贴到其他位置");
  } catch (e) {
    console.error("[report-copy-image] 复制报告截图失败：", e);
    ElMessage.error("复制失败，请重试或改用浏览器截图");
  } finally {
    copying.value = false;
  }
}

// ---- 复制链接 ----
const reportLink = computed(() =>
  appHashUrl(`/report/detail/${routeId.value}`)
);
async function copyLink() {
  const ok = await copyText(reportLink.value);
  if (ok) {
    ElMessage.success("链接已复制");
  } else {
    ElMessage.error("复制失败，请手动复制地址栏链接");
  }
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
    ElMessage.error(e?.message || "报告加载失败");
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
  loadStrategyOptions();
});
</script>

<template>
  <div v-loading="loading" class="report-detail">
    <!-- 顶部操作栏：左侧新建/修改/发布/废弃，右侧历史报告下拉 + 复制链接（无 layout，页面自带导航入口） -->
    <div class="op-bar">
      <div class="op-left">
        <el-button class="op-back" @click="goBack">
          <IconifyIconOffline
            :icon="ArrowLeft"
            style="width: 16px; height: 16px"
          />
          返回列表
        </el-button>
        <el-button
          v-if="canWrite"
          type="primary"
          @click="router.push('/report/detail/new')"
        >
          <IconifyIconOffline
            :icon="AddLine"
            style="width: 16px; height: 16px"
          />
          新建报告
        </el-button>
        <el-button v-if="canEditCurrent && !editing" @click="startEdit">
          <IconifyIconOffline
            :icon="EditLine"
            style="width: 16px; height: 16px"
          />
          修改报告
        </el-button>
        <el-button
          v-if="canPublishCurrent && !editing"
          type="success"
          :loading="publishing"
          @click="onPublish"
        >
          <IconifyIconOffline
            :icon="SendPlane"
            style="width: 16px; height: 16px"
          />
          发布报告
        </el-button>
      </div>
      <div class="op-right">
        <span v-if="!isNew && report" class="op-title">
          <IconifyIconOffline
            :icon="FileText"
            style="
              width: 16px;
              height: 16px;
              vertical-align: -2px;
              margin-right: 4px;
            "
          />
          报告 #{{ report.id }}
        </span>
        <el-dropdown trigger="click" @command="openHistory">
          <el-button>
            <IconifyIconOffline
              :icon="HistoryLine"
              style="width: 16px; height: 16px; margin-right: 4px"
            />
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
        <el-button
          v-if="!isNew && report && !editing"
          :loading="copying"
          @click="copyReport"
        >
          <IconifyIconOffline
            :icon="FileCopy"
            style="width: 16px; height: 16px"
          />
          复制报告
        </el-button>
        <el-button v-if="!isNew && report" @click="copyLink">
          <IconifyIconOffline
            :icon="LinkIcon"
            style="width: 16px; height: 16px"
          />
          复制链接
        </el-button>
      </div>
    </div>

    <!-- 报告单（恒存在，截图目标） -->
    <div
      v-if="report || editing"
      ref="cardWrapRef"
      class="section report-card-wrap"
    >
      <div class="report-card">
        <!-- 第 1 行：居中大标题 + 状态/结论徽章 -->
        <div class="card-head">
          <div class="card-head-badges">
            <el-tag
              :type="statusTag(cardData.status).type"
              size="small"
              effect="dark"
            >
              {{ statusTag(cardData.status).text }}
            </el-tag>
            <el-tag
              :type="conclusionTag(cardData.conclusion).type"
              size="small"
              effect="dark"
            >
              <IconifyIconOffline
                :icon="conclusionIcon(cardData.conclusion)"
                style="
                  width: 14px;
                  height: 14px;
                  vertical-align: -2px;
                  margin-right: 3px;
                "
              />
              {{ conclusionTag(cardData.conclusion).text }}
            </el-tag>
            <span v-if="cardData.is_updated" class="badge-updated">
              <IconifyIconOffline
                :icon="RefreshLine"
                style="width: 13px; height: 13px; vertical-align: -1px"
              />
              已更新 {{ cardData.update_count }} 次
            </span>
          </div>
          <span class="card-title">{{ headTitle }}</span>
          <div class="card-head-meta">
            <IconifyIconOffline
              :icon="TimeLine"
              style="width: 14px; height: 14px; vertical-align: -2px"
            />
            创建于 {{ formatTime(cardData.created_at, "YYYY-MM-DD HH:mm") }}
            <span
              v-if="cardData.status === 'published' && cardData.published_at"
            >
              · 发布于
              {{ formatTime(cardData.published_at, "YYYY-MM-DD HH:mm") }}
            </span>
          </div>
        </div>

        <!-- 第 2~ 行：报告信息行（编辑态行内控件 / 只读态文本） -->
        <div class="card-rows">
          <!-- 上半区：基本信息网格（双列） -->
          <div class="info-grid">
            <div class="card-row">
              <span class="row-label">
                <IconifyIconOffline :icon="FileText" class="label-icon" />
                报告标题
              </span>
              <el-input
                v-if="editing"
                v-model="form.title"
                placeholder="例：27A 冒烟验证报告"
              />
              <span v-else class="row-value">{{ cardData.title || "—" }}</span>
            </div>
            <div class="card-row">
              <span class="row-label">
                <IconifyIconOffline :icon="Hashtag" class="label-icon" />
                报告编号
              </span>
              <span class="row-value">{{ report?.id ?? "—" }}</span>
            </div>
            <div class="card-row">
              <span class="row-label">
                <IconifyIconOffline :icon="GitBranch" class="label-icon" />
                关联版本
              </span>
              <el-select
                v-if="editing"
                v-model="form.version_name"
                placeholder="可选"
                clearable
                @change="onVersionChange"
              >
                <el-option
                  v-for="v in versionOptions"
                  :key="v.name"
                  :label="v.name"
                  :value="v.name"
                />
              </el-select>
              <span v-else class="row-value">{{
                cardData.version_name || "—"
              }}</span>
            </div>
            <div class="card-row">
              <span class="row-label">
                <IconifyIconOffline :icon="FlagLine" class="label-icon" />
                关联策略
              </span>
              <el-select
                v-if="editing"
                v-model="form.strategy_name"
                placeholder="可选"
                clearable
                :disabled="!form.version_name"
              >
                <el-option
                  v-for="s in strategyOptions"
                  :key="s.name"
                  :label="s.name"
                  :value="s.name"
                />
              </el-select>
              <span v-else class="row-value">{{
                cardData.strategy_name || "—"
              }}</span>
            </div>
            <div class="card-row">
              <span class="row-label">
                <IconifyIconOffline :icon="ServerLine" class="label-icon" />
                验证环境
              </span>
              <el-input
                v-if="editing"
                v-model="form.environment"
                placeholder="例：测试环境 / 生产预发"
              />
              <span v-else class="row-value">{{
                cardData.environment || "—"
              }}</span>
            </div>
            <div
              class="card-row conclusion-row"
              :class="`conclusion-${cardData.conclusion}`"
            >
              <span class="row-label">
                <IconifyIconOffline
                  :icon="conclusionIcon(cardData.conclusion)"
                  class="label-icon"
                />
                验证结论
              </span>
              <el-radio-group
                v-if="editing"
                v-model="form.conclusion"
                :disabled="conclusionLocked"
              >
                <el-radio value="pass">通过</el-radio>
                <el-radio value="fail">不通过</el-radio>
                <el-radio value="risk">有风险</el-radio>
              </el-radio-group>
              <span
                v-if="editing && conclusionLocked"
                class="conclusion-locked-hint"
              >
                报告已发布，最终结论不可修改
              </span>
              <span v-else class="row-value conclusion-value">
                <IconifyIconOffline
                  :icon="conclusionIcon(cardData.conclusion)"
                  class="conclusion-icon"
                />
                {{ conclusionTag(cardData.conclusion).text }}（{{
                  cardData.conclusion
                }}）
              </span>
            </div>
          </div>

          <!-- 下半区：详细内容（全宽） -->
          <div class="detail-section">
            <div class="card-row">
              <span class="row-label">
                <IconifyIconOffline :icon="ClipboardLine" class="label-icon" />
                验证内容
              </span>
              <el-input
                v-if="editing"
                v-model="form.summary"
                type="textarea"
                :rows="3"
                placeholder="填写验证内容，将展示在报告单中"
              />
              <span v-else class="row-value">{{
                cardData.summary || "—"
              }}</span>
            </div>
            <div class="card-row">
              <span class="row-label">
                <IconifyIconOffline :icon="AlarmWarning" class="label-icon" />
                问题与风险
              </span>
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
              <span class="row-label">
                <IconifyIconOffline :icon="StickyNote" class="label-icon" />
                备注
              </span>
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
        </div>

        <!-- 最后一行：发布人 + 核心结论 + 状态 + 发布/不发布 -->
        <div class="card-foot">
          <div class="foot-left">
            <span class="foot-publisher">
              <IconifyIconOffline
                :icon="UserLine"
                style="
                  width: 15px;
                  height: 15px;
                  vertical-align: -2px;
                  margin-right: 3px;
                "
              />
              {{ cardData.created_by_username || "—" }}
            </span>
            <el-tag
              :type="conclusionTag(cardData.conclusion).type"
              size="small"
              class="foot-tag"
            >
              <IconifyIconOffline
                :icon="conclusionIcon(cardData.conclusion)"
                style="
                  width: 13px;
                  height: 13px;
                  vertical-align: -1px;
                  margin-right: 3px;
                "
              />
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
              <IconifyIconOffline
                :icon="TimeLine"
                style="width: 13px; height: 13px; vertical-align: -1px"
              />
              发布于
              {{ formatTime(cardData.published_at, "YYYY-MM-DD HH:mm") }}，共
              {{ cardData.publish_count }} 次
              <el-tag
                v-if="cardData.is_updated"
                type="warning"
                size="small"
                class="foot-tag"
              >
                <IconifyIconOffline
                  :icon="RefreshLine"
                  style="width: 12px; height: 12px; vertical-align: -1px"
                />
                更新报告（已更新 {{ cardData.update_count }} 次）
              </el-tag>
            </span>
          </div>
          <div class="foot-actions">
            <template v-if="editing">
              <el-button :loading="saving" @click="saveDraft">
                <IconifyIconOffline
                  :icon="SaveLine"
                  style="width: 15px; height: 15px"
                />
                保存草稿
              </el-button>
              <el-button
                type="success"
                :loading="publishing"
                @click="onPublish"
              >
                <IconifyIconOffline
                  :icon="SendPlane"
                  style="width: 15px; height: 15px"
                />
                发布
              </el-button>
              <el-button v-if="!isNew" @click="cancelEdit">
                <IconifyIconOffline
                  :icon="CloseLine"
                  style="width: 15px; height: 15px"
                />
                取消
              </el-button>
            </template>
            <template v-else-if="canEditCurrent">
              <el-button @click="startEdit">
                <IconifyIconOffline
                  :icon="EditLine"
                  style="width: 15px; height: 15px"
                />
                编辑
              </el-button>
              <el-button
                type="success"
                :loading="publishing"
                @click="onPublish"
              >
                <IconifyIconOffline
                  :icon="SendPlane"
                  style="width: 15px; height: 15px"
                />
                发布
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
  background: var(--el-bg-color-page);
}
.op-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 16px;
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  box-shadow: var(--el-box-shadow-lighter);
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
.op-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: inline-flex;
  align-items: center;
}
.section {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
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
  box-shadow: var(--el-box-shadow);
}
.report-card {
  background: var(--el-bg-color);
  padding: 24px 32px;
}
/* 第 1 行：居中大标题 + 徽章 */
.card-head {
  text-align: center;
  border-bottom: 2px solid var(--el-color-primary);
  padding-bottom: 16px;
}
.card-head-badges {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.badge-updated {
  font-size: 12px;
  color: var(--el-color-warning);
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.card-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  letter-spacing: 1px;
  display: block;
}
.card-head-meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
}
/* 第 2~ 行：报告信息行 */
.card-rows {
  padding: 12px 0;
}
/* 上半区：基本信息双列网格 */
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 24px;
}
/* 结论行跨双列 */
.conclusion-row {
  grid-column: 1 / -1;
}
.card-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 9px 4px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  font-size: 14px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}
.card-row:last-child {
  border-bottom: none;
}
.row-label {
  flex-shrink: 0;
  width: 88px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding-top: 4px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.label-icon {
  width: 15px;
  height: 15px;
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}
.row-value {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
}
.card-row :deep(.el-input),
.card-row :deep(.el-select),
.card-row :deep(.el-textarea) {
  max-width: 380px;
}
/* 结论行高亮 */
.conclusion-row {
  margin-top: 4px;
  padding: 10px 8px;
  border-radius: 6px;
  border-bottom: none;
}
.conclusion-pass {
  background: var(--el-color-success-light-9);
}
.conclusion-fail {
  background: var(--el-color-danger-light-9);
}
.conclusion-risk {
  background: var(--el-color-warning-light-9);
}
.conclusion-value {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
}
.conclusion-icon {
  width: 18px;
  height: 18px;
}
.conclusion-pass .conclusion-icon,
.conclusion-pass .label-icon {
  color: var(--el-color-success);
}
.conclusion-fail .conclusion-icon,
.conclusion-fail .label-icon {
  color: var(--el-color-danger);
}
.conclusion-risk .conclusion-icon,
.conclusion-risk .label-icon {
  color: var(--el-color-warning);
}
/* 下半区：详细内容区块 */
.detail-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.detail-section .card-row :deep(.el-input),
.detail-section .card-row :deep(.el-select),
.detail-section .card-row :deep(.el-textarea) {
  max-width: 100%;
  flex: 1;
}
/* 最后一行：发布人 + 核心结论 + 发布/不发布 */
.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  border-top: 1px solid var(--el-border-color-lighter);
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
  color: var(--el-text-color-regular);
  font-size: 13px;
  display: inline-flex;
  align-items: center;
}
.foot-tag {
  flex-shrink: 0;
}
.foot-meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
/* 已发布最终结论锁定提示 */
.conclusion-locked-hint {
  color: var(--el-color-warning);
  font-size: 12px;
  line-height: 32px;
}
.foot-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
/* 响应式：窄屏时网格变单列 */
@media (max-width: 640px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
  .conclusion-row {
    grid-column: auto;
  }
}
</style>
