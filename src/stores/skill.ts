import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  createSkill,
  deleteSkill,
  getSkill,
  listSkills,
  putSkill,
  replaceSkillPackage,
  uploadNewSkillPackage,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import type { AdminScopeRef, SkillDetail, WorkspaceSkillAsset } from "@/types/admin";

export const useSkillStore = defineStore("skill", () => {
  const loading = ref(false);
  const opening = ref(false);
  const saving = ref(false);
  const errorMessage = ref("");

  const skills = ref<WorkspaceSkillAsset[]>([]);
  const currentSkill = ref<SkillDetail | null>(null);
  const draftContent = ref("");
  const isDirty = computed(() => {
    return currentSkill.value !== null && draftContent.value !== currentSkill.value.content;
  });

  async function loadSkills(scope: AdminScopeRef): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      skills.value = await listSkills(scope);
    } catch (error) {
      skills.value = [];
      errorMessage.value = error instanceof ApiError ? error.message : "加载 Skill 列表失败。";
    } finally {
      loading.value = false;
    }
  }

  async function openSkill(scope: AdminScopeRef, assetKey: string): Promise<void> {
    opening.value = true;
    errorMessage.value = "";
    try {
      currentSkill.value = await getSkill(scope, assetKey);
      draftContent.value = currentSkill.value.content;
    } catch (error) {
      currentSkill.value = null;
      draftContent.value = "";
      errorMessage.value = error instanceof ApiError ? error.message : "读取 Skill 失败。";
    } finally {
      opening.value = false;
    }
  }

  async function createNewSkill(payload: {
    scope: AdminScopeRef;
    name: string;
    description: string;
    status: string;
    content: string;
  }): Promise<SkillDetail> {
    saving.value = true;
    errorMessage.value = "";
    try {
      const skill = await createSkill(payload);
      currentSkill.value = skill;
      draftContent.value = skill.content;
      await loadSkills(payload.scope);
      return skill;
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "创建 Skill 失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function createFromPackage(scope: AdminScopeRef, name: string, file: File): Promise<SkillDetail> {
    saving.value = true;
    errorMessage.value = "";
    try {
      const skill = await uploadNewSkillPackage(scope, name, file);
      currentSkill.value = skill;
      draftContent.value = skill.content;
      await loadSkills(scope);
      return skill;
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "上传 Skill 包失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function saveSkill(scope: AdminScopeRef): Promise<void> {
    if (!currentSkill.value) {
      return;
    }
    saving.value = true;
    errorMessage.value = "";
    try {
      currentSkill.value = await putSkill(scope, currentSkill.value.asset_key, {
        name: currentSkill.value.name,
        description: currentSkill.value.description,
        status: currentSkill.value.status,
        content: draftContent.value,
      });
      draftContent.value = currentSkill.value.content;
      await loadSkills(scope);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "保存 Skill 失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function updateCurrentMetadata(
    scope: AdminScopeRef,
    payload: {
      name: string;
      description: string;
      status: string;
    },
  ): Promise<void> {
    if (!currentSkill.value) {
      return;
    }
    saving.value = true;
    errorMessage.value = "";
    try {
      currentSkill.value = await putSkill(scope, currentSkill.value.asset_key, {
        ...payload,
        content: draftContent.value,
      });
      draftContent.value = currentSkill.value.content;
      await loadSkills(scope);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "更新 Skill 元信息失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function removeSkill(scope: AdminScopeRef, assetKey: string): Promise<void> {
    await deleteSkill(scope, assetKey);
    if (currentSkill.value?.asset_key === assetKey) {
      currentSkill.value = null;
      draftContent.value = "";
    }
    await loadSkills(scope);
  }

  async function replaceCurrentPackage(scope: AdminScopeRef, file: File): Promise<void> {
    if (!currentSkill.value) {
      return;
    }
    saving.value = true;
    errorMessage.value = "";
    try {
      currentSkill.value = await replaceSkillPackage(scope, currentSkill.value.asset_key, file);
      draftContent.value = currentSkill.value.content;
      await loadSkills(scope);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "上传 Skill 包失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  function clearCurrentSkill(): void {
    currentSkill.value = null;
    draftContent.value = "";
  }

  function reset(): void {
    loading.value = false;
    opening.value = false;
    saving.value = false;
    errorMessage.value = "";
    skills.value = [];
    currentSkill.value = null;
    draftContent.value = "";
  }

  return {
    loading,
    opening,
    saving,
    errorMessage,
    skills,
    currentSkill,
    draftContent,
    isDirty,
    loadSkills,
    openSkill,
    createNewSkill,
    createFromPackage,
    saveSkill,
    updateCurrentMetadata,
    removeSkill,
    replaceCurrentPackage,
    clearCurrentSkill,
    reset,
  };
});
