import { ref } from "vue";
import { defineStore } from "pinia";

import {
  createScene,
  createGitScene,
  deleteScene,
  syncSceneGit,
  listScenes,
  updateSceneGitConfig,
  updateScene,
  uploadNewScenePackage,
  uploadScenePackage,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import type { AdminScopeRef, WorkspaceSceneAsset } from "@/types/admin";

export const useSceneStore = defineStore("scene", () => {
  const loading = ref(false);
  const saving = ref(false);
  const errorMessage = ref("");
  const scenes = ref<WorkspaceSceneAsset[]>([]);
  const currentScene = ref<WorkspaceSceneAsset | null>(null);

  async function loadScenes(scope: AdminScopeRef, options: { preserveCurrent?: boolean } = {}): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      const selectedAssetKey = options.preserveCurrent ? currentScene.value?.asset_key ?? "" : "";
      scenes.value = await listScenes(scope);
      if (selectedAssetKey) {
        currentScene.value = scenes.value.find((scene) => scene.asset_key === selectedAssetKey) ?? null;
      } else {
        currentScene.value = null;
      }
    } catch (error) {
      scenes.value = [];
      currentScene.value = null;
      errorMessage.value = error instanceof ApiError ? error.message : "加载 Scene 列表失败。";
    } finally {
      loading.value = false;
    }
  }

  function selectScene(assetKey: string): void {
    currentScene.value = scenes.value.find((scene) => scene.asset_key === assetKey) ?? null;
  }

  async function createNewScene(payload: {
    scope: AdminScopeRef;
    name: string;
    description: string;
    status: string;
    requiredSkillAssetKey: string;
  }): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      const created = await createScene(payload);
      await loadScenes(payload.scope);
      selectScene(created.asset_key);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "创建 Scene 失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function createNewGitScene(payload: {
    scope: AdminScopeRef;
    name: string;
    description: string;
    status: string;
    requiredSkillAssetKey: string;
    gitRepositoryId: string;
    branch: string;
    ref: string;
    subdir: string;
    autoSyncEnabled: boolean;
    dailySyncTime: string;
    timezone: string;
  }): Promise<WorkspaceSceneAsset> {
    saving.value = true;
    errorMessage.value = "";
    try {
      const created = await createGitScene(payload);
      await loadScenes(payload.scope);
      selectScene(created.asset_key);
      return created;
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "创建 Git Scene 失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function createFromPackage(scope: AdminScopeRef, name: string, file: File): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      const created = await uploadNewScenePackage(scope, name, file);
      await loadScenes(scope);
      selectScene(created.asset_key);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "上传 Scene 包失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function updateCurrentScene(
    scope: AdminScopeRef,
    payload: {
      name: string;
      description: string;
      status: string;
      requiredSkillAssetKey: string;
    },
  ): Promise<void> {
    if (!currentScene.value) {
      return;
    }
    saving.value = true;
    errorMessage.value = "";
    try {
      const updated = await updateScene(scope, currentScene.value.asset_key, payload);
      await loadScenes(scope);
      selectScene(updated.asset_key);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "更新 Scene 失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function updateCurrentSceneGitConfig(
    scope: AdminScopeRef,
    assetKey: string,
    payload: {
      gitRepositoryId?: string;
      branch?: string;
      ref?: string;
      subdir?: string;
      autoSyncEnabled?: boolean;
      dailySyncTime?: string;
      timezone?: string;
    },
  ): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      const git = await updateSceneGitConfig(scope, assetKey, payload);
      await loadScenes(scope);
      selectScene(assetKey);
      if (currentScene.value) {
        currentScene.value = { ...currentScene.value, git };
      }
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "更新 Git Scene 配置失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function removeScene(scope: AdminScopeRef, assetKey: string): Promise<void> {
    await deleteScene(scope, assetKey);
    if (currentScene.value?.asset_key === assetKey) {
      currentScene.value = null;
    }
    await loadScenes(scope);
  }

  async function replacePackage(scope: AdminScopeRef, assetKey: string, file: File): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      const updated = await uploadScenePackage(scope, assetKey, file);
      await loadScenes(scope);
      selectScene(updated.asset_key);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "上传 Scene 包失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function syncGitScene(scope: AdminScopeRef, assetKey: string) {
    saving.value = true;
    errorMessage.value = "";
    try {
      return await syncSceneGit(scope, assetKey);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "同步 Git Scene 失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  function clearCurrentScene(): void {
    currentScene.value = null;
  }

  function reset(): void {
    loading.value = false;
    saving.value = false;
    errorMessage.value = "";
    scenes.value = [];
    currentScene.value = null;
  }

  return {
    loading,
    saving,
    errorMessage,
    scenes,
    currentScene,
    loadScenes,
    selectScene,
    createNewScene,
    createNewGitScene,
    createFromPackage,
    updateCurrentScene,
    updateCurrentSceneGitConfig,
    removeScene,
    replacePackage,
    syncGitScene,
    clearCurrentScene,
    reset,
  };
});
