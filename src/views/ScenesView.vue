<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import {
  ArrowLeft,
  ArrowRight as ChevronRight,
  Box as PackageOpen,
  Box as PackagePlus,
  CircleCheck as CheckCircle2,
  Collection as Layers3,
  Connection as GitBranch,
  Document as File,
  DocumentAdd as FilePlus,
  Download,
  Edit as Pencil,
  Folder,
  FolderAdd as FolderPlus,
  Finished as Save,
  Plus,
  Refresh as RefreshCw,
  Search,
  Delete as Trash2,
  Upload,
  View as Eye,
} from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import type { UploadFile } from "element-plus";

import {
  createSceneDirectory,
  deleteScenePath,
  downloadScenePath,
  getSceneGitSyncJob,
  listSceneEntries,
  listSceneGitSyncJobs,
  listAvailableGitRepositories,
  moveScenePath,
  readSceneFile,
  uploadSceneDirectoryPackage,
  uploadSceneFile,
  writeSceneFile,
} from "@/api/admin";
import AppPanel from "@/components/AppPanel.vue";
import CodeEditor from "@/components/CodeEditor.vue";
import FieldInput from "@/components/FieldInput.vue";
import FormDrawer from "@/components/FormDrawer.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import MarkdownEditor from "@/components/MarkdownEditor.vue";
import StatusBanner from "@/components/StatusBanner.vue";
import { useSceneStore } from "@/stores/scene";
import { useScopeStore } from "@/stores/scope";
import { useSkillStore } from "@/stores/skill";
import { useUiStore } from "@/stores/ui";
import type { BackgroundJob, ManagedFileEntry, ManagedGitRepository, ManagedTextFile, WorkspaceSceneAsset } from "@/types/admin";
import { formatBytes, formatDate } from "@/utils/format";
import { fitFloatingElementToViewport } from "@/utils/floatingPosition";
import { joinRelativePath, parentRelativePath } from "@/utils/path";

interface FinderColumn {
  path: string;
  entries: ManagedFileEntry[];
  loading: boolean;
  error: string;
}

type SceneActionId =
  | "create-scene"
  | "create-git-scene"
  | "sync-git-scene"
  | "upload-scene-package"
  | "metadata"
  | "replace-asset-package"
  | "create-file"
  | "create-directory"
  | "upload-file"
  | "delete-scene"
  | "preview"
  | "edit"
  | "download"
  | "replace-file"
  | "replace-directory-package"
  | "rename"
  | "move"
  | "delete";

interface SceneAction {
  id: SceneActionId;
  label: string;
  icon: typeof File;
  tone: "primary" | "secondary" | "danger";
  wide?: boolean;
}

interface ContextMenuState {
  open: boolean;
  x: number;
  y: number;
  parentPath: string;
  targetEntry: ManagedFileEntry | null;
  targetScene: WorkspaceSceneAsset | null;
  assetBrowser: boolean;
}

type UploadComponentRef = {
  $el: HTMLElement;
  clearFiles: () => void;
};

type ScrollbarRef = {
  setScrollLeft: (value: number) => void;
};

const scopeStore = useScopeStore();
const sceneStore = useSceneStore();
const skillStore = useSkillStore();
const uiStore = useUiStore();

const scopeRefs = storeToRefs(scopeStore);
const sceneRefs = storeToRefs(sceneStore);
const skillRefs = storeToRefs(skillStore);

const createOpen = ref(false);
const createMode = ref<"normal" | "git">("normal");
const metadataOpen = ref(false);
const keyword = ref("");
const columns = ref<FinderColumn[]>([]);
const selectedPathByColumn = ref<Record<number, string>>({});
const selectedEntry = ref<ManagedFileEntry | null>(null);
const openedFile = ref<ManagedTextFile | null>(null);
const fileDraft = ref("");
const fileMode = ref<"preview" | "edit" | null>(null);
const fileLoading = ref(false);
const fileError = ref("");
const fileSaving = ref(false);
const treeLoading = ref(false);
const treeError = ref("");
const uploadInput = ref<UploadComponentRef | null>(null);
const packageInput = ref<UploadComponentRef | null>(null);
const assetPackageInput = ref<UploadComponentRef | null>(null);
const createPackageInput = ref<UploadComponentRef | null>(null);
const uploadTargetPath = ref("");
const uploadTargetMode = ref<"directory" | "file">("directory");
const packageTargetPath = ref("");
const directoryScroller = ref<ScrollbarRef | null>(null);
const contextMenuElement = ref<HTMLElement | null>(null);
const activeSyncJobId = ref("");
const availableGitRepositories = ref<ManagedGitRepository[]>([]);
const syncJobProgress = ref(0);
const syncJobMessage = ref("");
const syncJobStatus = ref("");
let syncPollTimer: number | null = null;
const contextMenu = ref<ContextMenuState>({
  open: false,
  x: 0,
  y: 0,
  parentPath: "",
  targetEntry: null,
  targetScene: null,
  assetBrowser: false,
});

const form = reactive({
  name: "",
  description: "",
  status: "enabled",
  requiredSkillAssetKey: "",
  gitRepositoryId: "",
  branch: "",
  ref: "",
  subdir: "",
  autoSyncEnabled: false,
  dailySyncTime: "03:00",
  timezone: "Asia/Shanghai",
});

const metadataForm = reactive({
  name: "",
  description: "",
  status: "enabled",
  requiredSkillAssetKey: "",
  isGit: false,
  gitRepositoryId: "",
  branch: "",
  ref: "",
  subdir: "",
  autoSyncEnabled: false,
  dailySyncTime: "03:00",
  timezone: "Asia/Shanghai",
});

const currentScope = computed(() => scopeRefs.selectedAssetTenantScope.value);
const currentScene = computed(() => sceneRefs.currentScene.value);
const filteredScenes = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  if (!text) {
    return sceneRefs.scenes.value;
  }
  return sceneRefs.scenes.value.filter((scene) =>
    [scene.name, scene.asset_key, scene.description].some((value) => value.toLowerCase().includes(text)),
  );
});
const selectedAssetKey = computed(() => currentScene.value?.asset_key ?? "");
const currentSceneReadonly = computed(() => currentScene.value?.readonly || currentScene.value?.source === "git");
const currentSceneGit = computed(() => currentScene.value?.git ?? null);
const currentGitRepository = computed(() =>
  availableGitRepositories.value.find(
    (repository) => repository.id === currentSceneGit.value?.git_repository_id,
  ) ?? null,
);
const syncInProgress = computed(() => syncJobStatus.value === "queued" || syncJobStatus.value === "running");
const syncProgressLabel = computed(() => {
  if (syncInProgress.value) {
    return `${syncJobProgress.value}%`;
  }
  return syncStatusLabel(currentSceneGit.value?.last_sync_status || "never");
});
const syncBannerBody = computed(() => `${syncProgressLabel.value} · ${syncJobMessage.value || "正在同步仓库内容"}`);
const skillOptions = computed(() => skillRefs.skills.value.filter((skill) => skill.status === "enabled"));
const boundSkill = computed(() => {
  const key = currentScene.value?.required_skill_asset_key ?? "";
  return skillRefs.skills.value.find((skill) => skill.asset_key === key) ?? null;
});
const activeDirectoryPath = computed(() => {
  if (selectedEntry.value?.entry_type === "directory") {
    return selectedEntry.value.path;
  }
  if (selectedEntry.value?.entry_type === "file") {
    return parentRelativePath(selectedEntry.value.path);
  }
  return columns.value[columns.value.length - 1]?.path ?? "";
});
const openedFileDirty = computed(() => openedFile.value !== null && fileDraft.value !== openedFile.value.content);
const canSaveFile = computed(
  () =>
    fileMode.value === "edit"
    && openedFileDirty.value
    && !fileSaving.value
    && !fileLoading.value
    && !currentSceneReadonly.value,
);
const openedFileMarkdown = computed(() => {
  const path = openedFile.value?.path || selectedEntry.value?.path || "";
  const lowerPath = path.toLowerCase();
  return lowerPath.endsWith(".md") || lowerPath.endsWith(".markdown");
});
const inlineFilePath = computed(() => openedFile.value?.path || selectedEntry.value?.path || "");
const inlineFileName = computed(() => {
  const parts = inlineFilePath.value.split("/").filter(Boolean);
  return parts[parts.length - 1] || inlineFilePath.value || "未打开文件";
});
const inlineFilePathLabel = computed(() => inlineFilePath.value || "未打开路径");
const selectedEntryMeta = computed(() => {
  const entry = selectedEntry.value;
  if (!entry) {
    return [];
  }
  const rows = [
    ["类型", entry.entry_type === "directory" ? "目录" : fileKind(entry)],
    ["路径", entry.path],
  ];
  if (entry.entry_type === "file") {
    rows.splice(1, 0, ["大小", formatBytes(entry.size_bytes)]);
  }
  rows.push(["修改时间", formatDate(entry.modified_at ?? undefined)]);
  return rows;
});
const detailActions = computed(() => {
  if (!currentScene.value) {
    return [];
  }
  return selectedEntry.value ? entryActions(selectedEntry.value) : sceneRootActions();
});
const contextMenuActions = computed(() => {
  const menu = contextMenu.value;
  if (menu.assetBrowser) {
    return sceneBrowserActions();
  }
  if (menu.targetScene) {
    return sceneRootActions();
  }
  if (menu.targetEntry) {
    return entryActions(menu.targetEntry);
  }
  return directoryEmptyActions();
});

watch(
  () => currentScope.value,
  async (scope) => {
    if (scope) {
      sceneStore.clearCurrentScene();
      resetTreeState();
      resetSyncState();
      const [gitRepositories] = await Promise.all([
        listAvailableGitRepositories(scope),
        sceneStore.loadScenes(scope),
        skillStore.loadSkills(scope),
      ]);
      availableGitRepositories.value = gitRepositories;
    } else {
      sceneStore.reset();
      skillStore.reset();
      availableGitRepositories.value = [];
      resetTreeState();
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  stopSyncPolling();
});

function resetForm(): void {
  form.name = "";
  form.description = "";
  form.status = "enabled";
  form.requiredSkillAssetKey = "";
  form.gitRepositoryId = "";
  form.branch = "";
  form.ref = "";
  form.subdir = "";
  form.autoSyncEnabled = false;
  form.dailySyncTime = "03:00";
  form.timezone = "Asia/Shanghai";
}

function openCreate(): void {
  createMode.value = "normal";
  resetForm();
  createOpen.value = true;
}

function openCreateGit(): void {
  createMode.value = "git";
  resetForm();
  createOpen.value = true;
}

function closeCreate(): void {
  createOpen.value = false;
  resetForm();
}

function packageAssetName(filename: string): string {
  return filename.replace(/\.zip$/iu, "").trim();
}

function openUploadDialog(uploadRef: UploadComponentRef | null): void {
  uploadRef?.$el.querySelector<HTMLInputElement>("input[type='file']")?.click();
}

async function promptText(title: string, inputValue: string): Promise<string> {
  try {
    const { value } = await ElMessageBox.prompt(title, title, {
      inputValue,
      confirmButtonText: "确定",
      cancelButtonText: "取消",
    });
    return String(value ?? "").trim();
  } catch {
    return "";
  }
}

async function confirmDanger(message: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, "确认操作", {
      confirmButtonText: "确认",
      cancelButtonText: "取消",
      type: "warning",
    });
    return true;
  } catch {
    return false;
  }
}

function openCreateFromPackage(): void {
  openUploadDialog(createPackageInput.value);
}

function syncStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    never: "未同步",
    queued: "排队中",
    running: "同步中",
    succeeded: "已同步",
    failed: "同步失败",
    canceled: "已取消",
  };
  return labels[status] ?? status;
}

function assetStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    enabled: "启用",
    disabled: "停用",
    deleted: "已删除",
  };
  return labels[status] ?? status;
}

function gitSubdirLabel(subdir: string): string {
  return subdir.trim() || "仓库根目录";
}

async function submitCreate(): Promise<void> {
  if (!currentScope.value) {
    return;
  }
  const name = form.name.trim();
  if (!name) {
    uiStore.pushNotice({ tone: "warning", title: "请填写 Scene 名称" });
    return;
  }
  let shouldStartInitialSync = false;
  if (createMode.value === "git") {
    if (!form.gitRepositoryId) {
      uiStore.pushNotice({ tone: "warning", title: "请选择可用 Git 仓库" });
      return;
    }
    await sceneStore.createNewGitScene({
      scope: currentScope.value,
      name,
      description: form.description.trim(),
      status: form.status,
      requiredSkillAssetKey: form.requiredSkillAssetKey,
      gitRepositoryId: form.gitRepositoryId,
      branch: form.branch.trim(),
      ref: form.ref.trim(),
      subdir: form.subdir.trim(),
      autoSyncEnabled: form.autoSyncEnabled,
      dailySyncTime: form.dailySyncTime.trim() || "03:00",
      timezone: form.timezone.trim() || "Asia/Shanghai",
    });
    shouldStartInitialSync = true;
  } else {
    await sceneStore.createNewScene({
      scope: currentScope.value,
      name,
      description: form.description.trim(),
      status: form.status,
      requiredSkillAssetKey: form.requiredSkillAssetKey,
    });
  }
  closeCreate();
  await reloadSceneTree();
  if (shouldStartInitialSync) {
    await syncCurrentGitScene("create");
  }
  uiStore.pushNotice({ tone: "success", title: "Scene 已创建" });
}

async function openScene(scene: WorkspaceSceneAsset): Promise<void> {
  resetSyncState();
  sceneStore.selectScene(scene.asset_key);
  await reloadSceneTree();
  await restoreSceneSyncState();
}

async function handleCreatePackageFile(file: File | undefined): Promise<void> {
  if (!file || !currentScope.value) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".zip")) {
    uiStore.pushNotice({ tone: "warning", title: "请选择 zip 包" });
    return;
  }
  const name = packageAssetName(file.name);
  if (!name) {
    uiStore.pushNotice({ tone: "warning", title: "zip 文件名不能为空" });
    return;
  }
  try {
    await sceneStore.createFromPackage(currentScope.value, name, file);
    await reloadSceneTree();
    uiStore.pushNotice({ tone: "success", title: "Scene 包已上传" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "上传 Scene 包失败", body: error instanceof Error ? error.message : "" });
  }
}

async function handleCreatePackage(uploadFile: UploadFile): Promise<void> {
  const file = uploadFile.raw;
  createPackageInput.value?.clearFiles();
  await handleCreatePackageFile(file);
}

function openMetadata(): void {
  const scene = currentScene.value;
  if (!scene) {
    return;
  }
  metadataForm.name = scene.name;
  metadataForm.description = scene.description;
  metadataForm.status = scene.status;
  metadataForm.requiredSkillAssetKey = scene.required_skill_asset_key ?? "";
  metadataForm.isGit = scene.source === "git" && !!scene.git;
  metadataForm.gitRepositoryId = scene.git?.git_repository_id ?? "";
  metadataForm.branch = scene.git?.branch ?? "";
  metadataForm.ref = scene.git?.ref ?? "";
  metadataForm.subdir = scene.git?.subdir ?? "";
  metadataForm.autoSyncEnabled = scene.git?.auto_sync_enabled ?? false;
  metadataForm.dailySyncTime = scene.git?.daily_sync_time || "03:00";
  metadataForm.timezone = scene.git?.timezone || "Asia/Shanghai";
  metadataOpen.value = true;
}

async function submitMetadata(): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  const assetKey = currentScene.value.asset_key;
  const shouldUpdateGit = metadataForm.isGit;
  if (shouldUpdateGit && !metadataForm.gitRepositoryId) {
    uiStore.pushNotice({ tone: "warning", title: "请选择可用 Git 仓库" });
    return;
  }
  await sceneStore.updateCurrentScene(currentScope.value, {
    name: metadataForm.name.trim(),
    description: metadataForm.description.trim(),
    status: metadataForm.status,
    requiredSkillAssetKey: metadataForm.requiredSkillAssetKey,
  });
  if (shouldUpdateGit) {
    await sceneStore.updateCurrentSceneGitConfig(currentScope.value, assetKey, {
      gitRepositoryId: metadataForm.gitRepositoryId,
      branch: metadataForm.branch.trim(),
      ref: metadataForm.ref.trim(),
      subdir: metadataForm.subdir.trim(),
      autoSyncEnabled: metadataForm.autoSyncEnabled,
      dailySyncTime: metadataForm.dailySyncTime.trim() || "03:00",
      timezone: metadataForm.timezone.trim() || "Asia/Shanghai",
    });
  }
  metadataOpen.value = false;
  await reloadSceneTree();
  uiStore.pushNotice({ tone: "success", title: "Scene 元信息已更新" });
}

async function removeCurrent(): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  const scene = currentScene.value;
  if (!await confirmDanger(`确认删除 Scene：${scene.name}？`)) {
    return;
  }
  resetSyncState();
  await sceneStore.removeScene(currentScope.value, scene.asset_key);
  resetTreeState();
  uiStore.pushNotice({ tone: "success", title: "Scene 已删除" });
}

async function refresh(): Promise<void> {
  if (!currentScope.value) {
    return;
  }
  await Promise.all([
    sceneStore.loadScenes(currentScope.value, { preserveCurrent: true }),
    skillStore.loadSkills(currentScope.value),
  ]);
  if (currentScene.value) {
    await reloadSceneTree();
  }
}

async function syncCurrentGitScene(trigger: "manual" | "create" = "manual"): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  if (syncInProgress.value) {
    return;
  }
  try {
    const job = await sceneStore.syncGitScene(currentScope.value, currentScene.value.asset_key);
    applySyncJob(job, trigger === "create" ? "创建完成，正在同步仓库内容" : "同步任务已创建");
    startSyncPolling(job.job_id);
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "同步失败", body: error instanceof Error ? error.message : "" });
  }
}

function applySyncJob(job: BackgroundJob, fallbackMessage = ""): void {
  activeSyncJobId.value = job.job_id;
  syncJobStatus.value = job.status;
  syncJobProgress.value = job.progress;
  syncJobMessage.value = fallbackMessage || job.message || job.error || "";
}

function startSyncPolling(jobId: string): void {
  stopSyncPolling();
  syncPollTimer = window.setInterval(async () => {
    try {
      const job = await getSceneGitSyncJob(jobId);
      applySyncJob(job);
      if (job.status === "succeeded" || job.status === "failed" || job.status === "canceled") {
        stopSyncPolling();
        await refresh();
        if (job.status === "succeeded") {
          uiStore.pushNotice({ tone: "success", title: "Git Scene 已同步" });
        } else {
          uiStore.pushNotice({ tone: "danger", title: "Git Scene 同步失败", body: job.error });
        }
      }
    } catch (error) {
      stopSyncPolling();
      uiStore.pushNotice({ tone: "danger", title: "同步状态读取失败", body: error instanceof Error ? error.message : "" });
    }
  }, 1500);
}

async function restoreSceneSyncState(): Promise<void> {
  const scope = currentScope.value;
  const scene = currentScene.value;
  if (!scope || !scene || scene.source !== "git" || !scene.git) {
    return;
  }
  const assetKey = scene.asset_key;
  try {
    const jobs = await listSceneGitSyncJobs(scope, assetKey);
    if (currentScene.value?.asset_key !== assetKey) {
      return;
    }
    const activeJob = jobs.find((job) => job.status === "queued" || job.status === "running");
    if (activeJob) {
      applySyncJob(activeJob);
      startSyncPolling(activeJob.job_id);
    }
  } catch (error) {
    if (currentScene.value?.asset_key === assetKey) {
      uiStore.pushNotice({
        tone: "danger",
        title: "同步记录读取失败",
        body: error instanceof Error ? error.message : "",
      });
    }
  }
}

function stopSyncPolling(): void {
  if (syncPollTimer !== null) {
    window.clearInterval(syncPollTimer);
    syncPollTimer = null;
  }
}

function resetSyncState(): void {
  stopSyncPolling();
  activeSyncJobId.value = "";
  syncJobProgress.value = 0;
  syncJobMessage.value = "";
  syncJobStatus.value = "";
}

function resetTreeState(): void {
  columns.value = [];
  selectedPathByColumn.value = {};
  selectedEntry.value = null;
  openedFile.value = null;
  fileDraft.value = "";
  fileMode.value = null;
  fileError.value = "";
  treeError.value = "";
}

async function reloadSceneTree(): Promise<void> {
  resetTreeState();
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  await loadColumn(0, "");
}

async function refreshTreeKeepingSelection(): Promise<void> {
  if (!currentScene.value) {
    return;
  }
  const paths = columns.value.map((column) => column.path);
  const selectedPath = selectedEntry.value?.path ?? "";
  columns.value = [];
  selectedPathByColumn.value = {};
  for (const [index, path] of (paths.length ? paths : [""]).entries()) {
    await loadColumn(index, path);
  }
  if (selectedPath) {
    selectedEntry.value = findLoadedEntry(selectedPath);
  }
}

async function loadColumn(index: number, path: string): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  const nextColumns = columns.value.slice(0, index + 1);
  nextColumns[index] = { path, entries: [], loading: true, error: "" };
  columns.value = nextColumns;
  treeLoading.value = true;
  treeError.value = "";
  try {
    const entries = await listSceneEntries(currentScope.value, currentScene.value.asset_key, path);
    columns.value[index] = { path, entries, loading: false, error: "" };
  } catch (error) {
    const message = error instanceof Error ? error.message : "加载 Scene 目录失败。";
    columns.value[index] = { path, entries: [], loading: false, error: message };
    treeError.value = message;
  } finally {
    treeLoading.value = false;
  }
  await nextTick();
  directoryScroller.value?.setScrollLeft(999999);
}

async function openDirectory(entry: ManagedFileEntry, columnIndex: number): Promise<void> {
  selectedEntry.value = entry;
  selectedPathByColumn.value = Object.fromEntries(
    Object.entries(selectedPathByColumn.value)
      .filter(([index]) => Number(index) < columnIndex)
      .concat([[String(columnIndex), entry.path]]),
  );
  openedFile.value = null;
  fileDraft.value = "";
  fileMode.value = null;
  await loadColumn(columnIndex + 1, entry.path);
}

async function selectFile(entry: ManagedFileEntry, columnIndex: number, mode?: "preview" | "edit"): Promise<void> {
  selectedEntry.value = entry;
  selectedPathByColumn.value = Object.fromEntries(
    Object.entries(selectedPathByColumn.value)
      .filter(([index]) => Number(index) < columnIndex)
      .concat([[String(columnIndex), entry.path]]),
  );
  columns.value = columns.value.slice(0, columnIndex + 1);
  if (mode) {
    await openFile(entry, mode);
  }
}

async function openFile(entry: ManagedFileEntry, mode: "preview" | "edit"): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  const nextMode = currentSceneReadonly.value && mode === "edit" ? "preview" : mode;
  fileLoading.value = true;
  fileError.value = "";
  fileMode.value = nextMode;
  try {
    openedFile.value = await readSceneFile(currentScope.value, currentScene.value.asset_key, entry.path);
    fileDraft.value = openedFile.value.content;
  } catch (error) {
    openedFile.value = null;
    fileDraft.value = "";
    fileError.value = error instanceof Error ? error.message : "读取文件失败。";
  } finally {
    fileLoading.value = false;
  }
}

function closeFileMode(): void {
  fileMode.value = null;
  openedFile.value = null;
  fileDraft.value = "";
  fileError.value = "";
  fileLoading.value = false;
}

async function saveOpenedFile(): Promise<void> {
  if (!currentScope.value || !currentScene.value || !openedFile.value) {
    return;
  }
  fileSaving.value = true;
  try {
    openedFile.value = await writeSceneFile({
      scope: currentScope.value,
      sceneAssetKey: currentScene.value.asset_key,
      path: openedFile.value.path,
      content: fileDraft.value,
      expectedVersion: openedFile.value.version,
    });
    fileDraft.value = openedFile.value.content;
    await refreshTreeKeepingSelection();
    uiStore.pushNotice({ tone: "success", title: "文件已保存" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "保存失败", body: error instanceof Error ? error.message : "" });
  } finally {
    fileSaving.value = false;
  }
}

async function createFileInActiveDirectory(parentPath = activeDirectoryPath.value): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  const name = await promptText("新建文件名", "index.md");
  if (!name) {
    return;
  }
  const path = joinRelativePath(parentPath, name);
  try {
    const file = await writeSceneFile({
      scope: currentScope.value,
      sceneAssetKey: currentScene.value.asset_key,
      path,
      content: "",
      expectedVersion: null,
    });
    await refreshTreeKeepingSelection();
    openedFile.value = file;
    fileDraft.value = file.content;
    fileMode.value = "edit";
    selectedEntry.value = findLoadedEntry(path);
    uiStore.pushNotice({ tone: "success", title: "文件已创建" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "创建文件失败", body: error instanceof Error ? error.message : "" });
  }
}

async function createDirectoryInActiveDirectory(parentPath = activeDirectoryPath.value): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  const name = await promptText("新建目录名", "docs");
  if (!name) {
    return;
  }
  const path = joinRelativePath(parentPath, name);
  try {
    await createSceneDirectory(currentScope.value, currentScene.value.asset_key, path);
    await refreshTreeKeepingSelection();
    uiStore.pushNotice({ tone: "success", title: "目录已创建" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "创建目录失败", body: error instanceof Error ? error.message : "" });
  }
}

function openUploadIntoActiveDirectory(parentPath = activeDirectoryPath.value): void {
  uploadTargetPath.value = parentPath;
  uploadTargetMode.value = "directory";
  openUploadDialog(uploadInput.value);
}

function openUploadReplaceFile(entry: ManagedFileEntry): void {
  uploadTargetPath.value = entry.path;
  uploadTargetMode.value = "file";
  openUploadDialog(uploadInput.value);
}

async function handleUploadFile(file: File | undefined): Promise<void> {
  if (!file || !currentScope.value || !currentScene.value) {
    return;
  }
  const targetPath = uploadTargetMode.value === "file"
    ? uploadTargetPath.value
    : joinRelativePath(uploadTargetPath.value, file.name);
  try {
    await uploadSceneFile(currentScope.value, currentScene.value.asset_key, targetPath, file);
    await refreshTreeKeepingSelection();
    uiStore.pushNotice({ tone: "success", title: "文件已上传" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "上传失败", body: error instanceof Error ? error.message : "" });
  }
}

async function handleUploadFileChange(uploadFile: UploadFile): Promise<void> {
  const file = uploadFile.raw;
  uploadInput.value?.clearFiles();
  await handleUploadFile(file);
}

function openInternalPackageReplace(entry: ManagedFileEntry): void {
  packageTargetPath.value = entry.path;
  openUploadDialog(packageInput.value);
}

async function handleInternalPackageReplaceFile(file: File | undefined): Promise<void> {
  if (!file || !currentScope.value || !currentScene.value) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".zip")) {
    uiStore.pushNotice({ tone: "warning", title: "请选择 zip 包" });
    return;
  }
  try {
    await uploadSceneDirectoryPackage(currentScope.value, currentScene.value.asset_key, packageTargetPath.value, file);
    await refreshTreeKeepingSelection();
    uiStore.pushNotice({ tone: "success", title: "目录已替换" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "替换失败", body: error instanceof Error ? error.message : "" });
  }
}

async function handleInternalPackageReplace(uploadFile: UploadFile): Promise<void> {
  const file = uploadFile.raw;
  packageInput.value?.clearFiles();
  await handleInternalPackageReplaceFile(file);
}

function openAssetPackageReplace(): void {
  openUploadDialog(assetPackageInput.value);
}

async function handleAssetPackageReplaceFile(file: File | undefined): Promise<void> {
  if (!file || !currentScope.value || !currentScene.value) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".zip")) {
    uiStore.pushNotice({ tone: "warning", title: "请选择 zip 包" });
    return;
  }
  await sceneStore.replacePackage(currentScope.value, currentScene.value.asset_key, file);
  await reloadSceneTree();
  uiStore.pushNotice({ tone: "success", title: "Scene 包已替换" });
}

async function handleAssetPackageReplace(uploadFile: UploadFile): Promise<void> {
  const file = uploadFile.raw;
  assetPackageInput.value?.clearFiles();
  await handleAssetPackageReplaceFile(file);
}

async function renameSelectedEntry(): Promise<void> {
  if (!currentScope.value || !currentScene.value || !selectedEntry.value) {
    return;
  }
  const name = await promptText("重命名", selectedEntry.value.name);
  if (!name || name === selectedEntry.value.name) {
    return;
  }
  const destination = joinRelativePath(parentRelativePath(selectedEntry.value.path), name);
  try {
    await moveScenePath(currentScope.value, currentScene.value.asset_key, selectedEntry.value.path, destination);
    await refreshTreeKeepingSelection();
    selectedEntry.value = findLoadedEntry(destination);
    uiStore.pushNotice({ tone: "success", title: "名称已更新" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "重命名失败", body: error instanceof Error ? error.message : "" });
  }
}

async function moveSelectedEntry(): Promise<void> {
  if (!currentScope.value || !currentScene.value || !selectedEntry.value) {
    return;
  }
  const destination = await promptText("移动到目标路径", selectedEntry.value.path);
  if (!destination || destination === selectedEntry.value.path) {
    return;
  }
  try {
    await moveScenePath(currentScope.value, currentScene.value.asset_key, selectedEntry.value.path, destination);
    await refreshTreeKeepingSelection();
    selectedEntry.value = findLoadedEntry(destination);
    uiStore.pushNotice({ tone: "success", title: "路径已移动" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "移动失败", body: error instanceof Error ? error.message : "" });
  }
}

async function deleteSelectedEntry(): Promise<void> {
  if (!currentScope.value || !currentScene.value || !selectedEntry.value) {
    return;
  }
  if (!await confirmDanger(`确认删除 ${selectedEntry.value.path}？`)) {
    return;
  }
  try {
    await deleteScenePath(
      currentScope.value,
      currentScene.value.asset_key,
      selectedEntry.value.path,
      selectedEntry.value.entry_type === "directory",
    );
    if (openedFile.value?.path === selectedEntry.value.path) {
      openedFile.value = null;
      fileDraft.value = "";
      fileMode.value = null;
    }
    selectedEntry.value = null;
    await refreshTreeKeepingSelection();
    uiStore.pushNotice({ tone: "warning", title: "已删除" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "删除失败", body: error instanceof Error ? error.message : "" });
  }
}

async function downloadSelectedEntry(): Promise<void> {
  if (!currentScope.value || !currentScene.value || !selectedEntry.value) {
    return;
  }
  await downloadPath(selectedEntry.value.path, selectedEntry.value.entry_type === "directory" ? `${selectedEntry.value.name}.zip` : selectedEntry.value.name);
}

async function downloadCurrentScene(): Promise<void> {
  if (!currentScene.value) {
    return;
  }
  await downloadPath("", `${currentScene.value.name || currentScene.value.asset_key}.zip`);
}

async function downloadPath(path: string, filename: string): Promise<void> {
  if (!currentScope.value || !currentScene.value) {
    return;
  }
  try {
    const blob = await downloadScenePath(currentScope.value, currentScene.value.asset_key, path);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "下载失败", body: error instanceof Error ? error.message : "" });
  }
}

function sceneRootActions(): SceneAction[] {
  if (currentSceneReadonly.value) {
    return [
      action("metadata", "元信息", CheckCircle2, "secondary"),
      action("sync-git-scene", "同步 Git", GitBranch, "primary"),
      action("download", "下载 Scene", Download, "secondary"),
      action("delete-scene", "删除 Scene", Trash2, "danger", true),
    ];
  }
  return [
    action("metadata", "元信息", CheckCircle2, "secondary"),
    action("replace-asset-package", "上传替换", PackageOpen, "secondary"),
    action("download", "下载 Scene", Download, "secondary"),
    action("create-directory", "新建目录", FolderPlus, "secondary"),
    action("create-file", "新建文件", FilePlus, "primary"),
    action("upload-file", "上传文件", Upload, "secondary", true),
    action("delete-scene", "删除 Scene", Trash2, "danger", true),
  ];
}

function sceneBrowserActions(): SceneAction[] {
  return [
    action("upload-scene-package", "上传 Scene 包", Upload, "secondary"),
    action("create-git-scene", "新建 Git Scene", GitBranch, "secondary"),
    action("create-scene", "新建 Scene", Plus, "primary"),
  ];
}

function entryActions(entry: ManagedFileEntry): SceneAction[] {
  if (currentSceneReadonly.value) {
    return [
      ...(entry.entry_type === "file" ? [action("preview", "预览", Eye, "secondary")] : []),
      action("download", "下载", Download, "secondary"),
    ];
  }
  if (entry.entry_type === "file") {
    return [
      action("preview", "预览", Eye, "secondary"),
      action("edit", "编辑", Pencil, "primary"),
      action("download", "下载", Download, "secondary"),
      action("replace-file", "上传覆盖", Upload, "secondary"),
      action("rename", "重命名", Pencil, "secondary"),
      action("move", "移动", Folder, "secondary"),
      action("delete", "删除", Trash2, "danger"),
    ];
  }
  return [
    action("create-file", "新建文件", FilePlus, "primary"),
    action("create-directory", "新建目录", FolderPlus, "secondary"),
    action("download", "下载", Download, "secondary"),
    action("replace-directory-package", "包替换", PackageOpen, "secondary"),
    action("rename", "重命名", Pencil, "secondary"),
    action("move", "移动", Folder, "secondary"),
    action("delete", "删除", Trash2, "danger"),
  ];
}

function directoryEmptyActions(): SceneAction[] {
  if (!currentScene.value || currentSceneReadonly.value) {
    return [];
  }
  return [
    action("create-file", "新建文件", FilePlus, "primary"),
    action("create-directory", "新建目录", FolderPlus, "secondary"),
    action("upload-file", "上传文件", Upload, "secondary"),
  ];
}

function action(
  id: SceneActionId,
  label: string,
  icon: SceneAction["icon"],
  tone: SceneAction["tone"],
  wide = false,
): SceneAction {
  return { id, label, icon, tone, wide };
}

async function runSceneAction(
  actionId: SceneActionId,
  entry: ManagedFileEntry | null = selectedEntry.value,
  parentPath = activeDirectoryPath.value,
): Promise<void> {
  closeContextMenu();
  if (actionId === "create-scene") {
    openCreate();
    return;
  }
  if (actionId === "create-git-scene") {
    openCreateGit();
    return;
  }
  if (actionId === "upload-scene-package") {
    openCreateFromPackage();
    return;
  }
  if (actionId === "metadata") {
    openMetadata();
    return;
  }
  if (actionId === "sync-git-scene") {
    await syncCurrentGitScene();
    return;
  }
  if (actionId === "replace-asset-package") {
    openAssetPackageReplace();
    return;
  }
  if (actionId === "delete-scene") {
    await removeCurrent();
    return;
  }
  if (actionId === "download" && !entry) {
    await downloadCurrentScene();
    return;
  }
  if (actionId === "create-file") {
    await createFileInActiveDirectory(parentPath);
    return;
  }
  if (actionId === "create-directory") {
    await createDirectoryInActiveDirectory(parentPath);
    return;
  }
  if (actionId === "upload-file") {
    openUploadIntoActiveDirectory(parentPath);
    return;
  }
  if (!entry) {
    return;
  }
  selectedEntry.value = entry;
  if (actionId === "preview") {
    await openFile(entry, "preview");
    return;
  }
  if (actionId === "edit") {
    await openFile(entry, "edit");
    return;
  }
  if (actionId === "download") {
    await downloadSelectedEntry();
    return;
  }
  if (actionId === "replace-file") {
    openUploadReplaceFile(entry);
    return;
  }
  if (actionId === "replace-directory-package") {
    openInternalPackageReplace(entry);
    return;
  }
  if (actionId === "rename") {
    await renameSelectedEntry();
    return;
  }
  if (actionId === "move") {
    await moveSelectedEntry();
    return;
  }
  if (actionId === "delete") {
    await deleteSelectedEntry();
  }
}

async function runContextMenuAction(actionId: SceneActionId): Promise<void> {
  const menu = contextMenu.value;
  if (menu.targetScene && selectedAssetKey.value !== menu.targetScene.asset_key) {
    await openScene(menu.targetScene);
  }
  if (!menu.targetEntry && menu.parentPath) {
    selectedEntry.value = findLoadedEntry(menu.parentPath);
  }
  await runSceneAction(actionId, menu.targetEntry, menu.parentPath);
}

async function fitContextMenu(anchorX: number, anchorY: number): Promise<void> {
  await nextTick();
  const element = contextMenuElement.value;
  if (!element || !contextMenu.value.open || contextMenu.value.x !== anchorX || contextMenu.value.y !== anchorY) return;
  const rect = element.getBoundingClientRect();
  const position = fitFloatingElementToViewport(
    anchorX,
    anchorY,
    rect.width,
    rect.height,
    window.innerWidth,
    window.innerHeight,
  );
  contextMenu.value = { ...contextMenu.value, ...position };
}

function handleSceneContextMenu(event: MouseEvent, scene: WorkspaceSceneAsset): void {
  event.preventDefault();
  event.stopPropagation();
  contextMenu.value = {
    open: true,
    x: event.clientX,
    y: event.clientY,
    parentPath: "",
    targetEntry: null,
    targetScene: scene,
    assetBrowser: false,
  };
  void fitContextMenu(event.clientX, event.clientY);
}

function handleSceneBrowserContextMenu(event: MouseEvent): void {
  const actions = sceneBrowserActions();
  if (!actions.length) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  contextMenu.value = {
    open: true,
    x: event.clientX,
    y: event.clientY,
    parentPath: "",
    targetEntry: null,
    targetScene: null,
    assetBrowser: true,
  };
  void fitContextMenu(event.clientX, event.clientY);
}

function handleEntryContextMenu(event: MouseEvent, entry: ManagedFileEntry): void {
  const actions = entryActions(entry);
  if (!actions.length) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  selectedEntry.value = entry;
  contextMenu.value = {
    open: true,
    x: event.clientX,
    y: event.clientY,
    parentPath: entry.entry_type === "directory" ? entry.path : parentRelativePath(entry.path),
    targetEntry: entry,
    targetScene: null,
    assetBrowser: false,
  };
  void fitContextMenu(event.clientX, event.clientY);
}

function handleColumnContextMenu(event: MouseEvent, column: FinderColumn): void {
  const actions = directoryEmptyActions();
  if (!actions.length) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  selectedEntry.value = column.path ? findLoadedEntry(column.path) : null;
  contextMenu.value = {
    open: true,
    x: event.clientX,
    y: event.clientY,
    parentPath: column.path,
    targetEntry: null,
    targetScene: null,
    assetBrowser: false,
  };
  void fitContextMenu(event.clientX, event.clientY);
}

function closeContextMenu(): void {
  contextMenu.value = {
    ...contextMenu.value,
    open: false,
    targetEntry: null,
    targetScene: null,
    assetBrowser: false,
  };
}

function findLoadedEntry(path: string): ManagedFileEntry | null {
  for (const column of columns.value) {
    const entry = column.entries.find((item) => item.path === path);
    if (entry) {
      return entry;
    }
  }
  return null;
}

function fileKind(entry: ManagedFileEntry): string {
  if (entry.entry_type === "directory") {
    return "目录";
  }
  const lowerName = entry.name.toLowerCase();
  if (lowerName.endsWith(".md") || lowerName.endsWith(".markdown")) return "Markdown";
  if (lowerName.endsWith(".json")) return "JSON";
  if (lowerName.endsWith(".txt")) return "Text";
  return "Text";
}
</script>

<template>
  <div class="skills-page skill-manager-page" @click="closeContextMenu">
    <AppPanel class="finder-card skills-finder-card" :class="{ 'inline-editing': fileMode }">
      <header class="finder-toolbar skills-finder-toolbar">
        <el-button v-if="fileMode" class="inline-editor-back" :icon="ArrowLeft" @click="closeFileMode">
          返回
        </el-button>
        <div class="finder-heading" :class="{ 'inline-file-heading': fileMode }">
          <h2>{{ fileMode ? inlineFileName : "场景管理" }}</h2>
          <p v-if="fileMode" class="inline-file-path" :title="inlineFilePathLabel">{{ inlineFilePathLabel }}</p>
          <p v-else>Scene 本体元信息由数据库管理，目录内部文件按文件树维护。</p>
        </div>
        <div v-if="!fileMode" class="finder-actions skills-toolbar-actions">
          <el-button
            class="scene-toolbar-button"
            :icon="RefreshCw"
            :disabled="sceneRefs.loading.value"
            @click="refresh"
          >
            刷新
          </el-button>
          <el-button
            class="scene-toolbar-button"
            :icon="PackagePlus"
            :disabled="!currentScope || sceneRefs.saving.value"
            @click="openCreateFromPackage"
          >
            上传 Scene 包
          </el-button>
          <el-button
            class="scene-toolbar-button primary"
            type="primary"
            :icon="Plus"
            :disabled="!currentScope"
            @click="openCreate"
          >
            新建 Scene
          </el-button>
        </div>
        <el-button
          v-else
          class="inline-editor-save"
          type="primary"
          :icon="Save"
          :disabled="!canSaveFile"
          @click="saveOpenedFile"
        >
          {{ fileSaving ? "保存中" : "保存" }}
        </el-button>
      </header>

      <div class="skills-finder-body">
        <div v-if="!fileMode && (sceneRefs.errorMessage.value || treeError)" class="finder-alerts">
          <StatusBanner
            v-if="sceneRefs.errorMessage.value"
            tone="danger"
            title="Scene 操作失败"
            :body="sceneRefs.errorMessage.value"
          />
          <StatusBanner v-if="treeError" tone="danger" title="目录加载失败" :body="treeError" />
        </div>

        <div v-if="fileMode" class="inline-file-editor" :class="{ 'markdown-mode': openedFileMarkdown }">
          <LoadingBlock v-if="fileLoading" title="正在读取文件" body="请稍候。" />
          <StatusBanner v-else-if="fileError" tone="danger" title="读取失败" :body="fileError" />
          <template v-else-if="openedFile">
            <div class="inline-file-meta">
              <span>{{ fileMode === "preview" ? "预览模式" : "编辑模式" }}</span>
              <span>修改时间 {{ formatDate(openedFile.modified_at ?? undefined) }}</span>
              <strong>{{ openedFileDirty ? "有未保存变更" : "已同步" }}</strong>
            </div>
            <MarkdownEditor
              v-if="openedFileMarkdown"
              v-model="fileDraft"
              :readonly="fileMode !== 'edit'"
            />
            <CodeEditor
              v-else
              v-model="fileDraft"
              :filename="openedFile.path"
              :readonly="fileMode !== 'edit'"
            />
          </template>
        </div>

        <el-container v-else class="skill-finder-layout finder-layout">
          <el-aside class="skill-browser-column" width="25%">
            <el-header class="finder-column-header" height="42px">
              <span>场景浏览</span>
              <el-tag size="small" type="info" effect="plain">{{ filteredScenes.length }} 项</el-tag>
            </el-header>
            <el-input v-model="keyword" class="skill-browser-search" type="search" placeholder="搜索 Scene" clearable>
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          <el-scrollbar class="skill-browser-list" @contextmenu="handleSceneBrowserContextMenu">
              <el-skeleton v-if="sceneRefs.loading.value" :rows="5" animated class="finder-column-loading" />
              <el-empty
                v-else-if="!filteredScenes.length"
                class="finder-column-empty"
                description="新建后会写入数据库元信息，并创建对应 .scenes 目录。"
              >
                <template #image>
                  <el-icon class="finder-empty-symbol"><Layers3 /></el-icon>
                </template>
                <template #description>
                  <strong>暂无 Scene</strong>
                  <p>新建后会写入数据库元信息，并创建对应 .scenes 目录。</p>
                </template>
              </el-empty>
              <el-space v-else class="finder-entry-list" direction="vertical" fill :size="2">
                <el-button
                  v-for="scene in filteredScenes"
                  :key="scene.asset_key"
                  class="finder-row skill-root-row"
                  text
                  :class="{ selected: selectedAssetKey === scene.asset_key }"
                  @click="openScene(scene)"
                  @contextmenu="handleSceneContextMenu($event, scene)"
                >
                  <el-icon class="finder-entry-icon skill"><Layers3 /></el-icon>
                  <span class="finder-entry-text">
                    <span class="scene-list-title">
                      <strong>{{ scene.name }}</strong>
                      <span v-if="scene.source === 'git'" class="scene-list-tag">Git</span>
                    </span>
                    <small>{{ scene.description || "暂无描述" }}</small>
                  </span>
                  <el-icon class="finder-chevron"><ChevronRight /></el-icon>
                </el-button>
              </el-space>
            </el-scrollbar>
          </el-aside>

          <el-main class="finder-directory-region">
            <el-scrollbar
              ref="directoryScroller"
              class="finder-directory-scroller skill-directory-scroller"
              view-class="finder-column-strip"
              always
            >
            <el-aside
              v-for="(column, columnIndex) in columns"
              :key="`${column.path || 'root'}-${columnIndex}`"
              class="finder-column"
              width="50%"
            >
              <el-header class="finder-column-header" height="42px">
                <span>{{ column.path ? column.path.split('/').pop() : currentScene?.name }}</span>
                <el-tag size="small" type="info" effect="plain">{{ column.entries.length }} 项</el-tag>
              </el-header>

              <el-scrollbar class="finder-column-body" @contextmenu="handleColumnContextMenu($event, column)">
                <el-skeleton v-if="column.loading" :rows="5" animated class="finder-column-loading" />
                <el-alert
                  v-else-if="column.error"
                  title="目录加载失败"
                  :description="column.error"
                  type="error"
                  show-icon
                  :closable="false"
                />
                <el-empty
                  v-else-if="!column.entries.length"
                  class="finder-column-empty"
                  description="可以在当前目录新建文件或目录。"
                >
                  <template #image>
                    <el-icon class="finder-empty-symbol"><Folder /></el-icon>
                  </template>
                  <template #description>
                    <strong>目录为空</strong>
                    <p>可以在当前目录新建文件或目录。</p>
                  </template>
                </el-empty>

                <el-space v-else class="finder-entry-list" direction="vertical" fill :size="2">
                  <el-button
                    v-for="entry in column.entries"
                    :key="entry.path"
                    class="finder-row"
                    text
                    :class="{
                      selected: selectedPathByColumn[columnIndex] === entry.path,
                      active: selectedEntry?.path === entry.path,
                    }"
                    @click="entry.entry_type === 'directory' ? openDirectory(entry, columnIndex) : selectFile(entry, columnIndex)"
                    @dblclick="entry.entry_type === 'file' && selectFile(entry, columnIndex, 'edit')"
                    @contextmenu="handleEntryContextMenu($event, entry)"
                  >
                    <el-icon class="finder-entry-icon" :class="{ directory: entry.entry_type === 'directory', file: entry.entry_type !== 'directory' }">
                      <Folder v-if="entry.entry_type === 'directory'" />
                      <File v-else />
                    </el-icon>
                    <span class="finder-entry-text">
                      <strong>{{ entry.name }}</strong>
                      <small>{{ entry.entry_type === 'directory' ? '目录' : formatBytes(entry.size_bytes) }}</small>
                    </span>
                    <el-icon v-if="entry.entry_type === 'directory'" class="finder-chevron"><ChevronRight /></el-icon>
                  </el-button>
                </el-space>
              </el-scrollbar>
            </el-aside>

            <el-aside v-if="currentScene && !columns.length" class="finder-column" width="50%">
              <el-header class="finder-column-header" height="42px">
                <span>{{ currentScene.name }}</span>
                <el-tag size="small" type="info" effect="plain">0 项</el-tag>
              </el-header>
              <el-scrollbar class="finder-column-body">
                <el-skeleton v-if="treeLoading" :rows="5" animated class="finder-column-loading" />
              </el-scrollbar>
            </el-aside>
            </el-scrollbar>
          </el-main>

          <el-aside class="finder-detail-column skill-detail-column" width="25%">
            <el-header class="detail-panel-header" height="38px">
              <h3>详情</h3>
              <el-tag v-if="selectedEntry || currentScene" size="small" type="primary" effect="light">
                {{ selectedEntry ? selectedEntry.entry_type === "directory" ? "目录" : "文件" : "Scene" }}
              </el-tag>
            </el-header>

            <el-empty
              v-if="!currentScene"
              class="finder-detail-empty"
              description="左侧选择 Scene 后，在中间浏览目录，在这里执行本体与文件操作。"
            >
              <template #image>
                <el-icon class="finder-empty-symbol"><Layers3 /></el-icon>
              </template>
              <template #description>
                <strong>选择一个 Scene</strong>
                <p>左侧选择 Scene 后，在中间浏览目录，在这里执行本体与文件操作。</p>
              </template>
            </el-empty>

            <el-scrollbar v-else class="file-detail-panel">
              <StatusBanner
                v-if="syncInProgress"
                class="scene-sync-banner"
                tone="warning"
                title="Git Scene 同步中"
                :body="syncBannerBody"
              />
              <div class="file-detail-lockup">
                <el-icon v-if="!selectedEntry" class="file-detail-icon skill"><Layers3 /></el-icon>
                <el-icon v-else-if="selectedEntry.entry_type === 'directory'" class="file-detail-icon"><Folder /></el-icon>
                <el-icon v-else class="file-detail-icon file"><File /></el-icon>
                <div>
                  <h3>{{ selectedEntry?.name || currentScene.name }}</h3>
                  <p>{{ selectedEntry ? selectedEntry.entry_type === "directory" ? "文件夹" : `${fileKind(selectedEntry)} 文件` : currentSceneReadonly ? "Git Scene 只读" : "Scene 本体" }}</p>
                </div>
              </div>

              <div v-if="!selectedEntry && currentSceneGit" class="scene-git-status">
                <div>
                  <span>同步状态</span>
                  <strong>{{ syncProgressLabel }}</strong>
                </div>
                <p>
                  {{
                    syncInProgress
                      ? (syncJobMessage || "正在同步")
                      : currentSceneGit.last_synced_at
                        ? `上次同步 ${formatDate(currentSceneGit.last_synced_at)}`
                        : "尚未同步"
                  }}
                </p>
              </div>

              <el-descriptions class="file-detail-list" :column="1" size="small" border>
                <template v-if="!selectedEntry">
                  <el-descriptions-item label="目录">{{ currentScene.path }}</el-descriptions-item>
                  <el-descriptions-item label="来源">{{ currentScene.source === "git" ? "Git 仓库" : currentScene.source }}</el-descriptions-item>
                  <el-descriptions-item label="状态">{{ assetStatusLabel(currentScene.status) }}</el-descriptions-item>
                  <el-descriptions-item label="绑定 Skill">{{ boundSkill?.name || "未绑定" }}</el-descriptions-item>
                  <template v-if="currentSceneGit">
                    <el-descriptions-item label="仓库">
                      {{ currentGitRepository?.display_name || currentGitRepository?.alias || currentSceneGit.git_repository_id }}
                    </el-descriptions-item>
                    <el-descriptions-item v-if="currentGitRepository" label="仓库地址">
                      {{ currentGitRepository.repo_url }}
                    </el-descriptions-item>
                    <el-descriptions-item label="分支">{{ currentSceneGit.branch || currentSceneGit.ref || "-" }}</el-descriptions-item>
                    <el-descriptions-item label="仓库路径">{{ gitSubdirLabel(currentSceneGit.subdir) }}</el-descriptions-item>
                    <el-descriptions-item label="自动同步">
                      <span class="scene-git-tag" :class="{ muted: !currentSceneGit.auto_sync_enabled }">
                        {{ currentSceneGit.auto_sync_enabled ? currentSceneGit.daily_sync_time : "关闭" }}
                      </span>
                    </el-descriptions-item>
                  </template>
                  <el-descriptions-item label="描述">{{ currentScene.description || "-" }}</el-descriptions-item>
                </template>
                <template v-else>
                  <template v-for="[label, value] in selectedEntryMeta" :key="label">
                    <el-descriptions-item :label="label">{{ value }}</el-descriptions-item>
                  </template>
                </template>
              </el-descriptions>

              <div class="detail-action-section">
                <h4>{{ selectedEntry ? "文件操作" : "Scene 本体操作" }}</h4>
                <div class="file-detail-file-actions">
                  <el-button
                    v-for="actionItem in detailActions"
                    :key="actionItem.id"
                    :type="actionItem.tone === 'primary' ? 'primary' : 'default'"
                    :class="[
                      actionItem.tone === 'primary' ? 'file-primary-action' : 'file-secondary-action',
                      { danger: actionItem.tone === 'danger', 'full-width': actionItem.wide },
                    ]"
                    @click="runSceneAction(actionItem.id)"
                  >
                    <el-icon><component :is="actionItem.icon" /></el-icon>
                    {{ actionItem.label }}
                  </el-button>
                </div>
              </div>
            </el-scrollbar>
          </el-aside>
        </el-container>
      </div>
    </AppPanel>

    <div
      v-if="contextMenu.open && contextMenuActions.length"
      ref="contextMenuElement"
      class="admin-context-menu"
      :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      @click.stop
    >
      <el-button
        v-for="actionItem in contextMenuActions"
        :key="actionItem.id"
        size="small"
        text
        type="default"
        :class="{ danger: actionItem.tone === 'danger' }"
        @click="runContextMenuAction(actionItem.id)"
      >
        <el-icon class="context-menu-icon" aria-hidden="true">
          <component :is="actionItem.icon" />
        </el-icon>
        <span class="context-menu-label">
          {{ actionItem.label }}
        </span>
      </el-button>
    </div>

    <FormDrawer
      :open="createOpen"
      :title="createMode === 'git' ? '新建 Git Scene' : '新建 Scene'"
      :subtitle="createMode === 'git'
        ? 'Git Scene 内容由仓库同步生成，创建后不支持手动编辑目录或文件。'
        : 'Scene 名称作为展示名，asset_key 由后端生成，内容目录由 Server 管理。'"
      :saving="sceneRefs.saving.value"
      :size="createMode === 'git' ? 'wide' : 'default'"
      submit-text="创建"
      @close="closeCreate"
      @submit="submitCreate"
    >
      <div class="asset-form">
        <FieldInput v-model="form.name" label="Scene 名称" placeholder="network-check" />
        <FieldInput v-model="form.description" label="描述" placeholder="描述场景用途" />
        <label>
          <span>状态</span>
          <el-select v-model="form.status" class="asset-form-select">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </label>
        <label>
          <span>绑定 Skill</span>
          <el-select v-model="form.requiredSkillAssetKey" class="asset-form-select" filterable clearable placeholder="不绑定">
            <el-option label="不绑定" value="" />
            <el-option v-for="skill in skillOptions" :key="skill.asset_key" :label="skill.name" :value="skill.asset_key" />
          </el-select>
        </label>
        <template v-if="createMode === 'git'">
          <el-alert
            v-if="!availableGitRepositories.length"
            type="warning"
            :closable="false"
            show-icon
            title="当前触点没有可用 Git 仓库，请先在“场景 Git 授权”中分配"
          />
          <label>
            <span>Git 仓库</span>
            <el-select
              v-model="form.gitRepositoryId"
              class="asset-form-select"
              filterable
              placeholder="选择当前触点可用的仓库"
            >
              <el-option
                v-for="repository in availableGitRepositories"
                :key="repository.id"
                :label="repository.display_name || repository.alias"
                :value="repository.id"
              >
                <el-space :size="12">
                  <span>{{ repository.display_name || repository.alias }}</span>
                  <el-text size="small" type="info">{{ repository.repo_url }}</el-text>
                </el-space>
              </el-option>
            </el-select>
          </label>
          <div class="asset-form-grid">
            <FieldInput v-model="form.branch" label="分支" placeholder="留空则使用仓库默认分支" />
            <FieldInput v-model="form.ref" label="指定 ref" placeholder="可选，优先于分支" />
          </div>
          <FieldInput v-model="form.subdir" label="仓库子目录" placeholder="可选，例如 scenes/default" />
          <el-checkbox v-model="form.autoSyncEnabled" class="asset-form-check">启用每日自动同步</el-checkbox>
          <div class="asset-form-grid">
            <FieldInput v-model="form.dailySyncTime" label="每日同步时间" type="time" />
          </div>
        </template>
      </div>
    </FormDrawer>

    <FormDrawer
      :open="metadataOpen"
      :title="metadataForm.isGit ? '编辑 Git Scene 元信息' : '编辑 Scene 元信息'"
      :subtitle="metadataForm.isGit
        ? 'Git Scene 内容由仓库同步，元信息和同步配置写入数据库。'
        : '元信息写入数据库；内部文件与子目录只维护在文件系统。'"
      :saving="sceneRefs.saving.value"
      :size="metadataForm.isGit ? 'wide' : 'default'"
      @close="metadataOpen = false"
      @submit="submitMetadata"
    >
      <div class="asset-form">
        <FieldInput v-model="metadataForm.name" label="Scene 名称" />
        <FieldInput v-model="metadataForm.description" label="描述" />
        <label>
          <span>状态</span>
          <el-select v-model="metadataForm.status" class="asset-form-select">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </label>
        <label>
          <span>绑定 Skill</span>
          <el-select v-model="metadataForm.requiredSkillAssetKey" class="asset-form-select" filterable clearable placeholder="不绑定">
            <el-option label="不绑定" value="" />
            <el-option v-for="skill in skillOptions" :key="skill.asset_key" :label="skill.name" :value="skill.asset_key" />
          </el-select>
        </label>
        <template v-if="metadataForm.isGit">
          <div class="asset-form-section">
            <span>Git 配置</span>
          </div>
          <label>
            <span>Git 仓库</span>
            <el-select
              v-model="metadataForm.gitRepositoryId"
              class="asset-form-select"
              filterable
              placeholder="选择当前触点可用的仓库"
            >
              <el-option
                v-for="repository in availableGitRepositories"
                :key="repository.id"
                :label="repository.display_name || repository.alias"
                :value="repository.id"
              >
                <el-space :size="12">
                  <span>{{ repository.display_name || repository.alias }}</span>
                  <el-text size="small" type="info">{{ repository.repo_url }}</el-text>
                </el-space>
              </el-option>
            </el-select>
          </label>
          <div class="asset-form-grid">
            <FieldInput v-model="metadataForm.branch" label="分支" placeholder="master" />
            <FieldInput v-model="metadataForm.ref" label="指定 ref" placeholder="可选，优先于分支" />
          </div>
          <FieldInput v-model="metadataForm.subdir" label="仓库子目录" placeholder="空值表示仓库根目录" />
          <el-checkbox v-model="metadataForm.autoSyncEnabled" class="asset-form-check">启用每日自动同步</el-checkbox>
          <div class="asset-form-grid">
            <FieldInput v-model="metadataForm.dailySyncTime" label="每日同步时间" type="time" />
          </div>
        </template>
      </div>
    </FormDrawer>

    <el-upload ref="uploadInput" class="hidden-upload" action="#" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleUploadFileChange" />
    <el-upload ref="packageInput" class="hidden-upload" action="#" accept=".zip,application/zip" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleInternalPackageReplace" />
    <el-upload ref="assetPackageInput" class="hidden-upload" action="#" accept=".zip,application/zip" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleAssetPackageReplace" />
    <el-upload ref="createPackageInput" class="hidden-upload" action="#" accept=".zip,application/zip" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleCreatePackage" />
  </div>
</template>
