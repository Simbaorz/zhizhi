<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import {
  ArrowLeft,
  ArrowRight as ChevronRight,
  Box as PackageOpen,
  Box as PackagePlus,
  CircleCheck as CheckCircle2,
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
  createSkillDirectory,
  deleteSkillPath,
  downloadSkillPath,
  listSkillEntries,
  moveSkillPath,
  readSkillFile,
  uploadSkillFile,
  uploadSkillPackage,
  writeSkillFile,
} from "@/api/admin";
import AppPanel from "@/components/AppPanel.vue";
import CodeEditor from "@/components/CodeEditor.vue";
import FieldInput from "@/components/FieldInput.vue";
import FormDrawer from "@/components/FormDrawer.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import MarkdownEditor from "@/components/MarkdownEditor.vue";
import StatusBanner from "@/components/StatusBanner.vue";
import { useScopeStore } from "@/stores/scope";
import { useSkillStore } from "@/stores/skill";
import { useUiStore } from "@/stores/ui";
import type { ManagedFileEntry, ManagedTextFile, WorkspaceSkillAsset } from "@/types/admin";
import { formatBytes, formatDate } from "@/utils/format";
import { fitFloatingElementToViewport } from "@/utils/floatingPosition";
import { joinRelativePath, parentRelativePath } from "@/utils/path";

interface FinderColumn {
  path: string;
  entries: ManagedFileEntry[];
  loading: boolean;
  error: string;
}

type SkillActionId =
  | "create-skill"
  | "upload-skill-package"
  | "metadata"
  | "replace-asset-package"
  | "create-file"
  | "create-directory"
  | "upload-file"
  | "delete-skill"
  | "preview"
  | "edit"
  | "download"
  | "replace-file"
  | "replace-directory-package"
  | "rename"
  | "move"
  | "delete";

interface SkillAction {
  id: SkillActionId;
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
  targetSkill: WorkspaceSkillAsset | null;
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
const skillStore = useSkillStore();
const uiStore = useUiStore();

const scopeRefs = storeToRefs(scopeStore);
const skillRefs = storeToRefs(skillStore);

const createOpen = ref(false);
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
const contextMenu = ref<ContextMenuState>({
  open: false,
  x: 0,
  y: 0,
  parentPath: "",
  targetEntry: null,
  targetSkill: null,
  assetBrowser: false,
});

const form = reactive({
  name: "",
  description: "",
  status: "enabled",
  content: defaultSkillContent("skill-name"),
});

const metadataForm = reactive({
  name: "",
  description: "",
  status: "enabled",
});

const currentScope = computed(() => scopeRefs.selectedAssetTenantScope.value);
const currentSkill = computed(() => skillRefs.currentSkill.value);
const currentSkillRoot = computed(() => currentSkill.value?.path ?? "");
const filteredSkills = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  if (!text) {
    return skillRefs.skills.value;
  }
  return skillRefs.skills.value.filter((skill) =>
    [skill.name, skill.asset_key, skill.description].some((value) => value.toLowerCase().includes(text)),
  );
});
const selectedAssetKey = computed(() => currentSkill.value?.asset_key ?? "");
const activeDirectoryPath = computed(() => {
  if (selectedEntry.value?.entry_type === "directory") {
    return selectedEntry.value.path;
  }
  if (selectedEntry.value?.entry_type === "file") {
    return parentRelativePath(selectedEntry.value.path);
  }
  return columns.value[columns.value.length - 1]?.path || currentSkillRoot.value;
});
const openedFileDirty = computed(() => openedFile.value !== null && fileDraft.value !== openedFile.value.content);
const canSaveFile = computed(
  () => fileMode.value === "edit" && openedFileDirty.value && !fileSaving.value && !fileLoading.value,
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

function assetStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    enabled: "启用",
    disabled: "停用",
    deleted: "已删除",
  };
  return labels[status] ?? status;
}

const detailActions = computed(() => {
  if (!currentSkill.value) {
    return [];
  }
  return selectedEntry.value ? entryActions(selectedEntry.value) : skillRootActions();
});
const contextMenuActions = computed(() => {
  const menu = contextMenu.value;
  if (menu.assetBrowser) {
    return skillBrowserActions();
  }
  if (menu.targetSkill) {
    return skillRootActions();
  }
  if (menu.targetEntry) {
    return entryActions(menu.targetEntry);
  }
  return directoryEmptyActions(menu.parentPath);
});

watch(
  () => currentScope.value,
  async (scope) => {
    if (scope) {
      skillStore.clearCurrentSkill();
      resetTreeState();
      await skillStore.loadSkills(scope);
    } else {
      skillStore.reset();
      resetTreeState();
    }
  },
  { immediate: true },
);

function defaultSkillContent(skillName: string): string {
  return `---
name: ${JSON.stringify(skillName)}
description: ${JSON.stringify("描述这个 Skill 的用途和能力边界。")}
when_to_use: ${JSON.stringify("描述这个 Skill 什么时候应该被使用。")}
---

# ${skillName}

## 适用场景
描述这个 Skill 什么时候应该被使用。

## 操作规范
- 写清楚输入、处理步骤和输出要求。
- 明确边界条件和禁止事项。
`;
}

function resetCreateForm(): void {
  form.name = "";
  form.description = "";
  form.status = "enabled";
  form.content = defaultSkillContent("skill-name");
}

function openCreate(): void {
  resetCreateForm();
  createOpen.value = true;
}

function closeCreate(): void {
  createOpen.value = false;
  resetCreateForm();
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

async function submitCreate(): Promise<void> {
  if (!currentScope.value) {
    return;
  }
  const name = form.name.trim();
  if (!name) {
    uiStore.pushNotice({ tone: "warning", title: "请填写 Skill 名称" });
    return;
  }
  const content = form.content === defaultSkillContent("skill-name") ? defaultSkillContent(name) : form.content;
  await skillStore.createNewSkill({
    scope: currentScope.value,
    name,
    description: form.description.trim(),
    status: form.status,
    content,
  });
  closeCreate();
  await reloadSkillTree();
  uiStore.pushNotice({ tone: "success", title: "Skill 已创建" });
}

async function openSkill(skill: WorkspaceSkillAsset): Promise<void> {
  if (!currentScope.value) {
    return;
  }
  resetTreeState();
  await skillStore.openSkill(currentScope.value, skill.asset_key);
  await reloadSkillTree();
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
    await skillStore.createFromPackage(currentScope.value, name, file);
    await reloadSkillTree();
    uiStore.pushNotice({ tone: "success", title: "Skill 包已上传" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "上传 Skill 包失败", body: error instanceof Error ? error.message : "" });
  }
}

async function handleCreatePackage(uploadFile: UploadFile): Promise<void> {
  const file = uploadFile.raw;
  createPackageInput.value?.clearFiles();
  await handleCreatePackageFile(file);
}

function openMetadata(): void {
  const skill = currentSkill.value;
  if (!skill) {
    return;
  }
  metadataForm.name = skill.name;
  metadataForm.description = skill.description;
  metadataForm.status = skill.status;
  metadataOpen.value = true;
}

async function submitMetadata(): Promise<void> {
  if (!currentScope.value || !currentSkill.value) {
    return;
  }
  const previousAssetKey = currentSkill.value.asset_key;
  await skillStore.updateCurrentMetadata(currentScope.value, {
    name: metadataForm.name.trim(),
    description: metadataForm.description.trim(),
    status: metadataForm.status,
  });
  metadataOpen.value = false;
  const refreshed = skillRefs.skills.value.find((skill) => skill.asset_key === previousAssetKey);
  if (refreshed) {
    await skillStore.openSkill(currentScope.value, refreshed.asset_key);
  }
  await reloadSkillTree();
  uiStore.pushNotice({ tone: "success", title: "Skill 元信息已更新" });
}

async function removeCurrent(): Promise<void> {
  if (!currentScope.value || !currentSkill.value) {
    return;
  }
  const skill = currentSkill.value;
  if (!await confirmDanger(`确认删除 Skill：${skill.name}？`)) {
    return;
  }
  await skillStore.removeSkill(currentScope.value, skill.asset_key);
  resetTreeState();
  uiStore.pushNotice({ tone: "success", title: "Skill 已删除" });
}

async function refresh(): Promise<void> {
  if (!currentScope.value) {
    return;
  }
  await skillStore.loadSkills(currentScope.value);
  if (currentSkill.value) {
    await reloadSkillTree();
  }
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

async function reloadSkillTree(): Promise<void> {
  resetTreeState();
  if (!currentScope.value || !currentSkillRoot.value) {
    return;
  }
  await loadColumn(0, currentSkillRoot.value);
}

async function refreshTreeKeepingSelection(): Promise<void> {
  const paths = columns.value.map((column) => column.path);
  const selectedPath = selectedEntry.value?.path ?? "";
  columns.value = [];
  selectedPathByColumn.value = {};
  for (const [index, path] of (paths.length ? paths : [currentSkillRoot.value]).entries()) {
    await loadColumn(index, path);
  }
  if (selectedPath) {
    selectedEntry.value = findLoadedEntry(selectedPath);
  }
}

async function loadColumn(index: number, path: string): Promise<void> {
  if (!currentScope.value) {
    return;
  }
  const nextColumns = columns.value.slice(0, index + 1);
  nextColumns[index] = { path, entries: [], loading: true, error: "" };
  columns.value = nextColumns;
  treeLoading.value = true;
  treeError.value = "";
  try {
    const entries = await listSkillEntries(currentScope.value, path);
    columns.value[index] = { path, entries, loading: false, error: "" };
  } catch (error) {
    const message = error instanceof Error ? error.message : "加载 Skill 目录失败。";
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
  if (!currentScope.value) {
    return;
  }
  fileLoading.value = true;
  fileError.value = "";
  fileMode.value = mode;
  try {
    openedFile.value = await readSkillFile(currentScope.value, entry.path);
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
  if (!currentScope.value || !openedFile.value) {
    return;
  }
  fileSaving.value = true;
  try {
    openedFile.value = await writeSkillFile({
      scope: currentScope.value,
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
  if (!currentScope.value) {
    return;
  }
  const name = await promptText("新建文件名", "notes.md");
  if (!name) {
    return;
  }
  const path = joinRelativePath(parentPath, name);
  try {
    const file = await writeSkillFile({ scope: currentScope.value, path, content: "", expectedVersion: null });
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
  if (!currentScope.value) {
    return;
  }
  const name = await promptText("新建目录名", "references");
  if (!name) {
    return;
  }
  const path = joinRelativePath(parentPath, name);
  try {
    await createSkillDirectory(currentScope.value, path);
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
  if (!file || !currentScope.value || !uploadTargetPath.value) {
    return;
  }
  const targetPath = uploadTargetMode.value === "file"
    ? uploadTargetPath.value
    : joinRelativePath(uploadTargetPath.value, file.name);
  try {
    await uploadSkillFile(currentScope.value, targetPath, file);
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
  if (!file || !currentScope.value || !packageTargetPath.value) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".zip")) {
    uiStore.pushNotice({ tone: "warning", title: "请选择 zip 包" });
    return;
  }
  try {
    await uploadSkillPackage(currentScope.value, packageTargetPath.value, file);
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
  if (!file || !currentScope.value || !currentSkill.value) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".zip")) {
    uiStore.pushNotice({ tone: "warning", title: "请选择 zip 包" });
    return;
  }
  await skillStore.replaceCurrentPackage(currentScope.value, file);
  await reloadSkillTree();
  uiStore.pushNotice({ tone: "success", title: "Skill 包已替换" });
}

async function handleAssetPackageReplace(uploadFile: UploadFile): Promise<void> {
  const file = uploadFile.raw;
  assetPackageInput.value?.clearFiles();
  await handleAssetPackageReplaceFile(file);
}

async function renameSelectedEntry(): Promise<void> {
  if (!currentScope.value || !selectedEntry.value) {
    return;
  }
  const name = await promptText("重命名", selectedEntry.value.name);
  if (!name || name === selectedEntry.value.name) {
    return;
  }
  const destination = joinRelativePath(parentRelativePath(selectedEntry.value.path), name);
  try {
    await moveSkillPath(currentScope.value, selectedEntry.value.path, destination);
    await refreshTreeKeepingSelection();
    selectedEntry.value = findLoadedEntry(destination);
    uiStore.pushNotice({ tone: "success", title: "名称已更新" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "重命名失败", body: error instanceof Error ? error.message : "" });
  }
}

async function moveSelectedEntry(): Promise<void> {
  if (!currentScope.value || !selectedEntry.value) {
    return;
  }
  const destination = await promptText("移动到目标路径", selectedEntry.value.path);
  if (!destination || destination === selectedEntry.value.path) {
    return;
  }
  try {
    await moveSkillPath(currentScope.value, selectedEntry.value.path, destination);
    await refreshTreeKeepingSelection();
    selectedEntry.value = findLoadedEntry(destination);
    uiStore.pushNotice({ tone: "success", title: "路径已移动" });
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "移动失败", body: error instanceof Error ? error.message : "" });
  }
}

async function deleteSelectedEntry(): Promise<void> {
  if (!currentScope.value || !selectedEntry.value) {
    return;
  }
  if (!await confirmDanger(`确认删除 ${selectedEntry.value.path}？`)) {
    return;
  }
  try {
    await deleteSkillPath(currentScope.value, selectedEntry.value.path, selectedEntry.value.entry_type === "directory");
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
  if (!currentScope.value || !selectedEntry.value) {
    return;
  }
  try {
    const blob = await downloadSkillPath(currentScope.value, selectedEntry.value.path);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = selectedEntry.value.entry_type === "directory" ? `${selectedEntry.value.name}.zip` : selectedEntry.value.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    uiStore.pushNotice({ tone: "danger", title: "下载失败", body: error instanceof Error ? error.message : "" });
  }
}

function skillRootActions(): SkillAction[] {
  return [
    action("metadata", "元信息", CheckCircle2, "secondary"),
    action("replace-asset-package", "上传替换", PackageOpen, "secondary"),
    action("create-directory", "新建目录", FolderPlus, "secondary"),
    action("create-file", "新建文件", FilePlus, "primary"),
    action("upload-file", "上传文件", Upload, "secondary", true),
    action("delete-skill", "删除 Skill", Trash2, "danger", true),
  ];
}

function skillBrowserActions(): SkillAction[] {
  return [
    action("upload-skill-package", "上传 Skill 包", Upload, "secondary"),
    action("create-skill", "新建 Skill", Plus, "primary"),
  ];
}

function entryActions(entry: ManagedFileEntry): SkillAction[] {
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

function directoryEmptyActions(parentPath: string): SkillAction[] {
  if (!parentPath) {
    return [];
  }
  return [
    action("create-file", "新建文件", FilePlus, "primary"),
    action("create-directory", "新建目录", FolderPlus, "secondary"),
    action("upload-file", "上传文件", Upload, "secondary"),
  ];
}

function action(
  id: SkillActionId,
  label: string,
  icon: SkillAction["icon"],
  tone: SkillAction["tone"],
  wide = false,
): SkillAction {
  return { id, label, icon, tone, wide };
}

async function runSkillAction(
  actionId: SkillActionId,
  entry: ManagedFileEntry | null = selectedEntry.value,
  parentPath = activeDirectoryPath.value,
): Promise<void> {
  closeContextMenu();
  if (actionId === "create-skill") {
    openCreate();
    return;
  }
  if (actionId === "upload-skill-package") {
    openCreateFromPackage();
    return;
  }
  if (actionId === "metadata") {
    openMetadata();
    return;
  }
  if (actionId === "replace-asset-package") {
    openAssetPackageReplace();
    return;
  }
  if (actionId === "delete-skill") {
    await removeCurrent();
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

async function runContextMenuAction(actionId: SkillActionId): Promise<void> {
  const menu = contextMenu.value;
  if (menu.targetSkill && selectedAssetKey.value !== menu.targetSkill.asset_key && currentScope.value) {
    await skillStore.openSkill(currentScope.value, menu.targetSkill.asset_key);
    await reloadSkillTree();
  }
  if (!menu.targetEntry && menu.parentPath) {
    selectedEntry.value = findLoadedEntry(menu.parentPath);
  }
  await runSkillAction(actionId, menu.targetEntry, menu.parentPath);
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

function handleSkillContextMenu(event: MouseEvent, skill: WorkspaceSkillAsset): void {
  event.preventDefault();
  event.stopPropagation();
  contextMenu.value = {
    open: true,
    x: event.clientX,
    y: event.clientY,
    parentPath: skill.path,
    targetEntry: null,
    targetSkill: skill,
    assetBrowser: false,
  };
  void fitContextMenu(event.clientX, event.clientY);
}

function handleSkillBrowserContextMenu(event: MouseEvent): void {
  const actions = skillBrowserActions();
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
    targetSkill: null,
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
    targetSkill: null,
    assetBrowser: false,
  };
  void fitContextMenu(event.clientX, event.clientY);
}

function handleColumnContextMenu(event: MouseEvent, column: FinderColumn): void {
  const actions = directoryEmptyActions(column.path);
  if (!actions.length) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  selectedEntry.value = findLoadedEntry(column.path);
  contextMenu.value = {
    open: true,
    x: event.clientX,
    y: event.clientY,
    parentPath: column.path,
    targetEntry: null,
    targetSkill: null,
    assetBrowser: false,
  };
  void fitContextMenu(event.clientX, event.clientY);
}

function closeContextMenu(): void {
  contextMenu.value = {
    ...contextMenu.value,
    open: false,
    targetEntry: null,
    targetSkill: null,
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
          <h2>{{ fileMode ? inlineFileName : "技能管理" }}</h2>
          <p v-if="fileMode" class="inline-file-path" :title="inlineFilePathLabel">{{ inlineFilePathLabel }}</p>
          <p v-else>Skill 本体元信息由数据库管理，目录内部文件按文件树维护。</p>
        </div>
        <div v-if="!fileMode" class="finder-actions skills-toolbar-actions">
          <el-button
            class="skill-toolbar-button"
            :icon="RefreshCw"
            :disabled="skillRefs.loading.value"
            @click="refresh"
          >
            刷新
          </el-button>
          <el-button
            class="skill-toolbar-button"
            :icon="PackagePlus"
            :disabled="!currentScope || skillRefs.saving.value"
            @click="openCreateFromPackage"
          >
            上传 Skill 包
          </el-button>
          <el-button
            class="skill-toolbar-button primary"
            type="primary"
            :icon="Plus"
            :disabled="!currentScope"
            @click="openCreate"
          >
            新建 Skill
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
        <div v-if="!fileMode && (skillRefs.errorMessage.value || treeError)" class="finder-alerts">
          <StatusBanner
            v-if="skillRefs.errorMessage.value"
            tone="danger"
            title="Skill 操作失败"
            :body="skillRefs.errorMessage.value"
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
            <span>技能浏览</span>
            <el-tag size="small" type="info" effect="plain">{{ filteredSkills.length }} 项</el-tag>
          </el-header>
          <el-input v-model="keyword" class="skill-browser-search" type="search" placeholder="搜索 Skill" clearable>
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-scrollbar class="skill-browser-list" @contextmenu="handleSkillBrowserContextMenu">
            <el-skeleton v-if="skillRefs.loading.value" :rows="5" animated class="finder-column-loading" />
            <el-empty
              v-else-if="!filteredSkills.length"
              class="finder-column-empty"
              description="新建后会写入数据库元信息，并创建对应 .skills 目录。"
            >
              <template #image>
                <el-icon class="finder-empty-symbol"><PackageOpen /></el-icon>
              </template>
              <template #description>
                <strong>暂无 Skill</strong>
                <p>新建后会写入数据库元信息，并创建对应 .skills 目录。</p>
              </template>
            </el-empty>
            <el-space v-else class="finder-entry-list" direction="vertical" fill :size="2">
              <el-button
                v-for="skill in filteredSkills"
                :key="skill.asset_key"
                class="finder-row skill-root-row"
                text
                :class="{ selected: selectedAssetKey === skill.asset_key }"
                @click="openSkill(skill)"
                @contextmenu="handleSkillContextMenu($event, skill)"
              >
                <el-icon class="finder-entry-icon skill"><PackageOpen /></el-icon>
                <span class="finder-entry-text">
                  <strong>{{ skill.name }}</strong>
                  <small>{{ skill.description || skill.asset_key }}</small>
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
            :key="`${column.path}-${columnIndex}`"
            class="finder-column"
            width="50%"
          >
            <el-header class="finder-column-header" height="42px">
              <span>{{ columnIndex === 0 ? currentSkill?.name : column.path.split('/').pop() }}</span>
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

          <el-aside
            v-if="skillRefs.opening.value || (currentSkill && !columns.length)"
            class="finder-column"
            width="50%"
          >
            <el-header class="finder-column-header" height="42px">
              <span>{{ skillRefs.opening.value ? "正在加载 Skill" : currentSkill?.name }}</span>
              <el-tag size="small" type="info" effect="plain">0 项</el-tag>
            </el-header>
            <el-scrollbar class="finder-column-body">
              <el-skeleton
                v-if="skillRefs.opening.value || treeLoading"
                :rows="5"
                animated
                class="finder-column-loading"
              />
            </el-scrollbar>
          </el-aside>
          </el-scrollbar>
        </el-main>

        <el-aside class="finder-detail-column skill-detail-column" width="25%">
          <el-header class="detail-panel-header" height="38px">
            <h3>详情</h3>
            <el-tag v-if="selectedEntry || currentSkill" size="small" type="primary" effect="light">
              {{ selectedEntry ? selectedEntry.entry_type === "directory" ? "目录" : "文件" : "Skill" }}
            </el-tag>
          </el-header>

          <LoadingBlock
            v-if="skillRefs.opening.value"
            title="正在读取 Skill"
            body="请稍候。"
          />

          <el-empty
            v-else-if="!currentSkill"
            class="finder-detail-empty"
            description="左侧选择 Skill 后，在中间浏览目录，在这里执行本体与文件操作。"
          >
            <template #image>
              <el-icon class="finder-empty-symbol"><PackageOpen /></el-icon>
            </template>
            <template #description>
              <strong>选择一个 Skill</strong>
              <p>左侧选择 Skill 后，在中间浏览目录，在这里执行本体与文件操作。</p>
            </template>
          </el-empty>

          <el-scrollbar v-else class="file-detail-panel">
            <div class="file-detail-lockup">
              <el-icon v-if="!selectedEntry" class="file-detail-icon skill"><PackageOpen /></el-icon>
              <el-icon v-else-if="selectedEntry.entry_type === 'directory'" class="file-detail-icon"><Folder /></el-icon>
              <el-icon v-else class="file-detail-icon file"><File /></el-icon>
              <div>
                <h3>{{ selectedEntry?.name || currentSkill.name }}</h3>
                <p>{{ selectedEntry ? selectedEntry.entry_type === "directory" ? "文件夹" : `${fileKind(selectedEntry)} 文件` : "Skill 本体" }}</p>
              </div>
            </div>

            <el-descriptions class="file-detail-list" :column="1" size="small" border>
              <template v-if="!selectedEntry">
                <el-descriptions-item label="目录">{{ currentSkill.path }}</el-descriptions-item>
                <el-descriptions-item label="状态">{{ assetStatusLabel(currentSkill.status) }}</el-descriptions-item>
                <el-descriptions-item label="描述">{{ currentSkill.description || "-" }}</el-descriptions-item>
              </template>
              <template v-else>
                <template v-for="[label, value] in selectedEntryMeta" :key="label">
                  <el-descriptions-item :label="label">{{ value }}</el-descriptions-item>
                </template>
              </template>
            </el-descriptions>

            <div class="detail-action-section">
              <h4>{{ selectedEntry ? "文件操作" : "Skill 本体操作" }}</h4>
              <div class="file-detail-file-actions">
                <el-button
                  v-for="actionItem in detailActions"
                  :key="actionItem.id"
                  :type="actionItem.tone === 'primary' ? 'primary' : 'default'"
                  :class="[
                    actionItem.tone === 'primary' ? 'file-primary-action' : 'file-secondary-action',
                    { danger: actionItem.tone === 'danger', 'full-width': actionItem.wide },
                  ]"
                  @click="runSkillAction(actionItem.id)"
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
      title="新建 Skill"
      subtitle="Skill 名称会作为 .skills 下的目录名，asset_key 由后端生成。"
      :saving="skillRefs.saving.value"
      submit-text="创建"
      @close="closeCreate"
      @submit="submitCreate"
    >
      <div class="asset-form">
        <FieldInput v-model="form.name" label="Skill 名称" placeholder="network-troubleshoot" />
        <FieldInput v-model="form.description" label="描述" placeholder="描述用途和边界" />
        <label>
          <span>状态</span>
          <el-select v-model="form.status" class="asset-form-select">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </label>
        <label>
          <span>SKILL.md</span>
          <el-input v-model="form.content" class="asset-form-textarea" type="textarea" :autosize="{ minRows: 16 }" />
        </label>
      </div>
    </FormDrawer>

    <FormDrawer
      :open="metadataOpen"
      title="编辑 Skill 元信息"
      subtitle="重命名会同步移动 .skills 下的 Skill 目录。"
      :saving="skillRefs.saving.value"
      @close="metadataOpen = false"
      @submit="submitMetadata"
    >
      <div class="asset-form">
        <FieldInput v-model="metadataForm.name" label="Skill 名称" />
        <FieldInput v-model="metadataForm.description" label="描述" />
        <label>
          <span>状态</span>
          <el-select v-model="metadataForm.status" class="asset-form-select">
            <el-option label="启用" value="enabled" />
            <el-option label="停用" value="disabled" />
          </el-select>
        </label>
      </div>
    </FormDrawer>

    <el-upload ref="uploadInput" class="hidden-upload" action="#" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleUploadFileChange" />
    <el-upload ref="packageInput" class="hidden-upload" action="#" accept=".zip,application/zip" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleInternalPackageReplace" />
    <el-upload ref="assetPackageInput" class="hidden-upload" action="#" accept=".zip,application/zip" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleAssetPackageReplace" />
    <el-upload ref="createPackageInput" class="hidden-upload" action="#" accept=".zip,application/zip" :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleCreatePackage" />
  </div>
</template>
