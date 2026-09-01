<script setup lang="ts">
import {
  Close,
  CollectionTag,
  Picture,
  Promotion,
  QuestionFilled,
  Tickets,
} from "@element-plus/icons-vue";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

import type {
  ChatCapabilities,
  PendingAsk,
  SlashCandidate,
  SlashTarget,
} from "@/types";

const props = defineProps<{
  disabled: boolean;
  targets: SlashCandidate[];
  pendingAsk: PendingAsk | null;
  capabilities: ChatCapabilities;
  imageSupportStatus: "loading" | "supported" | "unsupported" | "error";
}>();

const emit = defineEmits<{
  send: [content: string, files: File[], slashTarget: SlashTarget | null];
  answerAsk: [answers: Record<string, string | string[]>];
  dismissAsk: [answers: Record<string, string | string[]>];
  refreshTargets: [];
}>();

interface ImageItem {
  key: string;
  file: File;
  previewUrl: string;
}

const content = ref("");
const selectedTarget = ref<SlashCandidate | null>(null);
const imageItems = ref<ImageItem[]>([]);
const imageError = ref("");
const imageInputRef = ref<HTMLInputElement | null>(null);
const composerInputRef = ref<{ focus: () => void } | null>(null);
const slashDismissed = ref(false);
const questionIndex = ref(0);
const askAnswers = ref<Record<string, string | string[]>>({});
const customAnswer = ref("");
const multiSelection = ref<string[]>([]);

const slashQuery = computed(() => {
  const match = content.value.match(/^\/([^\s]*)$/u);
  return match ? match[1].toLowerCase() : null;
});
const visibleTargets = computed(() => {
  const query = slashQuery.value;
  if (query === null) return [];
  return props.targets
    .filter((target) =>
      [target.name, target.description, target.kind].join(" ").toLowerCase().includes(query),
    )
    .slice(0, 8);
});
const showSlashPanel = computed(
  () => !slashDismissed.value && !selectedTarget.value && slashQuery.value !== null,
);
const imageInputEnabled = computed(
  () =>
    !props.disabled &&
    !props.pendingAsk &&
    props.imageSupportStatus === "supported",
);
const imageButtonTip = computed(() => {
  if (props.disabled) return "智能体执行中，暂时无法上传图片";
  if (props.pendingAsk) return "请先完成当前补充信息";
  if (props.imageSupportStatus === "loading") return "正在获取当前模型能力";
  if (props.imageSupportStatus === "unsupported") return "当前模型不支持图片输入";
  if (props.imageSupportStatus === "error") return "暂时无法获取当前模型能力";
  return "上传图片";
});
const placeholder = computed(() => {
  if (props.pendingAsk) return "请先回答上方问题";
  if (props.disabled) return "智能体执行中，暂无法输入信息…";
  if (selectedTarget.value?.kind === "skill") return "输入技能参数";
  if (selectedTarget.value?.kind === "scene") return "输入当前场景下的问题";
  return "输入消息，输入 / 选择技能或场景";
});
const canSend = computed(
  () =>
    !props.disabled &&
    !props.pendingAsk &&
    (Boolean(content.value.trim()) || Boolean(selectedTarget.value) || imageItems.value.length > 0),
);
const activeQuestion = computed(() => props.pendingAsk?.questions[questionIndex.value] ?? null);
const askProgress = computed(
  () => `${Math.min(questionIndex.value + 1, props.pendingAsk?.questions.length ?? 1)} of ${props.pendingAsk?.questions.length ?? 1}`,
);
const askDialogVisible = computed({
  get: () => Boolean(props.pendingAsk && activeQuestion.value),
  set: (open: boolean) => {
    if (!open) dismissAsk();
  },
});

watch(slashQuery, (value) => {
  slashDismissed.value = false;
  if (value !== null) emit("refreshTargets");
});

watch(
  () => props.pendingAsk?.askId,
  () => {
    questionIndex.value = 0;
    askAnswers.value = {};
    customAnswer.value = "";
    multiSelection.value = [];
  },
);

function selectTarget(target: SlashCandidate): void {
  selectedTarget.value = target;
  slashDismissed.value = true;
  content.value = "";
  void nextTick(() => composerInputRef.value?.focus());
}

function removeTarget(): void {
  selectedTarget.value = null;
  void nextTick(() => composerInputRef.value?.focus());
}

function send(): void {
  if (!canSend.value) return;
  const target = selectedTarget.value;
  emit(
    "send",
    content.value.trim(),
    imageItems.value.map((item) => item.file),
    target ? { kind: target.kind, asset_key: target.asset_key, name: target.name } : null,
  );
  content.value = "";
  selectedTarget.value = null;
  clearImages();
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && showSlashPanel.value) {
    slashDismissed.value = true;
    return;
  }
  if (event.key === "Backspace" && !content.value && selectedTarget.value) {
    event.preventDefault();
    removeTarget();
    return;
  }
  if (event.key === "Enter" && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
    event.preventDefault();
    send();
  }
}

function openImagePicker(): void {
  if (imageInputEnabled.value) imageInputRef.value?.click();
}

function handleImageInput(event: Event): void {
  const input = event.target instanceof HTMLInputElement ? event.target : null;
  addImages(Array.from(input?.files ?? []));
  if (input) input.value = "";
}

function handlePaste(event: ClipboardEvent): void {
  const files = Array.from(event.clipboardData?.files ?? []).filter((file) =>
    file.type.startsWith("image/"),
  );
  if (!files.length) return;
  event.preventDefault();
  addImages(files);
}

function addImages(files: File[]): void {
  imageError.value = "";
  if (!imageInputEnabled.value) {
    imageError.value = imageButtonTip.value;
    return;
  }
  const accepted = new Set(props.capabilities.accepted_mime_types);
  const supported = files.filter(
    (file) => accepted.has(file.type) && file.size <= props.capabilities.max_image_bytes,
  );
  if (supported.length !== files.length) {
    imageError.value = `仅支持 ${[...accepted].join(" / ")}，且单张不超过 ${formatBytes(props.capabilities.max_image_bytes)}`;
  }
  const slots = Math.max(props.capabilities.max_images_per_message - imageItems.value.length, 0);
  if (supported.length > slots) {
    imageError.value = `单次最多上传 ${props.capabilities.max_images_per_message} 张图片`;
  }
  imageItems.value.push(
    ...supported.slice(0, slots).map((file) => ({
      key: `${file.name}-${file.size}-${file.lastModified}-${Date.now()}`,
      file,
      previewUrl: URL.createObjectURL(file),
    })),
  );
}

function removeImage(key: string): void {
  const item = imageItems.value.find((candidate) => candidate.key === key);
  if (item) URL.revokeObjectURL(item.previewUrl);
  imageItems.value = imageItems.value.filter((candidate) => candidate.key !== key);
}

function clearImages(): void {
  imageItems.value.forEach((item) => URL.revokeObjectURL(item.previewUrl));
  imageItems.value = [];
  imageError.value = "";
}

function chooseSingleAnswer(label: string): void {
  recordAnswer(cleanOptionLabel(label));
}

function submitMultiAnswer(): void {
  if (!multiSelection.value.length) return;
  recordAnswer(multiSelection.value.map(cleanOptionLabel));
}

function submitCustomAnswer(): void {
  const value = customAnswer.value.trim();
  if (value) recordAnswer(value);
}

function recordAnswer(answer: string | string[]): void {
  const question = activeQuestion.value;
  if (!question) return;
  const key = question.question || question.header || `question_${questionIndex.value + 1}`;
  askAnswers.value = { ...askAnswers.value, [key]: answer };
  if (questionIndex.value < (props.pendingAsk?.questions.length ?? 1) - 1) {
    questionIndex.value += 1;
    customAnswer.value = "";
    multiSelection.value = [];
    return;
  }
  emit("answerAsk", { ...askAnswers.value });
}

function dismissAsk(): void {
  if (!props.pendingAsk || props.disabled) return;
  emit("dismissAsk", { ...askAnswers.value });
}

function cleanOptionLabel(value: string): string {
  return value.replace(/\s*\(Recommended\)\s*$/i, "").trim();
}

function isRecommended(value: string): boolean {
  return /\(Recommended\)|推荐/u.test(value);
}

function formatBytes(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${Math.round((bytes / 1024 / 1024) * 10) / 10} MB`
    : `${Math.round(bytes / 1024)} KB`;
}

onBeforeUnmount(clearImages);
</script>

<template>
  <div class="composer-wrap">
    <el-card v-if="showSlashPanel" class="slash-panel" shadow="never">
      <div class="slash-panel-heading">
        <span>选择技能或场景</span>
        <small>{{ visibleTargets.length }} 项</small>
      </div>
      <button
        v-for="target in visibleTargets"
        :key="`${target.kind}-${target.asset_key}`"
        type="button"
        class="slash-option"
        @click="selectTarget(target)"
      >
        <el-icon><Tickets v-if="target.kind === 'skill'" /><CollectionTag v-else /></el-icon>
        <span>
          <strong>/{{ target.name }}</strong>
          <small>{{ target.description || (target.kind === "skill" ? "技能" : "场景") }}</small>
        </span>
        <em>{{ target.kind === "skill" ? "技能" : "场景" }}</em>
      </button>
      <el-empty v-if="!visibleTargets.length" description="没有匹配的技能或场景" :image-size="48" />
    </el-card>

    <el-dialog
      v-model="askDialogVisible"
      class="composer-ask-dialog"
      width="min(38.75rem, calc(100vw - 2rem))"
      append-to-body
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="!disabled"
    >
      <template #header>
        <div class="composer-ask-heading">
          <span><el-icon><QuestionFilled /></el-icon>需要确认</span>
          <small>{{ askProgress }}</small>
        </div>
      </template>

      <div v-if="activeQuestion">
        <div class="composer-ask-question">
          <strong v-if="activeQuestion.header">{{ activeQuestion.header }}</strong>
          <p>{{ activeQuestion.question || activeQuestion.header }}</p>
        </div>
        <el-checkbox-group
          v-if="activeQuestion.multiSelect"
          v-model="multiSelection"
          class="composer-ask-options"
        >
          <el-checkbox
            v-for="(option, index) in activeQuestion.options"
            :key="`${option.label}-${index}`"
            class="composer-ask-checkbox"
            :value="option.label"
            border
          >
            <span class="composer-ask-option-copy">
              <strong>{{ cleanOptionLabel(option.label) }}</strong>
              <small v-if="option.description">{{ option.description }}</small>
            </span>
          </el-checkbox>
          <el-button type="primary" :disabled="!multiSelection.length" @click="submitMultiAnswer">
            确认选择
          </el-button>
        </el-checkbox-group>
        <div v-else class="composer-ask-options">
          <el-button
            v-for="(option, index) in activeQuestion.options"
            :key="`${option.label}-${index}`"
            class="composer-ask-option"
            @click="chooseSingleAnswer(option.label)"
          >
            <span class="composer-ask-option-index">{{ index + 1 }}.</span>
            <span class="composer-ask-option-copy">
              <strong>{{ cleanOptionLabel(option.label) }}</strong>
              <small v-if="option.description || option.preview">
                {{ option.description || option.preview }}
              </small>
            </span>
            <em v-if="isRecommended(option.label)">推荐</em>
          </el-button>
        </div>
        <div class="composer-ask-custom">
          <el-input v-model="customAnswer" placeholder="请输入其他答案" @keyup.enter="submitCustomAnswer" />
          <el-button type="primary" :disabled="!customAnswer.trim()" @click="submitCustomAnswer">发送</el-button>
        </div>
      </div>

      <template #footer>
        <div class="composer-ask-actions">
          <span>回答后，智能体会从暂停位置继续执行。</span>
          <el-button :disabled="disabled" @click="dismissAsk">忽略</el-button>
        </div>
      </template>
    </el-dialog>

    <el-form class="composer" :class="{ 'composer-disabled': disabled || pendingAsk }" @submit.prevent="send">
      <el-tag
        v-if="selectedTarget"
        class="composer-target-token"
        :class="selectedTarget.kind"
        effect="light"
        closable
        @close="removeTarget"
      >
        <el-icon><Tickets v-if="selectedTarget.kind === 'skill'" /><CollectionTag v-else /></el-icon>
        <span>/{{ selectedTarget.name }}</span>
      </el-tag>
      <el-input
        ref="composerInputRef"
        v-model="content"
        class="composer-input"
        type="textarea"
        :rows="1"
        resize="none"
        :autosize="{ minRows: 1, maxRows: 5 }"
        :placeholder="placeholder"
        :disabled="disabled || Boolean(pendingAsk)"
        @keydown="handleKeydown"
        @paste="handlePaste"
      />
      <input
        ref="imageInputRef"
        class="composer-image-input"
        type="file"
        :accept="capabilities.accepted_mime_types.join(',')"
        multiple
        @change="handleImageInput"
      />
      <div class="composer-actions">
        <el-tooltip :content="imageButtonTip" placement="top">
          <span class="composer-image-tooltip">
            <el-button
              class="composer-action-button image-button"
              :disabled="!imageInputEnabled"
              :icon="Picture"
              aria-label="上传图片"
              @click="openImagePicker"
            />
          </span>
        </el-tooltip>
        <el-button
          class="composer-action-button send-button"
          :disabled="!canSend"
          native-type="submit"
          :icon="Promotion"
          aria-label="发送消息"
        />
      </div>
    </el-form>

    <el-card v-if="imageItems.length || imageError" class="composer-image-panel" shadow="never">
      <div class="composer-image-list">
        <figure v-for="item in imageItems" :key="item.key" class="composer-image-item">
          <img :src="item.previewUrl" :alt="item.file.name" />
          <el-button circle :icon="Close" aria-label="移除图片" @click="removeImage(item.key)" />
        </figure>
      </div>
      <el-alert v-if="imageError" type="error" :closable="false" show-icon :title="imageError" />
    </el-card>
  </div>
</template>
