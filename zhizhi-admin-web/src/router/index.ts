import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useBootstrapStore } from "@/stores/bootstrap";
import { useNavigationStore } from "@/stores/navigation";
import DataSourceView from "@/views/DataSourceView.vue";
import AccountsView from "@/views/AccountsView.vue";
import DashboardView from "@/views/DashboardView.vue";
import GlobalManagementView from "@/views/GlobalManagementView.vue";
import GitRepositoryManagementView from "@/views/GitRepositoryManagementView.vue";
import LoginView from "@/views/LoginView.vue";
import ModelManagementView from "@/views/ModelManagementView.vue";
import OrganizationView from "@/views/OrganizationView.vue";
import RolesView from "@/views/RolesView.vue";
import RecoveryView from "@/views/RecoveryView.vue";
import ScenesView from "@/views/ScenesView.vue";
import SkillsView from "@/views/SkillsView.vue";
import SetupView from "@/views/SetupView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/setup",
      component: SetupView,
      meta: { title: "系统初始化", auth: false },
    },
    {
      path: "/recovery",
      component: RecoveryView,
      meta: { title: "安装状态恢复", auth: false },
    },
    {
      path: "/login",
      component: LoginView,
      meta: { title: "后台登录", auth: false },
    },
    {
      path: "/",
      component: DashboardView,
      meta: { title: "首页", auth: true },
    },
    {
      path: "/dashboard",
      redirect: "/",
      meta: { auth: true },
    },
    {
      path: "/global",
      component: GlobalManagementView,
      meta: { title: "全局管理", auth: true, superOnly: true },
    },
    {
      path: "/org",
      component: OrganizationView,
      meta: { title: "组织管理", auth: true },
    },
    {
      path: "/accounts",
      component: AccountsView,
      meta: { title: "管理员账号", auth: true },
    },
    {
      path: "/models",
      component: ModelManagementView,
      meta: { title: "模型管理", auth: true },
    },
    {
      path: "/scene-git",
      component: GitRepositoryManagementView,
      meta: { title: "场景 Git 授权", auth: true },
    },
    {
      path: "/data-sources",
      component: DataSourceView,
      meta: { title: "数据源管理", auth: true },
    },
    {
      path: "/roles",
      component: RolesView,
      meta: { title: "角色管理", auth: true, superOnly: true },
    },
    {
      path: "/skills",
      component: SkillsView,
      meta: { title: "技能管理", auth: true },
    },
    {
      path: "/scenes",
      component: ScenesView,
      meta: { title: "Scene 管理", auth: true },
    },
  ],
});

router.beforeEach(async (to) => {
  const bootstrapStore = useBootstrapStore();
  const authStore = useAuthStore();
  const navigationStore = useNavigationStore();
  if (!bootstrapStore.checked && !bootstrapStore.loading) {
    try {
      await bootstrapStore.refresh();
    } catch {
      return to.path === "/setup" ? true : "/setup";
    }
  }

  if (bootstrapStore.state === "setup_required") {
    return to.path === "/setup" ? true : "/setup";
  }
  if (bootstrapStore.state === "recovery_required") {
    return to.path === "/recovery" ? true : "/recovery";
  }
  if (bootstrapStore.state === null) {
    return to.path === "/setup" ? true : "/setup";
  }
  if (["/setup", "/recovery"].includes(to.path)) {
    return "/login";
  }

  const requiresAuth = to.meta.auth !== false;

  if (!authStore.sessionChecked && !authStore.loading) {
    await authStore.restoreSession();
  }

  if (!requiresAuth) {
    if (authStore.isAuthenticated && to.path === "/login") {
      return navigationStore.defaultPath;
    }
    return true;
  }

  if (!authStore.isAuthenticated) {
    return "/login";
  }

  if (to.meta.superOnly && !authStore.isSuper) {
    return navigationStore.defaultPath;
  }

  return true;
});
